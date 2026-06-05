import json
from contextlib import nullcontext
from pathlib import Path
from uuid import uuid4

import pytest
from typer.testing import CliRunner

from pkcs.cli import app as cli_app
from pkcs.config import get_settings
from pkcs.ingest import IngestService
from pkcs.mcp.server import create_mcp_server
from pkcs.reader import ReadSourceService
from pkcs.reader.service import ReadSourceError
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


def make_reader_service(db_session) -> ReadSourceService:
    return ReadSourceService(session_factory=lambda: nullcontext(db_session))


def write_reader_fixture(path: Path, token: str) -> None:
    path.write_text(
        "# Reader Notes\n"
        "\n"
        "Introductory line before evidence.\n"
        f"Target evidence line contains {token}.\n"
        "Follow-up evidence line.\n"
        "\n"
        "Closing line after evidence.\n",
        encoding="utf-8",
    )


def test_read_source_by_chunk_id_maps_from_search_result(db_session, tmp_path) -> None:
    token = uuid4().hex
    source_path = tmp_path / "reader.md"
    write_reader_fixture(source_path, token)
    ingest = make_ingest_service(db_session, tmp_path / "raw")
    ingest.ingest_source(
        path=source_path,
        knowledge_type="document",
        canonical_key=f"document:reader-{token}",
    )
    result = make_search_service(db_session).search_knowledge(query=token, top_k=1).results[0]

    fragment = make_reader_service(db_session).read_source(chunk_id=result.chunk_id)

    assert fragment.source.source_id == result.source_id
    assert fragment.source.version_id == result.version_id
    assert fragment.source.chunk_id == result.chunk_id
    assert fragment.locator == result.citation.locator
    assert token in fragment.content
    assert fragment.context_line_start == fragment.line_start
    assert fragment.context_line_end == fragment.line_end


def test_read_source_by_source_version_locator_with_context_lines(db_session, tmp_path) -> None:
    token = uuid4().hex
    source_path = tmp_path / "locator.md"
    write_reader_fixture(source_path, token)
    report = make_ingest_service(db_session, tmp_path / "raw").ingest_source(
        path=source_path,
        knowledge_type="document",
        canonical_key=f"document:locator-{token}",
    )

    fragment = make_reader_service(db_session).read_source(
        source_id=report.source_id,
        version_id=report.version_id,
        locator="line 4-4",
        context_lines=1,
    )

    assert fragment.source.source_id == report.source_id
    assert fragment.source.version_id == report.version_id
    assert fragment.source.chunk_id is None
    assert fragment.locator == "line 4-4"
    assert fragment.line_start == 4
    assert fragment.line_end == 4
    assert fragment.context_line_start == 3
    assert fragment.context_line_end == 5
    assert "Introductory line before evidence." in fragment.content
    assert token in fragment.content
    assert "Follow-up evidence line." in fragment.content


def test_read_source_invalid_locator_and_missing_chunk_errors(db_session, tmp_path) -> None:
    token = uuid4().hex
    source_path = tmp_path / "invalid.md"
    write_reader_fixture(source_path, token)
    report = make_ingest_service(db_session, tmp_path / "raw").ingest_source(
        path=source_path,
        knowledge_type="document",
        canonical_key=f"document:invalid-{token}",
    )
    reader = make_reader_service(db_session)

    with pytest.raises(ReadSourceError, match="locator must use format"):
        reader.read_source(source_id=report.source_id, version_id=report.version_id, locator="paragraph 4")

    with pytest.raises(ReadSourceError, match="locator ends beyond source line count"):
        reader.read_source(source_id=report.source_id, version_id=report.version_id, locator="line 4-999")

    with pytest.raises(ReadSourceError, match="chunk not found"):
        reader.read_source(chunk_id=f"missing-{token}")


def test_cli_read_command_outputs_fragment(monkeypatch, migrated_database_url, tmp_path) -> None:
    token = uuid4().hex
    source_path = tmp_path / "cli-read.md"
    write_reader_fixture(source_path, token)
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
            f"document:cli-read-{token}",
        ],
    )
    search_result = runner.invoke(cli_app, ["search", token, "--top-k", "1"])
    chunk_id = json.loads(search_result.stdout)["results"][0]["chunk_id"]

    read_result = runner.invoke(cli_app, ["read", "--chunk-id", chunk_id])

    get_settings.cache_clear()
    assert read_result.exit_code == 0
    body = json.loads(read_result.stdout)
    assert body["source"]["chunk_id"] == chunk_id
    assert token in body["content"]


async def test_mcp_read_source_tool_smoke(monkeypatch, migrated_database_url, tmp_path) -> None:
    token = uuid4().hex
    source_path = tmp_path / "mcp-read.md"
    write_reader_fixture(source_path, token)
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
            "canonical_key": f"document:mcp-read-{token}",
        },
    )
    search_result = await server.call_tool("search_knowledge", {"query": token, "top_k": 1})
    chunk_id = json.loads(search_result[0].text)["results"][0]["chunk_id"]
    read_result = await server.call_tool("read_source", {"chunk_id": chunk_id, "context_lines": 1})

    get_settings.cache_clear()
    assert "read_source" in tool_names
    body = json.loads(read_result[0].text)
    assert body["source"]["chunk_id"] == chunk_id
    assert token in body["content"]
