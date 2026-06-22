import json
from collections import Counter
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from pkcs.context_pack.models import ContextPackEvidence, ContextPackResponse
from pkcs.eval.models import (
    M3ComparisonPassDiagnostics,
    M3ComparisonPassSummary,
    M3ComparisonQueryResult,
    M3ComparisonReport,
    M3ComparisonSummary,
    M3ContextPackQuality,
    M3EvalInputError,
    M3EvalQuery,
    M3EvalQueryResult,
    M3EvalReport,
    M3EvalSummary,
    M3ResultDistribution,
    M3SearchQuality,
    M3_EVAL_SUITE_LOCKED_REGRESSION,
    M3_FAILURE_CLASSES,
    M3_FAILURE_EVIDENCE_SELECTION_GAP,
    M3_FAILURE_MISSING_ALIAS,
    M3_FAILURE_MISSING_GLOSSARY,
    M3_FAILURE_SEMANTIC_GAP,
)
from pkcs.search.models import SearchResponse, SearchResult
from pkcs.search.planning import (
    PASS_ASCII_ENTITY,
    PASS_COMBINED,
    PASS_GLOSSARY_EXPANSION,
    PASS_ORIGINAL,
    PASS_SOURCE_ALIAS,
)


M3C_COMPARISON_SUITE = "m3c"
NOISY_RESULT_RATIO_THRESHOLD = 0.5
SOURCE_CONCENTRATION_MIN_RESULTS = 3
SOURCE_CONCENTRATION_SHARE_THRESHOLD = 0.8


class SearchServiceLike(Protocol):
    def search_knowledge(
        self,
        *,
        query: str,
        knowledge_type: str | None = None,
        canonical_key: str | None = None,
        top_k: int | None = None,
    ) -> SearchResponse:
        pass


class ContextPackServiceLike(Protocol):
    def get_context_pack(
        self,
        *,
        query: str,
        knowledge_type: str | None = None,
        canonical_key: str | None = None,
        top_k: int | None = None,
        budget_tokens: int | None = None,
    ) -> ContextPackResponse:
        pass


class PlannedSearchServiceLike(Protocol):
    def search_knowledge(
        self,
        *,
        query: str,
        knowledge_type: str | None = None,
        canonical_key: str | None = None,
        top_k: int | None = None,
    ) -> Any:
        pass


def load_m3_eval_queries(path: Path) -> list[M3EvalQuery]:
    rows: list[M3EvalQuery] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            raise M3EvalInputError(f"m3 eval line {line_number}: invalid JSON") from exc
        if not isinstance(payload, dict):
            raise M3EvalInputError(f"m3 eval line {line_number}: row must be an object")
        rows.append(M3EvalQuery.from_dict(payload, line_number=line_number))
    if not rows:
        raise M3EvalInputError(f"{path} must contain at least one M3 eval row")
    return rows


class M3BaselineEvaluator:
    def __init__(
        self,
        *,
        search_service: SearchServiceLike,
        context_pack_service: ContextPackServiceLike,
        search_top_k: int = 10,
        context_top_k: int = 10,
        context_budget_tokens: int | None = None,
    ) -> None:
        if search_top_k < 10:
            raise M3EvalInputError("search_top_k must be at least 10 so top_10_hit is meaningful")
        if context_top_k < 1:
            raise M3EvalInputError("context_top_k must be at least 1")
        if context_budget_tokens is not None and context_budget_tokens < 1:
            raise M3EvalInputError("context_budget_tokens must be at least 1 when set")
        self.search_service = search_service
        self.context_pack_service = context_pack_service
        self.search_top_k = search_top_k
        self.context_top_k = context_top_k
        self.context_budget_tokens = context_budget_tokens

    @classmethod
    def from_settings(
        cls,
        *,
        search_top_k: int = 10,
        context_top_k: int = 10,
        context_budget_tokens: int | None = None,
    ) -> "M3BaselineEvaluator":
        from pkcs.context_pack import ContextPackService
        from pkcs.search import SearchService

        return cls(
            search_service=SearchService.from_settings(),
            context_pack_service=ContextPackService.from_settings(),
            search_top_k=search_top_k,
            context_top_k=context_top_k,
            context_budget_tokens=context_budget_tokens,
        )

    def evaluate(
        self,
        queries: Sequence[M3EvalQuery],
        *,
        generated_at: str | None = None,
    ) -> M3EvalReport:
        results = [self._evaluate_query(row) for row in queries]
        return M3EvalReport(
            generated_at=generated_at or datetime.now(UTC).isoformat(),
            search_top_k=self.search_top_k,
            context_top_k=self.context_top_k,
            context_budget_tokens=self.context_budget_tokens,
            summary=_summarize(results),
            results=results,
        )

    def _evaluate_query(self, row: M3EvalQuery) -> M3EvalQueryResult:
        search_response = self.search_service.search_knowledge(query=row.query, top_k=self.search_top_k)
        context_pack = self.context_pack_service.get_context_pack(
            query=row.query,
            top_k=self.context_top_k,
            budget_tokens=self.context_budget_tokens,
        )
        return M3EvalQueryResult(
            query=row.query,
            query_type=row.query_type,
            expected_canonical_keys=row.expected_canonical_keys,
            search=_measure_search(search_response.results, row),
            context_pack=_measure_context_pack(context_pack, row),
            notes=row.notes,
        )


class M3ComparisonEvaluator:
    def __init__(
        self,
        *,
        simple_search_service: SearchServiceLike,
        planned_search_service: PlannedSearchServiceLike,
        context_pack_service: ContextPackServiceLike,
        search_top_k: int = 10,
        context_top_k: int = 10,
        context_budget_tokens: int | None = None,
    ) -> None:
        if search_top_k < 10:
            raise M3EvalInputError("search_top_k must be at least 10 so top_10_hit is meaningful")
        if context_top_k < 1:
            raise M3EvalInputError("context_top_k must be at least 1")
        if context_budget_tokens is not None and context_budget_tokens < 1:
            raise M3EvalInputError("context_budget_tokens must be at least 1 when set")
        self.simple_search_service = simple_search_service
        self.planned_search_service = planned_search_service
        self.context_pack_service = context_pack_service
        self.search_top_k = search_top_k
        self.context_top_k = context_top_k
        self.context_budget_tokens = context_budget_tokens

    @classmethod
    def from_settings(
        cls,
        *,
        search_top_k: int = 10,
        context_top_k: int = 10,
        context_budget_tokens: int | None = None,
    ) -> "M3ComparisonEvaluator":
        from pkcs.context_pack import ContextPackService
        from pkcs.search import PlannedSearchService, SearchService

        return cls(
            simple_search_service=SearchService.from_settings(),
            planned_search_service=PlannedSearchService.from_settings(),
            context_pack_service=ContextPackService.from_settings(),
            search_top_k=search_top_k,
            context_top_k=context_top_k,
            context_budget_tokens=context_budget_tokens,
        )

    def evaluate(
        self,
        queries: Sequence[M3EvalQuery],
        *,
        generated_at: str | None = None,
        suite: str = M3C_COMPARISON_SUITE,
    ) -> M3ComparisonReport:
        results = [self._evaluate_query(row) for row in queries]
        return M3ComparisonReport(
            suite=suite,
            generated_at=generated_at or datetime.now(UTC).isoformat(),
            search_top_k=self.search_top_k,
            context_top_k=self.context_top_k,
            context_budget_tokens=self.context_budget_tokens,
            summary=_summarize_comparison(results),
            pass_diagnostics=_summarize_comparison_passes(results),
            failure_classes=_summarize_failure_classes(results),
            results=results,
        )

    def _evaluate_query(self, row: M3EvalQuery) -> M3ComparisonQueryResult:
        simple_response = self.simple_search_service.search_knowledge(
            query=row.query,
            top_k=self.search_top_k,
        )
        planned_response = self.planned_search_service.search_knowledge(
            query=row.query,
            top_k=self.search_top_k,
        )
        context_pack = self.context_pack_service.get_context_pack(
            query=row.query,
            top_k=self.context_top_k,
            budget_tokens=self.context_budget_tokens,
        )
        simple_quality = _measure_search(simple_response.results, row)
        planned_quality = _measure_search(planned_response.results, row)
        context_quality = _measure_context_pack(context_pack, row)
        pass_diagnostics = _measure_pass_diagnostics(planned_response, row)
        return M3ComparisonQueryResult(
            query=row.query,
            query_type=row.query_type,
            suite=row.suite,
            language=row.language,
            query_style=row.query_style,
            expected_intent=row.expected_intent,
            expected_canonical_keys=row.expected_canonical_keys,
            diagnostic_tags=row.diagnostic_tags,
            simple_search=simple_quality,
            planned_search=planned_quality,
            planned_context_pack=context_quality,
            pass_diagnostics=pass_diagnostics,
            planned_result_distribution=_measure_result_distribution(planned_response.results, row),
            failure_classes=_classify_comparison_failure(
                row=row,
                planned_search=planned_quality,
                context_pack=context_quality,
                pass_diagnostics=pass_diagnostics,
            ),
            notes=row.notes,
        )


def write_m3_comparison_report(report: M3ComparisonReport, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report.to_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return output_path


def _measure_search(results: list[SearchResult], row: M3EvalQuery) -> M3SearchQuality:
    result_keys = [result.canonical_key for result in results]
    expected_source_rank = _first_expected_rank(result_keys, row.expected_canonical_keys)
    return M3SearchQuality(
        result_count=len(results),
        expected_source_rank=expected_source_rank,
        top_1_hit=expected_source_rank == 1,
        top_5_hit=expected_source_rank is not None and expected_source_rank <= 5,
        top_10_hit=expected_source_rank is not None and expected_source_rank <= 10,
        must_not_violations=_ordered_intersection(result_keys, row.must_not_canonical_keys),
        empty_result=len(results) == 0,
    )


def _measure_context_pack(context_pack: ContextPackResponse, row: M3EvalQuery) -> M3ContextPackQuality:
    evidence_text = _context_pack_evidence_text(context_pack)
    terms_found = [
        term for term in row.expected_evidence_terms if term.casefold() in evidence_text
    ]
    terms_missing = [term for term in row.expected_evidence_terms if term not in terms_found]
    evidence_keys = [item.canonical_key for item in context_pack.evidence]
    source_keys = [source.canonical_key for source in context_pack.sources]
    must_not_sources = _ordered_intersection([*evidence_keys, *source_keys], row.must_not_canonical_keys)
    all_terms_found = len(terms_missing) == 0
    evidence_traceable = all(_is_traceable(item) for item in context_pack.evidence)
    return M3ContextPackQuality(
        evidence_count=len(context_pack.evidence),
        sources_count=len(context_pack.sources),
        expected_evidence_terms_found=terms_found,
        expected_evidence_terms_missing=terms_missing,
        all_expected_evidence_terms_found=all_terms_found,
        all_evidence_traceable=evidence_traceable,
        must_not_sources_in_pack=must_not_sources,
        followup_read_suggestions_count=len(context_pack.followup_read_suggestions),
        caveats_present="## Conflicts / Caveats" in context_pack.context_pack_markdown,
        support_satisfied=(not row.support_required) or (len(context_pack.evidence) > 0 and all_terms_found),
    )


def _context_pack_evidence_text(context_pack: ContextPackResponse) -> str:
    parts = [context_pack.context_pack_markdown]
    for item in context_pack.evidence:
        parts.extend([item.title, item.snippet, item.content])
    return "\n".join(parts).casefold()


def _is_traceable(evidence: ContextPackEvidence) -> bool:
    required_refs = [
        evidence.chunk_id,
        evidence.source_id,
        evidence.version_id,
        evidence.canonical_key,
        evidence.locator,
    ]
    return (
        all(str(value).strip() for value in required_refs)
        and evidence.line_start >= 1
        and evidence.line_end >= evidence.line_start
    )


def _first_expected_rank(result_keys: list[str], expected_keys: list[str]) -> int | None:
    expected = set(expected_keys)
    for index, key in enumerate(result_keys, start=1):
        if key in expected:
            return index
    return None


def _ordered_intersection(keys: list[str], expected: list[str]) -> list[str]:
    expected_set = set(expected)
    seen: set[str] = set()
    violations: list[str] = []
    for key in keys:
        if key in expected_set and key not in seen:
            violations.append(key)
            seen.add(key)
    return violations


def _summarize(results: list[M3EvalQueryResult]) -> M3EvalSummary:
    total = len(results)
    return M3EvalSummary(
        query_count=total,
        top_1_hit_rate=_rate(sum(1 for item in results if item.search.top_1_hit), total),
        top_5_hit_rate=_rate(sum(1 for item in results if item.search.top_5_hit), total),
        top_10_hit_rate=_rate(sum(1 for item in results if item.search.top_10_hit), total),
        context_support_rate=_rate(sum(1 for item in results if item.context_pack.support_satisfied), total),
        traceability_rate=_rate(sum(1 for item in results if item.context_pack.all_evidence_traceable), total),
        caveats_rate=_rate(sum(1 for item in results if item.context_pack.caveats_present), total),
        search_must_not_violation_count=sum(len(item.search.must_not_violations) for item in results),
        context_must_not_violation_count=sum(
            len(item.context_pack.must_not_sources_in_pack) for item in results
        ),
        empty_result_count=sum(1 for item in results if item.search.empty_result),
    )


def _measure_pass_diagnostics(planned_response: Any, row: M3EvalQuery) -> M3ComparisonPassDiagnostics:
    pass_runs = getattr(planned_response, "pass_runs", [])
    pass_result_counts = {item.name: item.result_count for item in pass_runs}
    pass_error_types = {
        item.name: item.error_type
        for item in pass_runs
        if item.error_type is not None
    }
    observed_pass_names = set(pass_result_counts)
    return M3ComparisonPassDiagnostics(
        pass_result_counts=pass_result_counts,
        pass_error_types=pass_error_types,
        expected_source_pass_names=_expected_source_pass_names(planned_response.results, row),
        missing_expected_pass_names=[
            name for name in row.expected_pass_names if name not in observed_pass_names
        ],
    )


def _expected_source_pass_names(results: list[SearchResult], row: M3EvalQuery) -> list[str]:
    expected_keys = set(row.expected_canonical_keys)
    pass_names: list[str] = []
    seen: set[str] = set()
    for result in results:
        if result.canonical_key not in expected_keys:
            continue
        planned_metadata = result.metadata.get("planned_retrieval")
        if not isinstance(planned_metadata, dict):
            continue
        pass_hits = planned_metadata.get("pass_hits")
        if not isinstance(pass_hits, list):
            continue
        for hit in pass_hits:
            if not isinstance(hit, dict):
                continue
            pass_name = hit.get("pass_name")
            if not isinstance(pass_name, str) or pass_name in seen:
                continue
            seen.add(pass_name)
            pass_names.append(pass_name)
    return pass_names


def _measure_result_distribution(results: list[SearchResult], row: M3EvalQuery) -> M3ResultDistribution:
    result_keys = [result.canonical_key for result in results]
    result_count = len(result_keys)
    counts = Counter(result_keys)
    dominant_canonical_key: str | None = None
    dominant_count = 0
    if counts:
        dominant_canonical_key, dominant_count = counts.most_common(1)[0]
    expected_keys = set(row.expected_canonical_keys)
    unexpected_count = sum(1 for key in result_keys if key not in expected_keys)
    return M3ResultDistribution(
        result_count=result_count,
        distinct_canonical_key_count=len(counts),
        dominant_canonical_key=dominant_canonical_key,
        dominant_canonical_key_count=dominant_count,
        dominant_canonical_key_share=_rate(dominant_count, result_count),
        unexpected_result_count=unexpected_count,
        unexpected_result_ratio=_rate(unexpected_count, result_count),
    )


def _classify_comparison_failure(
    *,
    row: M3EvalQuery,
    planned_search: M3SearchQuality,
    context_pack: M3ContextPackQuality,
    pass_diagnostics: M3ComparisonPassDiagnostics,
) -> list[str]:
    if planned_search.top_10_hit:
        if not context_pack.support_satisfied:
            return [M3_FAILURE_EVIDENCE_SELECTION_GAP]
        return []

    failure_classes: list[str] = []
    if (
        PASS_SOURCE_ALIAS in row.expected_pass_names
        and pass_diagnostics.pass_result_counts.get(PASS_SOURCE_ALIAS, 0) == 0
    ):
        failure_classes.append(M3_FAILURE_MISSING_ALIAS)
    if (
        PASS_GLOSSARY_EXPANSION in row.expected_pass_names
        and pass_diagnostics.pass_result_counts.get(PASS_GLOSSARY_EXPANSION, 0) == 0
    ):
        failure_classes.append(M3_FAILURE_MISSING_GLOSSARY)
    if not failure_classes:
        failure_classes.append(M3_FAILURE_SEMANTIC_GAP)
    return failure_classes


def _summarize_comparison(results: list[M3ComparisonQueryResult]) -> M3ComparisonSummary:
    total = len(results)
    simple_hit_rate = _rate(sum(1 for item in results if item.simple_search.top_10_hit), total)
    planned_hit_rate = _rate(sum(1 for item in results if item.planned_search.top_10_hit), total)
    locked_results = [
        item for item in results if item.suite == M3_EVAL_SUITE_LOCKED_REGRESSION
    ]
    locked_passes = [
        item
        for item in locked_results
        if item.planned_search.top_10_hit and item.planned_context_pack.support_satisfied
    ]
    return M3ComparisonSummary(
        query_count=total,
        simple_top_10_hit_rate=simple_hit_rate,
        planned_top_10_hit_rate=planned_hit_rate,
        simple_to_planned_top_10_delta=planned_hit_rate - simple_hit_rate,
        planned_context_support_rate=_rate(
            sum(1 for item in results if item.planned_context_pack.support_satisfied),
            total,
        ),
        locked_regression_query_count=len(locked_results),
        locked_regression_pass_rate=_rate(len(locked_passes), len(locked_results)),
        planned_empty_result_count=sum(1 for item in results if item.planned_search.empty_result),
        context_support_miss_count=sum(
            1 for item in results if not item.planned_context_pack.support_satisfied
        ),
        noisy_result_query_count=sum(
            1
            for item in results
            if item.planned_result_distribution.result_count > 0
            and item.planned_result_distribution.unexpected_result_ratio >= NOISY_RESULT_RATIO_THRESHOLD
        ),
        source_concentration_query_count=sum(
            1
            for item in results
            if item.planned_result_distribution.result_count >= SOURCE_CONCENTRATION_MIN_RESULTS
            and item.planned_result_distribution.dominant_canonical_key_share
            >= SOURCE_CONCENTRATION_SHARE_THRESHOLD
        ),
    )


def _summarize_comparison_passes(results: list[M3ComparisonQueryResult]) -> M3ComparisonPassSummary:
    result_counts: Counter[str] = Counter()
    error_counts: Counter[str] = Counter()
    for result in results:
        result_counts.update(result.pass_diagnostics.pass_result_counts)
        error_counts.update(result.pass_diagnostics.pass_error_types.keys())
    return M3ComparisonPassSummary(
        original_hit_count=_pass_hit_count(results, PASS_ORIGINAL),
        ascii_entity_hit_count=_pass_hit_count(results, PASS_ASCII_ENTITY),
        glossary_hit_count=_pass_hit_count(results, PASS_GLOSSARY_EXPANSION),
        source_alias_hit_count=_pass_hit_count(results, PASS_SOURCE_ALIAS),
        combined_hit_count=_pass_hit_count(results, PASS_COMBINED),
        pass_result_counts=dict(sorted(result_counts.items())),
        pass_error_counts=dict(sorted(error_counts.items())),
    )


def _pass_hit_count(results: list[M3ComparisonQueryResult], pass_name: str) -> int:
    return sum(1 for item in results if pass_name in item.pass_diagnostics.expected_source_pass_names)


def _summarize_failure_classes(results: list[M3ComparisonQueryResult]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for result in results:
        counts.update(result.failure_classes)
    return {name: counts[name] for name in sorted(M3_FAILURE_CLASSES | set(counts))}


def _rate(count: int, total: int) -> float:
    if total == 0:
        return 0.0
    return count / total
