import json
from pathlib import Path

import pytest

from pkcs.context_pack.models import (
    ContextPackEvidence,
    ContextPackResponse,
    ContextPackSource,
    FollowupReadSuggestion,
)
from pkcs.eval import M3BaselineEvaluator, M3EvalInputError, M3EvalQuery, load_m3_eval_queries
from pkcs.search.models import SearchCitation, SearchResponse, SearchResult


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


def test_m3_eval_query_loader_rejects_invalid_rows(tmp_path) -> None:
    path = tmp_path / "bad.jsonl"
    path.write_text(json.dumps({"query": "missing fields"}) + "\n", encoding="utf-8")

    with pytest.raises(M3EvalInputError, match="query_type"):
        load_m3_eval_queries(path)


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


def search_result(result_id: str, canonical_key: str) -> SearchResult:
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
        metadata={},
    )
