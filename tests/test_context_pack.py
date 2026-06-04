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
from pkcs.search import PostgresFTSSearchProvider, SearchService
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
        source_type="markdown_doc",
        canonical_key=f"markdown_doc:first-{token}",
    )
    second_report = ingest.ingest_source(
        path=second_path,
        source_type="markdown_doc",
        canonical_key=f"markdown_doc:second-{token}",
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
        source_type="markdown_doc",
        canonical_key=f"markdown_doc:budget-{token}",
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
            "--source-type",
            "markdown_doc",
            "--canonical-key",
            f"markdown_doc:cli-context-{token}",
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
            "source_type": "markdown_doc",
            "canonical_key": f"markdown_doc:mcp-context-{token}",
        },
    )
    result = await server.call_tool("get_context_pack", {"query": token, "top_k": 5, "budget_tokens": 300})

    get_settings.cache_clear()
    assert "get_context_pack" in tool_names
    body = json.loads(result[0].text)
    assert body["evidence"]
    assert body["context_pack_markdown"].startswith("# Context Pack")
