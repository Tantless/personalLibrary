from contextlib import nullcontext
from pathlib import Path
from uuid import uuid4

from pkcs.ingest import IngestService
from pkcs.search import (
    PlannedSearchService,
    PostgresFTSSearchProvider,
    PostgresSourceAliasProvider,
    SearchService,
    SourceAlias,
    source_alias_from_metadata,
)
from pkcs.search.models import SearchCitation, SearchResult
from pkcs.search.planning import PASS_GLOSSARY_EXPANSION, PASS_SOURCE_ALIAS, QueryPlanner
from pkcs.storage.raw_archive import RawArchiveWriter


def make_ingest_service(db_session, raw_root: Path) -> IngestService:
    return IngestService(
        session_factory=lambda: nullcontext(db_session),
        raw_archive_writer=RawArchiveWriter(raw_root),
        chunk_max_chars=500,
        chunk_overlap_lines=1,
    )


def make_search_service(db_session) -> SearchService:
    return SearchService(
        provider=PostgresFTSSearchProvider(session_factory=lambda: nullcontext(db_session)),
        default_top_k=10,
    )


def make_planned_search_service(db_session) -> PlannedSearchService:
    return PlannedSearchService(
        provider=PostgresFTSSearchProvider(session_factory=lambda: nullcontext(db_session)),
        source_alias_provider=PostgresSourceAliasProvider(session_factory=lambda: nullcontext(db_session)),
        default_top_k=10,
    )


def test_source_alias_from_metadata_generates_product_aliases() -> None:
    alias = source_alias_from_metadata(
        title="OpenAI Agents Python: Tools docs",
        canonical_key="m3-corpus:ai:openai-agents-python-tools",
    )

    assert "Agents SDK" in alias.aliases
    assert "OpenAI Agents Python Tools docs" in alias.aliases
    assert "tools" in {term.casefold() for term in alias.terms}


def test_planned_search_recovers_source_from_mixed_language_query(db_session, tmp_path) -> None:
    token = uuid4().hex
    source_path = tmp_path / "agents-tools.md"
    source_path.write_text(
        "# OpenAI Agents Python: Tools docs\n\n"
        f"Function tools let agents invoke Python callables. Unique token {token}.\n",
        encoding="utf-8",
    )
    ingest = make_ingest_service(db_session, tmp_path / "raw")
    canonical_key = f"document:planned-tools-{token}"
    report = ingest.ingest_source(
        path=source_path,
        knowledge_type="document",
        canonical_key=canonical_key,
    )
    query = "Agents SDK 如何处理工具调用？"

    baseline = make_search_service(db_session).search_knowledge(
        query=query,
        canonical_key=canonical_key,
        top_k=5,
    )
    planned = make_planned_search_service(db_session).search_knowledge(
        query=query,
        canonical_key=canonical_key,
        top_k=5,
    )

    assert report.source_id not in {result.source_id for result in baseline.results}
    assert planned.results
    assert planned.results[0].source_id == report.source_id
    assert planned.results[0].metadata["planned_retrieval"]["fused_rank"] == 1
    pass_names = {
        hit["pass_name"]
        for hit in planned.results[0].metadata["planned_retrieval"]["pass_hits"]
    }
    assert {PASS_GLOSSARY_EXPANSION, PASS_SOURCE_ALIAS} <= pass_names


def test_planned_search_response_to_dict_has_plan_and_pass_runs(db_session, tmp_path) -> None:
    token = uuid4().hex
    source_path = tmp_path / "system-card.md"
    source_path.write_text(
        "# OpenAI GPT-5 System Card\n\n"
        f"Safety evaluations cover multiple risk categories. Unique token {token}.\n",
        encoding="utf-8",
    )
    make_ingest_service(db_session, tmp_path / "raw").ingest_source(
        path=source_path,
        knowledge_type="document",
        canonical_key=f"document:gpt5-system-card-{token}",
    )

    response = make_planned_search_service(db_session).search_knowledge(
        query="GPT-5 system card 讨论了哪些安全评估类别？",
        top_k=3,
    )
    body = response.to_dict()

    assert set(body) == {
        "query",
        "knowledge_type",
        "canonical_key",
        "top_k",
        "retrieval_plan",
        "pass_runs",
        "results",
    }
    assert body["retrieval_plan"]["intent"] == "safety_report_lookup"
    assert body["pass_runs"]
    assert body["results"][0]["metadata"]["planned_retrieval"]["fusion"] == "reciprocal_rank_v1"


def test_planned_search_continues_when_one_pass_fails() -> None:
    planner = QueryPlanner(
        source_aliases=[
            SourceAlias(
                title="OpenAI Agents Python Tools docs",
                aliases=("Agents SDK",),
                terms=("tools", "function tools"),
                canonical_key="document:tools",
            )
        ]
    )
    service = PlannedSearchService(
        provider=FlakyProvider(),
        planner=planner,
        default_top_k=5,
    )

    response = service.search_knowledge(query="Agents SDK 如何处理工具调用？", top_k=5)

    assert response.pass_runs[0].name == "original"
    assert response.pass_runs[0].error_type == "RuntimeError"
    assert response.results[0].canonical_key == "document:tools"
    assert response.results[0].metadata["planned_retrieval"]["pass_hits"]


class FlakyProvider:
    def search(
        self,
        *,
        query: str,
        top_k: int,
        knowledge_type: str | None = None,
        canonical_key: str | None = None,
    ) -> list[SearchResult]:
        if query == "Agents SDK 如何处理工具调用？":
            raise RuntimeError("planned test failure")
        if "function tools" not in query and "Tools docs" not in query:
            return []
        return [search_result("document:tools")]


def search_result(canonical_key: str) -> SearchResult:
    return SearchResult(
        result_id="result-1",
        chunk_id="chunk-1",
        source_id="source-1",
        version_id="version-1",
        canonical_key=canonical_key,
        title="OpenAI Agents Python Tools docs",
        source_format="md",
        normalized_format="markdown",
        knowledge_type="document",
        snippet="Function tools let agents invoke code.",
        score=1.0,
        citation=SearchCitation(locator="line 1-2", line_start=1, line_end=2),
        metadata={},
    )
