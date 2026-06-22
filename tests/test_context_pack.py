import json
from collections import Counter
from contextlib import nullcontext
from pathlib import Path
from uuid import uuid4

from typer.testing import CliRunner

from pkcs.cli import app as cli_app
from pkcs.config import get_settings
from pkcs.context_pack import ContextPackService
from pkcs.ingest import IngestService
from pkcs.mcp.server import create_mcp_server
from pkcs.reader import ReadSourceService
from pkcs.search import (
    PlannedSearchService,
    PostgresFTSSearchProvider,
    PostgresSourceAliasProvider,
    SearchService,
)
from pkcs.search.models import SearchCitation, SearchResponse, SearchResult
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


def make_context_service(
    db_session,
    *,
    max_evidence: int = 10,
    max_evidence_per_source: int = 3,
) -> ContextPackService:
    return ContextPackService(
        search_service=make_search_service(db_session),
        read_source_service=ReadSourceService(session_factory=lambda: nullcontext(db_session)),
        default_top_k=10,
        max_evidence=max_evidence,
        max_evidence_per_source=max_evidence_per_source,
    )


def make_planned_context_service(
    db_session,
    *,
    max_evidence: int = 10,
    max_evidence_per_source: int = 3,
) -> ContextPackService:
    session_factory = lambda: nullcontext(db_session)
    return ContextPackService(
        search_service=PlannedSearchService(
            provider=PostgresFTSSearchProvider(session_factory=session_factory),
            source_alias_provider=PostgresSourceAliasProvider(session_factory=session_factory),
            default_top_k=10,
        ),
        read_source_service=ReadSourceService(session_factory=session_factory),
        default_top_k=10,
        max_evidence=max_evidence,
        max_evidence_per_source=max_evidence_per_source,
    )


def write_multi_chunk_doc(path: Path, token: str, section_count: int) -> None:
    parts = ["# Multi Chunk"]
    for index in range(section_count):
        parts.extend(
            [
                "",
                f"## Section {index}",
                "",
                f"{token} evidence line {index} with source traceability.",
            ]
        )
    path.write_text("\n".join(parts), encoding="utf-8")


def test_context_pack_caps_per_source_and_maps_evidence_to_read_source(db_session, tmp_path) -> None:
    token = uuid4().hex
    first_path = tmp_path / "first.md"
    second_path = tmp_path / "second.md"
    write_multi_chunk_doc(first_path, token, 4)
    write_multi_chunk_doc(second_path, token, 2)
    ingest = make_ingest_service(db_session, tmp_path / "raw")
    first_report = ingest.ingest_source(
        path=first_path,
        knowledge_type="document",
        canonical_key=f"document:first-{token}",
    )
    second_report = ingest.ingest_source(
        path=second_path,
        knowledge_type="document",
        canonical_key=f"document:second-{token}",
    )
    service = make_context_service(db_session, max_evidence=5, max_evidence_per_source=2)

    response = service.get_context_pack(query=token, top_k=10)
    body = response.to_dict()

    assert {
        "query",
        "retrieval_plan",
        "sources",
        "evidence",
        "followup_read_suggestions",
        "context_pack_markdown",
    } == set(body)
    assert body["retrieval_plan"]["max_evidence"] == 5
    assert body["retrieval_plan"]["max_evidence_per_source"] == 2
    assert body["retrieval_plan"]["budget_is_soft_limit"] is True
    assert len(response.evidence) == 4
    assert len(response.evidence) <= 5
    per_source = Counter(item.source_id for item in response.evidence)
    assert max(per_source.values()) <= 2
    assert {item.source_id for item in response.evidence} == {first_report.source_id, second_report.source_id}
    assert len(response.sources) == 2
    assert len(response.followup_read_suggestions) == len(response.evidence)
    assert "## Conflicts / Caveats" in response.context_pack_markdown
    assert "Real conflict detection is not performed in MVP." in response.context_pack_markdown

    reader = ReadSourceService(session_factory=lambda: nullcontext(db_session))
    for item in response.evidence:
        fragment = reader.read_source(chunk_id=item.chunk_id)
        assert fragment.source.source_id == item.source_id
        assert fragment.source.version_id == item.version_id
        assert fragment.locator == item.locator
        assert item.content == fragment.content


def test_context_pack_budget_tokens_softly_reduces_markdown(db_session, tmp_path) -> None:
    token = uuid4().hex
    source_path = tmp_path / "budget.md"
    write_multi_chunk_doc(source_path, token, 5)
    make_ingest_service(db_session, tmp_path / "raw").ingest_source(
        path=source_path,
        knowledge_type="document",
        canonical_key=f"document:budget-{token}",
    )
    service = make_context_service(db_session, max_evidence=5, max_evidence_per_source=5)

    full = service.get_context_pack(query=token, top_k=10)
    limited = service.get_context_pack(query=token, top_k=10, budget_tokens=120)

    assert len(limited.evidence) == len(full.evidence)
    assert len(limited.context_pack_markdown) < len(full.context_pack_markdown)
    assert limited.retrieval_plan["budget_tokens"] == 120
    assert "soft Markdown length hint" in limited.context_pack_markdown
    assert "## Conflicts / Caveats" in limited.context_pack_markdown


def test_context_pack_no_results_returns_empty_evidence_with_caveats(db_session) -> None:
    token = f"missing{uuid4().hex}"
    response = make_context_service(db_session).get_context_pack(query=token, top_k=5)

    assert response.evidence == []
    assert response.sources == []
    assert response.followup_read_suggestions == []
    assert "No sources matched the query." in response.context_pack_markdown
    assert "## Conflicts / Caveats" in response.context_pack_markdown


def test_context_pack_selection_prefers_query_supporting_evidence() -> None:
    noise = fake_search_result(
        result_id="noise",
        chunk_id="noise-chunk",
        snippet="A general Bevy overview without the expected support terms.",
    )
    supporting = fake_search_result(
        result_id="supporting",
        chunk_id="supporting-chunk",
        snippet="Bevy is a game engine built around ECS and entity component system patterns.",
    )
    service = ContextPackService(
        search_service=FakeSearchService([noise, supporting]),
        read_source_service=FakeReadSourceService(
            {
                "noise-chunk": "A general Bevy overview without the expected support terms.",
                "supporting-chunk": (
                    "Bevy is a game engine built around ECS and entity component system patterns."
                ),
            }
        ),
        default_top_k=10,
        max_evidence=1,
        max_evidence_per_source=1,
    )

    response = service.get_context_pack(
        query="哪个游戏引擎说明文档描述了实体组件系统能力？",
        top_k=2,
    )

    assert len(response.evidence) == 1
    assert response.evidence[0].chunk_id == "supporting-chunk"
    assert "ECS" in response.evidence[0].content
    assert "query-aware lexical support" in response.retrieval_plan["selection"]


def test_context_pack_uses_planned_search_for_mixed_language_query(db_session, tmp_path) -> None:
    token = uuid4().hex
    source_path = tmp_path / "agents-tools.md"
    source_path.write_text(
        "# OpenAI Agents Python: Tools docs\n\n"
        f"Function tools let agents invoke Python callables. Unique token {token}.\n",
        encoding="utf-8",
    )
    canonical_key = f"document:context-planned-tools-{token}"
    report = make_ingest_service(db_session, tmp_path / "raw").ingest_source(
        path=source_path,
        knowledge_type="document",
        canonical_key=canonical_key,
    )
    service = make_planned_context_service(db_session)

    response = service.get_context_pack(
        query="Agents SDK 如何处理工具调用？",
        canonical_key=canonical_key,
        top_k=5,
    )

    assert response.evidence
    assert response.evidence[0].source_id == report.source_id
    assert "Function tools" in response.evidence[0].content
    assert response.retrieval_plan["provider"] == "postgres_fts_planned"
    assert response.retrieval_plan["fusion"] == "reciprocal_rank_v1"
    assert response.retrieval_plan["query_plan"]["intent"] == "official_doc_lookup"
    assert {item["name"] for item in response.retrieval_plan["pass_runs"]} >= {
        "original",
        "source_alias",
        "combined",
    }
    assert "Pass source_alias" in response.context_pack_markdown

    fragment = ReadSourceService(session_factory=lambda: nullcontext(db_session)).read_source(
        chunk_id=response.evidence[0].chunk_id,
    )
    assert fragment.source.source_id == response.evidence[0].source_id
    assert fragment.locator == response.evidence[0].locator


def test_context_pack_hydrates_linked_markdown_artifacts(db_session, tmp_path) -> None:
    token = uuid4().hex
    asset_dir = tmp_path / "assets"
    asset_dir.mkdir()
    (asset_dir / "flow.png").write_bytes(b"fake-image")
    source_path = tmp_path / "artifacts.md"
    source_path.write_text(
        "# Artifact Context\n\n"
        f"{token} introduces a retrieval artifact set.\n\n"
        "| Stage | Output |\n"
        "| --- | --- |\n"
        "| Search | Candidate chunks |\n\n"
        "![Retrieval flow](assets/flow.png)\n",
        encoding="utf-8",
    )
    (tmp_path / "image-enrichment.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "images": [
                    {
                        "asset_path": "assets/flow.png",
                        "vision_summary": "A retrieval flow diagram from search to candidate chunks.",
                        "ocr_text": "Search -> Candidate chunks",
                        "visual_type": "diagram",
                        "key_elements": ["Search", "Candidate chunks"],
                        "confidence": "high",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    make_ingest_service(db_session, tmp_path / "raw").ingest_source(
        path=source_path,
        knowledge_type="document",
        canonical_key=f"document:context-artifacts-{token}",
    )
    service = make_context_service(db_session)

    response = service.get_context_pack(query=token, top_k=1)

    assert len(response.evidence) == 1
    content = response.evidence[0].content
    assert "Linked Artifacts:" in content
    assert "Table tbl_001" in content
    assert "Columns: Stage, Output; rows: 1" in content
    assert "Image img_001" in content
    assert "A retrieval flow diagram from search to candidate chunks." in content
    assert "OCR: Search -> Candidate chunks" in content
    assert "Visual type: diagram" in content
    assert "Key elements: Search, Candidate chunks" in content
    assert "Asset:" in content


def test_cli_context_pack_command_outputs_response(monkeypatch, migrated_database_url, tmp_path) -> None:
    token = uuid4().hex
    source_path = tmp_path / "cli-context.md"
    write_multi_chunk_doc(source_path, token, 2)
    monkeypatch.setenv("PKCS_DATABASE_URL", migrated_database_url)
    monkeypatch.setenv("PKCS_RAW_ARCHIVE_PATH", str(tmp_path / "raw"))
    get_settings.cache_clear()
    runner = CliRunner()
    runner.invoke(
        cli_app,
        [
            "ingest",
            str(source_path),
            "--knowledge-type",
            "document",
            "--canonical-key",
            f"document:cli-context-{token}",
        ],
    )

    result = runner.invoke(cli_app, ["context-pack", token, "--top-k", "5", "--budget-tokens", "300"])

    get_settings.cache_clear()
    assert result.exit_code == 0
    body = json.loads(result.stdout)
    assert body["query"] == token
    assert body["evidence"]
    assert body["followup_read_suggestions"]
    assert "## Conflicts / Caveats" in body["context_pack_markdown"]


async def test_mcp_get_context_pack_tool_smoke(monkeypatch, migrated_database_url, tmp_path) -> None:
    token = uuid4().hex
    source_path = tmp_path / "mcp-context.md"
    write_multi_chunk_doc(source_path, token, 2)
    monkeypatch.setenv("PKCS_DATABASE_URL", migrated_database_url)
    monkeypatch.setenv("PKCS_RAW_ARCHIVE_PATH", str(tmp_path / "raw"))
    get_settings.cache_clear()

    server = create_mcp_server()
    tools = await server.list_tools()
    tool_names = {tool.name for tool in tools}
    await server.call_tool(
        "ingest_source",
        {
            "path": str(source_path),
            "knowledge_type": "document",
            "canonical_key": f"document:mcp-context-{token}",
        },
    )
    result = await server.call_tool("get_context_pack", {"query": token, "top_k": 5, "budget_tokens": 300})

    get_settings.cache_clear()
    assert "get_context_pack" in tool_names
    body = json.loads(result[0].text)
    assert body["evidence"]
    assert body["context_pack_markdown"].startswith("# Context Pack")


class FakeSearchService:
    def __init__(self, results: list[SearchResult]) -> None:
        self.results = results

    def search_knowledge(self, *, query, knowledge_type=None, canonical_key=None, top_k=None):
        return SearchResponse(
            query=query,
            knowledge_type=knowledge_type,
            canonical_key=canonical_key,
            top_k=top_k or 10,
            results=self.results,
        )


class FakeReadSourceService:
    def __init__(self, content_by_chunk_id: dict[str, str]) -> None:
        self.content_by_chunk_id = content_by_chunk_id

    def read_source(self, *, chunk_id, source_id=None, version_id=None, locator=None, context_lines=0):
        return FakeSourceFragment(content=self.content_by_chunk_id[chunk_id])


class FakeSourceFragment:
    def __init__(self, *, content: str) -> None:
        self.content = content


def fake_search_result(*, result_id: str, chunk_id: str, snippet: str) -> SearchResult:
    return SearchResult(
        result_id=result_id,
        chunk_id=chunk_id,
        source_id="bevy-source",
        version_id="bevy-version",
        canonical_key="m3-corpus:game:bevy-readme",
        title="Bevy README",
        source_format="md",
        normalized_format="md",
        knowledge_type="document",
        snippet=snippet,
        score=1.0,
        citation=SearchCitation(locator="line 1-2", line_start=1, line_end=2),
        metadata={},
    )
