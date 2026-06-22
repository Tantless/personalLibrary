import json
from pathlib import Path

import pytest

from pkcs.context_pack.models import (
    ContextPackEvidence,
    ContextPackResponse,
    ContextPackSource,
    FollowupReadSuggestion,
)
from pkcs.eval import (
    M3_EVAL_SUITE_DIAGNOSTIC,
    M3_EVAL_SUITE_LOCKED_REGRESSION,
    M3_FAILURE_EVIDENCE_SELECTION_GAP,
    M3_FAILURE_MISSING_ALIAS,
    M3_FAILURE_MISSING_GLOSSARY,
    M3BaselineEvaluator,
    M3ComparisonEvaluator,
    M3EvalInputError,
    M3EvalQuery,
    load_m3_eval_queries,
    write_m3_comparison_report,
)
from pkcs.search import (
    PlannedSearchPassRun,
    PlannedSearchResponse,
    RetrievalPass,
    RetrievalPlan,
)
from pkcs.search.models import SearchCitation, SearchResponse, SearchResult
from pkcs.search.planning import (
    PASS_COMBINED,
    PASS_GLOSSARY_EXPANSION,
    PASS_ORIGINAL,
    PASS_SOURCE_ALIAS,
)


M3_EVAL_FIXTURE = Path("tests/fixtures/m3_eval_queries.jsonl")


def test_m3_eval_query_fixture_has_required_shape() -> None:
    rows = load_m3_eval_queries(M3_EVAL_FIXTURE)

    assert len(rows) >= 6
    assert {row.query_type for row in rows} >= {
        "official_doc_lookup",
        "safety_report_lookup",
        "broad_project_lookup",
        "recent_technical_lookup",
    }
    assert all(row.expected_canonical_keys for row in rows)
    assert all(row.expected_evidence_terms for row in rows)
    assert {row.suite for row in rows} == {M3_EVAL_SUITE_LOCKED_REGRESSION}
    assert all(row.expected_intent == row.query_type for row in rows)
    assert all(row.expected_pass_names == [] for row in rows)
    assert all(row.diagnostic_tags == [] for row in rows)


def test_m3_eval_query_loader_rejects_invalid_rows(tmp_path) -> None:
    path = tmp_path / "bad.jsonl"
    path.write_text(json.dumps({"query": "missing fields"}) + "\n", encoding="utf-8")

    with pytest.raises(M3EvalInputError, match="query_type"):
        load_m3_eval_queries(path)


def test_m3_eval_query_loader_accepts_v2_diagnostic_metadata(tmp_path) -> None:
    path = tmp_path / "v2.jsonl"
    payload = {
        "query": "Agents SDK 如何处理工具调用？",
        "query_type": "official_doc_lookup",
        "suite": M3_EVAL_SUITE_DIAGNOSTIC,
        "language": "mixed",
        "query_style": "natural_question",
        "expected_intent": "official_doc_lookup",
        "expected_pass_names": [
            "ascii_entity",
            "glossary_expansion",
            "source_alias",
            "combined",
        ],
        "diagnostic_tags": ["mixed_language", "technical_term"],
        "expected_canonical_keys": ["m3-corpus:ai:openai-agents-python-tools"],
        "expected_evidence_terms": ["tools", "function tools"],
        "must_not_canonical_keys": [],
        "support_required": True,
        "notes": "v2 row",
    }
    path.write_text(json.dumps(payload, ensure_ascii=False) + "\n", encoding="utf-8")

    rows = load_m3_eval_queries(path)
    row = rows[0]

    assert row.suite == M3_EVAL_SUITE_DIAGNOSTIC
    assert row.language == "mixed"
    assert row.query_style == "natural_question"
    assert row.expected_intent == "official_doc_lookup"
    assert row.expected_pass_names == [
        "ascii_entity",
        "glossary_expansion",
        "source_alias",
        "combined",
    ]
    assert row.diagnostic_tags == ["mixed_language", "technical_term"]
    assert row.to_dict()["suite"] == M3_EVAL_SUITE_DIAGNOSTIC


def test_m3_eval_query_loader_rejects_invalid_v2_metadata(tmp_path) -> None:
    path = tmp_path / "bad_v2.jsonl"
    payload = {
        "query": "Agents SDK 如何处理工具调用？",
        "query_type": "official_doc_lookup",
        "suite": "unknown_suite",
        "expected_canonical_keys": ["m3-corpus:ai:openai-agents-python-tools"],
        "expected_evidence_terms": ["tools", "function tools"],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False) + "\n", encoding="utf-8")

    with pytest.raises(M3EvalInputError, match="suite must be one of"):
        load_m3_eval_queries(path)


def test_m3_eval_query_loader_rejects_invalid_expected_pass_names(tmp_path) -> None:
    path = tmp_path / "bad_passes.jsonl"
    payload = {
        "query": "Agents SDK 如何处理工具调用？",
        "query_type": "official_doc_lookup",
        "expected_canonical_keys": ["m3-corpus:ai:openai-agents-python-tools"],
        "expected_evidence_terms": ["tools", "function tools"],
        "expected_pass_names": ["original", ""],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False) + "\n", encoding="utf-8")

    with pytest.raises(M3EvalInputError, match=r"expected_pass_names\[2\]"):
        load_m3_eval_queries(path)


def test_m3_eval_query_defaults_expected_intent_when_constructed_directly() -> None:
    row = M3EvalQuery(
        query="Agents SDK 如何处理工具调用？",
        query_type="official_doc_lookup",
        expected_canonical_keys=["m3-corpus:ai:openai-agents-python-tools"],
        expected_evidence_terms=["tools"],
    )

    assert row.expected_intent == "official_doc_lookup"


def test_m3_baseline_evaluator_reports_search_and_context_metrics() -> None:
    row = M3EvalQuery(
        query="How do guardrails keep evidence traceable?",
        query_type="official_doc_lookup",
        expected_canonical_keys=["m3-corpus:expected"],
        expected_evidence_terms=["guardrails", "traceable"],
        must_not_canonical_keys=["m3-corpus:wrong"],
        support_required=True,
        notes="fake row",
    )
    evaluator = M3BaselineEvaluator(
        search_service=FakeSearchService(),
        context_pack_service=FakeContextPackService(),
        search_top_k=10,
        context_top_k=5,
        context_budget_tokens=500,
    )

    report = evaluator.evaluate([row], generated_at="2026-06-22T00:00:00+00:00")
    body = report.to_dict()

    assert body["generated_at"] == "2026-06-22T00:00:00+00:00"
    assert body["summary"]["query_count"] == 1
    assert body["summary"]["top_1_hit_rate"] == 0
    assert body["summary"]["top_5_hit_rate"] == 1
    assert body["summary"]["top_10_hit_rate"] == 1
    assert body["summary"]["context_support_rate"] == 1
    assert body["summary"]["traceability_rate"] == 1
    assert body["summary"]["caveats_rate"] == 1
    assert body["summary"]["search_must_not_violation_count"] == 1
    assert body["summary"]["context_must_not_violation_count"] == 0

    result = body["results"][0]
    assert result["search"]["expected_source_rank"] == 2
    assert result["search"]["must_not_violations"] == ["m3-corpus:wrong"]
    assert result["context_pack"]["expected_evidence_terms_found"] == ["guardrails", "traceable"]
    assert result["context_pack"]["followup_read_suggestions_count"] == 1
    assert result["context_pack"]["support_satisfied"] is True


def test_m3_baseline_evaluator_marks_unsatisfied_support() -> None:
    row = M3EvalQuery(
        query="No supported evidence",
        query_type="broad_project_lookup",
        expected_canonical_keys=["m3-corpus:missing"],
        expected_evidence_terms=["missing term"],
        support_required=True,
    )
    evaluator = M3BaselineEvaluator(
        search_service=EmptySearchService(),
        context_pack_service=EmptyContextPackService(),
    )

    report = evaluator.evaluate([row], generated_at="2026-06-22T00:00:00+00:00")
    result = report.to_dict()["results"][0]

    assert result["search"]["expected_source_rank"] is None
    assert result["search"]["empty_result"] is True
    assert result["context_pack"]["expected_evidence_terms_missing"] == ["missing term"]
    assert result["context_pack"]["support_satisfied"] is False
    assert report.summary.empty_result_count == 1


def test_m3_comparison_evaluator_reports_planned_delta_passes_and_failures() -> None:
    recovered = M3EvalQuery(
        query="recover mixed language",
        query_type="official_doc_lookup",
        expected_canonical_keys=["m3-corpus:expected"],
        expected_evidence_terms=["tools"],
        expected_pass_names=[PASS_GLOSSARY_EXPANSION, PASS_SOURCE_ALIAS],
    )
    missing = M3EvalQuery(
        query="missing mixed language",
        query_type="official_doc_lookup",
        suite=M3_EVAL_SUITE_DIAGNOSTIC,
        expected_canonical_keys=["m3-corpus:missing"],
        expected_evidence_terms=["missing"],
        expected_pass_names=[PASS_GLOSSARY_EXPANSION, PASS_SOURCE_ALIAS],
    )
    evaluator = M3ComparisonEvaluator(
        simple_search_service=MappingSearchService(
            {
                recovered.query: [],
                missing.query: [],
            }
        ),
        planned_search_service=MappingPlannedSearchService(
            {
                recovered.query: planned_response(
                    recovered.query,
                    results=[
                        search_result_with_pass_hits(
                            "planned-hit",
                            "m3-corpus:expected",
                            [PASS_GLOSSARY_EXPANSION, PASS_SOURCE_ALIAS, PASS_COMBINED],
                        ),
                        search_result("planned-noise-1", "m3-corpus:noise"),
                        search_result("planned-noise-2", "m3-corpus:noise"),
                        search_result("planned-noise-3", "m3-corpus:noise"),
                        search_result("planned-noise-4", "m3-corpus:noise"),
                    ],
                    pass_runs=[
                        PlannedSearchPassRun(name=PASS_ORIGINAL, query=recovered.query, result_count=0),
                        PlannedSearchPassRun(
                            name=PASS_GLOSSARY_EXPANSION,
                            query="tools",
                            result_count=1,
                        ),
                        PlannedSearchPassRun(
                            name=PASS_SOURCE_ALIAS,
                            query="OpenAI Agents SDK",
                            result_count=1,
                        ),
                        PlannedSearchPassRun(name=PASS_COMBINED, query="tools OR sdk", result_count=1),
                    ],
                ),
                missing.query: planned_response(
                    missing.query,
                    results=[],
                    pass_runs=[
                        PlannedSearchPassRun(
                            name=PASS_ORIGINAL,
                            query=missing.query,
                            result_count=0,
                            error_type="RuntimeError",
                        ),
                        PlannedSearchPassRun(
                            name=PASS_GLOSSARY_EXPANSION,
                            query="missing",
                            result_count=0,
                        ),
                        PlannedSearchPassRun(
                            name=PASS_SOURCE_ALIAS,
                            query="Missing Source",
                            result_count=0,
                        ),
                    ],
                ),
            }
        ),
        context_pack_service=MappingContextPackService(
            {
                recovered.query: context_pack_response(
                    query=recovered.query,
                    canonical_key="m3-corpus:expected",
                    content="Function tools provide supported evidence.",
                ),
                missing.query: empty_context_pack_response(missing.query),
            }
        ),
        search_top_k=10,
        context_top_k=5,
    )

    report = evaluator.evaluate(
        [recovered, missing],
        generated_at="2026-06-22T00:00:00+00:00",
    )
    body = report.to_dict()

    assert body["suite"] == "m3c"
    assert body["summary"]["query_count"] == 2
    assert body["summary"]["simple_top_10_hit_rate"] == 0
    assert body["summary"]["planned_top_10_hit_rate"] == 0.5
    assert body["summary"]["simple_to_planned_top_10_delta"] == 0.5
    assert body["summary"]["planned_context_support_rate"] == 0.5
    assert body["summary"]["locked_regression_query_count"] == 1
    assert body["summary"]["locked_regression_pass_rate"] == 1
    assert body["summary"]["planned_empty_result_count"] == 1
    assert body["summary"]["context_support_miss_count"] == 1
    assert body["summary"]["noisy_result_query_count"] == 1
    assert body["summary"]["source_concentration_query_count"] == 1
    assert body["pass_diagnostics"]["glossary_hit_count"] == 1
    assert body["pass_diagnostics"]["source_alias_hit_count"] == 1
    assert body["pass_diagnostics"]["pass_error_counts"][PASS_ORIGINAL] == 1
    assert body["failure_classes"][M3_FAILURE_MISSING_ALIAS] == 1
    assert body["failure_classes"][M3_FAILURE_MISSING_GLOSSARY] == 1

    first = body["results"][0]
    assert first["simple_search"]["empty_result"] is True
    assert first["planned_search"]["top_10_hit"] is True
    assert first["planned_result_distribution"]["result_count"] == 5
    assert first["planned_result_distribution"]["unexpected_result_ratio"] == 0.8
    assert first["pass_diagnostics"]["expected_source_pass_names"] == [
        PASS_GLOSSARY_EXPANSION,
        PASS_SOURCE_ALIAS,
        PASS_COMBINED,
    ]
    assert first["failure_classes"] == []

    second = body["results"][1]
    assert second["planned_search"]["empty_result"] is True
    assert second["pass_diagnostics"]["pass_error_types"] == {PASS_ORIGINAL: "RuntimeError"}
    assert second["failure_classes"] == [
        M3_FAILURE_MISSING_ALIAS,
        M3_FAILURE_MISSING_GLOSSARY,
    ]


def test_m3_comparison_evaluator_marks_evidence_selection_gap() -> None:
    row = M3EvalQuery(
        query="planned hit but unsupported context",
        query_type="official_doc_lookup",
        expected_canonical_keys=["m3-corpus:expected"],
        expected_evidence_terms=["absent term"],
    )
    evaluator = M3ComparisonEvaluator(
        simple_search_service=MappingSearchService({row.query: []}),
        planned_search_service=MappingPlannedSearchService(
            {
                row.query: planned_response(
                    row.query,
                    results=[
                        search_result_with_pass_hits(
                            "planned-hit",
                            "m3-corpus:expected",
                            [PASS_ORIGINAL],
                        )
                    ],
                    pass_runs=[
                        PlannedSearchPassRun(name=PASS_ORIGINAL, query=row.query, result_count=1)
                    ],
                )
            }
        ),
        context_pack_service=MappingContextPackService(
            {
                row.query: empty_context_pack_response(row.query),
            }
        ),
    )

    report = evaluator.evaluate([row], generated_at="2026-06-22T00:00:00+00:00")
    body = report.to_dict()

    assert body["failure_classes"][M3_FAILURE_EVIDENCE_SELECTION_GAP] == 1
    assert body["results"][0]["failure_classes"] == [M3_FAILURE_EVIDENCE_SELECTION_GAP]
    assert body["results"][0]["planned_search"]["top_10_hit"] is True
    assert body["results"][0]["planned_context_pack"]["support_satisfied"] is False


def test_write_m3_comparison_report_writes_json(tmp_path) -> None:
    row = M3EvalQuery(
        query="write report",
        query_type="official_doc_lookup",
        expected_canonical_keys=["m3-corpus:expected"],
        expected_evidence_terms=["tools"],
    )
    evaluator = M3ComparisonEvaluator(
        simple_search_service=MappingSearchService({row.query: []}),
        planned_search_service=MappingPlannedSearchService(
            {
                row.query: planned_response(
                    row.query,
                    results=[
                        search_result_with_pass_hits(
                            "planned-hit",
                            "m3-corpus:expected",
                            [PASS_ORIGINAL],
                        )
                    ],
                    pass_runs=[
                        PlannedSearchPassRun(name=PASS_ORIGINAL, query=row.query, result_count=1)
                    ],
                )
            }
        ),
        context_pack_service=MappingContextPackService(
            {
                row.query: context_pack_response(
                    query=row.query,
                    canonical_key="m3-corpus:expected",
                    content="tools evidence",
                )
            }
        ),
    )
    report = evaluator.evaluate([row], generated_at="2026-06-22T00:00:00+00:00")

    output_path = write_m3_comparison_report(report, tmp_path / "eval-runs" / "m3c.json")
    body = json.loads(output_path.read_text(encoding="utf-8"))

    assert output_path.exists()
    assert body["suite"] == "m3c"
    assert body["summary"]["planned_top_10_hit_rate"] == 1


class MappingSearchService:
    def __init__(self, results_by_query):
        self.results_by_query = results_by_query

    def search_knowledge(self, *, query, knowledge_type=None, canonical_key=None, top_k=None):
        return SearchResponse(
            query=query,
            knowledge_type=knowledge_type,
            canonical_key=canonical_key,
            top_k=top_k or 10,
            results=self.results_by_query.get(query, []),
        )


class MappingPlannedSearchService:
    def __init__(self, responses_by_query):
        self.responses_by_query = responses_by_query

    def search_knowledge(self, *, query, knowledge_type=None, canonical_key=None, top_k=None):
        return self.responses_by_query[query]


class MappingContextPackService:
    def __init__(self, responses_by_query):
        self.responses_by_query = responses_by_query

    def get_context_pack(self, *, query, knowledge_type=None, canonical_key=None, top_k=None, budget_tokens=None):
        return self.responses_by_query[query]


def planned_response(query: str, *, results: list[SearchResult], pass_runs: list[PlannedSearchPassRun]):
    return PlannedSearchResponse(
        query=query,
        knowledge_type=None,
        canonical_key=None,
        top_k=10,
        retrieval_plan=RetrievalPlan(
            query=query,
            intent="official_doc_lookup",
            passes=[
                RetrievalPass(name=item.name, query=item.query)
                for item in pass_runs
            ],
        ),
        pass_runs=pass_runs,
        results=results,
    )


def search_result_with_pass_hits(
    result_id: str,
    canonical_key: str,
    pass_names: list[str],
) -> SearchResult:
    return search_result(
        result_id,
        canonical_key,
        metadata={
            "planned_retrieval": {
                "pass_hits": [
                    {
                        "pass_name": pass_name,
                        "query": pass_name,
                        "rank": index,
                        "score": 1.0,
                        "weight": 1.0,
                    }
                    for index, pass_name in enumerate(pass_names, start=1)
                ]
            }
        },
    )


def context_pack_response(*, query: str, canonical_key: str, content: str) -> ContextPackResponse:
    return ContextPackResponse(
        query=query,
        retrieval_plan={"provider": "fake", "pass_runs": []},
        sources=[
            ContextPackSource(
                source_id="source-1",
                version_id="version-1",
                canonical_key=canonical_key,
                title="Expected",
                source_format="md",
                normalized_format="md",
                knowledge_type="document",
                evidence_count=1,
            )
        ],
        evidence=[
            ContextPackEvidence(
                evidence_id="evidence-1",
                chunk_id="chunk-1",
                source_id="source-1",
                version_id="version-1",
                canonical_key=canonical_key,
                title="Expected",
                source_format="md",
                normalized_format="md",
                knowledge_type="document",
                locator="line 1-2",
                line_start=1,
                line_end=2,
                score=1.0,
                snippet=content,
                content=content,
                metadata={},
            )
        ],
        followup_read_suggestions=[
            FollowupReadSuggestion(
                chunk_id="chunk-1",
                source_id="source-1",
                version_id="version-1",
                locator="line 1-2",
                context_lines=2,
                reason="Read surrounding context.",
            )
        ],
        context_pack_markdown="# Context Pack\n\n## Conflicts / Caveats\n\nMVP caveat.",
    )


def empty_context_pack_response(query: str) -> ContextPackResponse:
    return ContextPackResponse(
        query=query,
        retrieval_plan={"provider": "fake", "pass_runs": []},
        sources=[],
        evidence=[],
        followup_read_suggestions=[],
        context_pack_markdown="# Context Pack\n\n## Conflicts / Caveats\n\nNo sources matched.",
    )


class FakeSearchService:
    def search_knowledge(self, *, query, knowledge_type=None, canonical_key=None, top_k=None):
        return SearchResponse(
            query=query,
            knowledge_type=knowledge_type,
            canonical_key=canonical_key,
            top_k=top_k or 10,
            results=[
                search_result("result-1", "m3-corpus:other"),
                search_result("result-2", "m3-corpus:expected"),
                search_result("result-3", "m3-corpus:wrong"),
            ],
        )


class EmptySearchService:
    def search_knowledge(self, *, query, knowledge_type=None, canonical_key=None, top_k=None):
        return SearchResponse(
            query=query,
            knowledge_type=knowledge_type,
            canonical_key=canonical_key,
            top_k=top_k or 10,
            results=[],
        )


class FakeContextPackService:
    def get_context_pack(self, *, query, knowledge_type=None, canonical_key=None, top_k=None, budget_tokens=None):
        return ContextPackResponse(
            query=query,
            retrieval_plan={"provider": "fake"},
            sources=[
                ContextPackSource(
                    source_id="source-1",
                    version_id="version-1",
                    canonical_key="m3-corpus:expected",
                    title="Expected",
                    source_format="md",
                    normalized_format="md",
                    knowledge_type="document",
                    evidence_count=1,
                )
            ],
            evidence=[
                ContextPackEvidence(
                    evidence_id="evidence-1",
                    chunk_id="chunk-1",
                    source_id="source-1",
                    version_id="version-1",
                    canonical_key="m3-corpus:expected",
                    title="Expected",
                    source_format="md",
                    normalized_format="md",
                    knowledge_type="document",
                    locator="line 1-2",
                    line_start=1,
                    line_end=2,
                    score=1.0,
                    snippet="Guardrails keep the source traceable.",
                    content="Guardrails keep evidence traceable through source references.",
                    metadata={},
                )
            ],
            followup_read_suggestions=[
                FollowupReadSuggestion(
                    chunk_id="chunk-1",
                    source_id="source-1",
                    version_id="version-1",
                    locator="line 1-2",
                    context_lines=2,
                    reason="Read surrounding context.",
                )
            ],
            context_pack_markdown="# Context Pack\n\n## Conflicts / Caveats\n\nMVP caveat.",
        )


class EmptyContextPackService:
    def get_context_pack(self, *, query, knowledge_type=None, canonical_key=None, top_k=None, budget_tokens=None):
        return ContextPackResponse(
            query=query,
            retrieval_plan={"provider": "fake"},
            sources=[],
            evidence=[],
            followup_read_suggestions=[],
            context_pack_markdown="# Context Pack\n\n## Conflicts / Caveats\n\nNo sources matched.",
        )


def search_result(
    result_id: str,
    canonical_key: str,
    *,
    metadata: dict | None = None,
) -> SearchResult:
    return SearchResult(
        result_id=result_id,
        chunk_id=f"{result_id}-chunk",
        source_id=f"{result_id}-source",
        version_id=f"{result_id}-version",
        canonical_key=canonical_key,
        title=canonical_key,
        source_format="md",
        normalized_format="md",
        knowledge_type="document",
        snippet=canonical_key,
        score=1.0,
        citation=SearchCitation(locator="line 1-2", line_start=1, line_end=2),
        metadata=metadata or {},
    )
