import json
from contextlib import nullcontext
from pathlib import Path
from uuid import uuid4

from typer.testing import CliRunner

from pkcs.cli import app as cli_app
from pkcs.config import get_settings
from pkcs.db.models import Source
from pkcs.ingest import IngestService
from pkcs.mcp.server import create_mcp_server
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


def test_search_knowledge_returns_stable_result_shape_and_filters(db_session, tmp_path) -> None:
    suffix = uuid4().hex
    markdown_path = tmp_path / "traceable.md"
    markdown_path.write_text(
        "# Traceable Notes\n\n"
        f"The project stores {suffix} evidence with source and version references.\n",
        encoding="utf-8",
    )
    conversation_path = tmp_path / "traceable.jsonl"
    conversation_path.write_text(
        f'{{"conversation_title":"Traceable Chat","role":"user","content":"Find {suffix} evidence."}}\n'
        f'{{"conversation_title":"Traceable Chat","role":"assistant","content":"Return stable citations for {suffix}."}}\n',
        encoding="utf-8",
    )
    markdown_key = f"document:traceable-{suffix}"
    conversation_key = f"ai_conversation:traceable-{suffix}"
    ingest = make_ingest_service(db_session, tmp_path / "raw")
    markdown_report = ingest.ingest_source(
        path=markdown_path,
        knowledge_type="document",
        canonical_key=markdown_key,
    )
    conversation_report = ingest.ingest_source(
        path=conversation_path,
        knowledge_type="ai_conversation",
        canonical_key=conversation_key,
    )
    search = make_search_service(db_session)

    response = search.search_knowledge(query=suffix, top_k=10)
    markdown_only = search.search_knowledge(query=suffix, knowledge_type="document", top_k=10)
    canonical_only = search.search_knowledge(query=suffix, canonical_key=conversation_key, top_k=10)

    assert response.query == suffix
    assert len(response.results) >= 2
    first = response.results[0].to_dict()
    assert {
        "result_id",
        "chunk_id",
        "source_id",
        "version_id",
        "canonical_key",
        "title",
        "source_format",
        "normalized_format",
        "knowledge_type",
        "snippet",
        "score",
        "citation",
        "metadata",
    } == set(first)
    assert first["citation"]["locator"].startswith("line ")
    assert first["source_format"] in {"md", "jsonl"}
    assert first["normalized_format"] in {"markdown", "plain_text"}
    assert first["citation"]["line_start"] <= first["citation"]["line_end"]
    assert first["score"] > 0
    assert first["snippet"]
    assert {result.source_id for result in response.results} >= {
        markdown_report.source_id,
        conversation_report.source_id,
    }
    assert {result.knowledge_type for result in markdown_only.results} == {"document"}
    assert {result.canonical_key for result in canonical_only.results} == {conversation_key}


def test_search_top_k_and_title_boost(db_session, tmp_path) -> None:
    suffix = uuid4().hex
    title_path = tmp_path / "title-match.md"
    title_path.write_text(
        f"# {suffix} Atlas\n\n"
        "This title match should sort ahead of a body-only match.\n",
        encoding="utf-8",
    )
    body_path = tmp_path / "body-match.md"
    body_path.write_text(
        "# Body Match\n\n"
        f"This body mentions {suffix} once without using it in the title.\n",
        encoding="utf-8",
    )
    ingest = make_ingest_service(db_session, tmp_path / "raw")
    title_report = ingest.ingest_source(
        path=title_path,
        knowledge_type="document",
        canonical_key=f"document:title-{suffix}",
    )
    ingest.ingest_source(
        path=body_path,
        knowledge_type="document",
        canonical_key=f"document:body-{suffix}",
    )

    response = make_search_service(db_session).search_knowledge(query=suffix, top_k=1)

    assert len(response.results) == 1
    assert response.results[0].source_id == title_report.source_id
    assert response.results[0].title == f"{suffix} Atlas"


def test_search_matches_source_title_when_chunk_text_does_not(db_session, tmp_path) -> None:
    suffix = uuid4().hex
    source_path = tmp_path / "source-title-only.md"
    source_path.write_text(
        "# Chunk Heading\n\n"
        "The body intentionally omits the source title lookup phrase.\n",
        encoding="utf-8",
    )
    report = make_ingest_service(db_session, tmp_path / "raw").ingest_source(
        path=source_path,
        knowledge_type="document",
        canonical_key=f"document:source-title-{suffix}",
    )
    source = db_session.get(Source, report.source_id)
    assert source is not None
    source.title = f"Source Alias Lookup {suffix}"
    db_session.flush()

    response = make_search_service(db_session).search_knowledge(
        query=f"Source Alias Lookup {suffix}",
        top_k=3,
    )

    assert response.results
    assert response.results[0].source_id == report.source_id


def test_search_no_results_returns_empty_list(db_session) -> None:
    response = make_search_service(db_session).search_knowledge(query=f"missingterm{uuid4().hex}", top_k=5)

    assert response.results == []


def test_search_can_return_markdown_table_artifact_chunk(db_session, tmp_path) -> None:
    token = f"artifactterm{uuid4().hex}"
    source_path = tmp_path / "table-search.md"
    source_path.write_text(
        "# Table Search\n\n"
        "| Component | Detail |\n"
        "| --- | --- |\n"
        f"| Retriever | {token} only appears in the table row |\n",
        encoding="utf-8",
    )
    make_ingest_service(db_session, tmp_path / "raw").ingest_source(
        path=source_path,
        knowledge_type="document",
        canonical_key=f"document:table-search-{token}",
    )

    response = make_search_service(db_session).search_knowledge(query=token, top_k=5)

    table_results = [result for result in response.results if result.metadata.get("chunk_kind") == "table_rows"]
    assert table_results
    assert table_results[0].metadata["artifact_type"] == "table"
    assert table_results[0].metadata["artifact_key"] == "tbl_001"
    assert table_results[0].metadata["artifact_id"]
    assert table_results[0].metadata["parent_narrative_chunk_id"]


def test_cli_search_command_outputs_response(monkeypatch, migrated_database_url, tmp_path) -> None:
    suffix = uuid4().hex
    source_path = tmp_path / "cli-search.md"
    source_path.write_text(f"# CLI Search\n\nSearchable token {suffix}.\n", encoding="utf-8")
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
            f"document:cli-search-{suffix}",
        ],
    )

    result = runner.invoke(cli_app, ["search", suffix, "--top-k", "1"])

    get_settings.cache_clear()
    assert result.exit_code == 0
    body = json.loads(result.stdout)
    assert body["query"] == suffix
    assert len(body["results"]) == 1
    assert body["results"][0]["canonical_key"] == f"document:cli-search-{suffix}"


async def test_mcp_search_knowledge_tool_smoke(monkeypatch, migrated_database_url, tmp_path) -> None:
    suffix = uuid4().hex
    source_path = tmp_path / "mcp-search.md"
    source_path.write_text(f"# MCP Search\n\nFastMCP can search token {suffix}.\n", encoding="utf-8")
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
            "canonical_key": f"document:mcp-search-{suffix}",
        },
    )
    result = await server.call_tool("search_knowledge", {"query": suffix, "top_k": 1})

    get_settings.cache_clear()
    assert "search_knowledge" in tool_names
    body = json.loads(result[0].text)
    assert body["results"][0]["canonical_key"] == f"document:mcp-search-{suffix}"
