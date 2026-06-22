import json
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from pkcs.context_pack.models import ContextPackEvidence, ContextPackResponse
from pkcs.eval.models import (
    M3ContextPackQuality,
    M3EvalInputError,
    M3EvalQuery,
    M3EvalQueryResult,
    M3EvalReport,
    M3EvalSummary,
    M3SearchQuality,
)
from pkcs.search.models import SearchResponse, SearchResult


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


def _rate(count: int, total: int) -> float:
    if total == 0:
        return 0.0
    return count / total
