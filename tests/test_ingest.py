import json
from contextlib import nullcontext
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select
from typer.testing import CliRunner

from pkcs.cli import app as cli_app
from pkcs.config import get_settings
from pkcs.db.models import Chunk, Citation, SourceVersion
from pkcs.ingest import IngestService
from pkcs.mcp.server import create_mcp_server
from pkcs.storage.raw_archive import RawArchiveWriter


def make_service(db_session, raw_root: Path, *, chunk_max_chars: int = 300) -> IngestService:
    return IngestService(
        session_factory=lambda: nullcontext(db_session),
        raw_archive_writer=RawArchiveWriter(raw_root),
        chunk_max_chars=chunk_max_chars,
        chunk_overlap_lines=1,
    )


def test_ingest_markdown_file_creates_version_chunks_citations_and_archive(db_session, tmp_path) -> None:
    source_path = tmp_path / "notes.md"
    source_path.write_text(
        "# Project Notes\n\n"
        "Introductory context.\n\n"
        "## Goals\n\n"
        "PKCS keeps source evidence traceable.\n\n"
        "## Acceptance\n\n"
        "Evidence must include source, version, and locator references.\n",
        encoding="utf-8",
    )
    service = make_service(db_session, tmp_path / "raw")

    report = service.ingest_source(
        path=source_path,
        source_type="markdown_doc",
        canonical_key=f"markdown_doc:test-{uuid4().hex}",
    )

    assert report.status == "completed"
    assert report.source_id is not None
    assert report.version_id is not None
    assert report.created_new_source is True
    assert report.created_new_version is True
    assert report.chunks_created >= 3
    assert len(report.succeeded) == 1

    version = db_session.get(SourceVersion, report.version_id)
    assert version is not None
    assert Path(version.raw_archive_path).exists()
    assert version.metadata_json["original_filename"] == "notes.md"

    chunks = db_session.scalars(select(Chunk).where(Chunk.version_id == report.version_id)).all()
    citations = db_session.scalars(select(Citation).where(Citation.version_id == report.version_id)).all()
    assert len(chunks) == report.chunks_created
    assert len(citations) == report.chunks_created
    assert any(chunk.heading_path == ["Project Notes", "Goals"] for chunk in chunks)
    assert all(citation.line_start <= citation.line_end for citation in citations)


def test_ingest_duplicate_hash_skips_and_new_hash_creates_new_version(db_session, tmp_path) -> None:
    source_path = tmp_path / "versioned.md"
    source_path.write_text("# Versioned\n\nOriginal body.\n", encoding="utf-8")
    canonical_key = f"markdown_doc:versioned-{uuid4().hex}"
    service = make_service(db_session, tmp_path / "raw")

    first = service.ingest_source(path=source_path, source_type="markdown_doc", canonical_key=canonical_key)
    duplicate = service.ingest_source(path=source_path, source_type="markdown_doc", canonical_key=canonical_key)
    source_path.write_text("# Versioned\n\nChanged body.\n", encoding="utf-8")
    changed = service.ingest_source(path=source_path, source_type="markdown_doc", canonical_key=canonical_key)

    assert first.status == "completed"
    assert duplicate.status == "skipped"
    assert duplicate.skipped[0].version_id == first.version_id
    assert duplicate.skipped[0].chunks_created == 0
    assert changed.status == "completed"
    assert changed.source_id == first.source_id
    assert changed.version_id != first.version_id
    assert changed.created_new_source is False

    versions = db_session.scalars(select(SourceVersion).where(SourceVersion.source_id == first.source_id)).all()
    assert len(versions) == 2


def test_ingest_directory_is_non_recursive_and_continues_after_file_failure(db_session, tmp_path) -> None:
    root = tmp_path / "batch"
    root.mkdir()
    (root / "good.md").write_text("# Good\n\nThis file should ingest.\n", encoding="utf-8")
    (root / "bad.md").write_bytes(b"\xff\xfe\x00")
    (root / "ignore.bin").write_bytes(b"not supported")
    nested = root / "nested"
    nested.mkdir()
    (nested / "nested.md").write_text("# Nested\n\nDo not ingest recursively.\n", encoding="utf-8")
    service = make_service(db_session, tmp_path / "raw")

    report = service.ingest_source(path=root, source_type="markdown_doc")

    assert report.status == "completed_with_errors"
    assert len(report.succeeded) == 1
    assert len(report.failed) == 1
    assert len(report.skipped) == 2
    assert report.succeeded[0].input_path.endswith("good.md")
    assert report.failed[0].input_path.endswith("bad.md")
    assert {Path(item.input_path).name for item in report.skipped} == {"ignore.bin", "nested"}


def test_ingest_ai_conversation_transcript_and_jsonl_metadata(db_session, tmp_path) -> None:
    service = make_service(db_session, tmp_path / "raw")
    transcript = Path("tests/fixtures/conversations/support-thread.md")
    jsonl = Path("tests/fixtures/conversations/codex-session.jsonl")

    transcript_report = service.ingest_source(
        path=transcript,
        source_type="ai_conversation",
        canonical_key=f"ai_conversation:transcript-{uuid4().hex}",
    )
    jsonl_report = service.ingest_source(
        path=jsonl,
        source_type="ai_conversation",
        canonical_key=f"ai_conversation:jsonl-{uuid4().hex}",
    )

    transcript_version = db_session.get(SourceVersion, transcript_report.version_id)
    jsonl_version = db_session.get(SourceVersion, jsonl_report.version_id)
    assert transcript_report.status == "completed"
    assert jsonl_report.status == "completed"
    assert transcript_version.metadata_json["format"] == "transcript"
    assert transcript_version.metadata_json["participants"] == ["Assistant", "User"]
    assert jsonl_version.metadata_json["format"] == "jsonl"
    assert jsonl_version.metadata_json["participants"] == ["assistant", "user"]

    chunks = db_session.scalars(select(Chunk).where(Chunk.version_id == transcript_report.version_id)).all()
    assert chunks
    assert chunks[0].metadata_json["roles"]
    assert chunks[0].metadata_json["turn_start"] == 0


def test_cli_ingest_command_outputs_report(monkeypatch, migrated_database_url, tmp_path) -> None:
    source_path = tmp_path / "cli.md"
    source_path.write_text("# CLI\n\nIngest from Typer command.\n", encoding="utf-8")
    monkeypatch.setenv("PKCS_DATABASE_URL", migrated_database_url)
    monkeypatch.setenv("PKCS_RAW_ARCHIVE_PATH", str(tmp_path / "raw"))
    get_settings.cache_clear()

    result = CliRunner().invoke(
        cli_app,
        [
            "ingest",
            str(source_path),
            "--source-type",
            "markdown_doc",
            "--canonical-key",
            f"markdown_doc:cli-{uuid4().hex}",
        ],
    )

    get_settings.cache_clear()
    assert result.exit_code == 0
    body = json.loads(result.stdout)
    assert body["status"] == "completed"
    assert body["succeeded"][0]["chunks_created"] >= 1


async def test_mcp_ingest_source_tool_smoke(monkeypatch, migrated_database_url, tmp_path) -> None:
    source_path = tmp_path / "mcp.md"
    source_path.write_text("# MCP\n\nIngest from FastMCP tool.\n", encoding="utf-8")
    monkeypatch.setenv("PKCS_DATABASE_URL", migrated_database_url)
    monkeypatch.setenv("PKCS_RAW_ARCHIVE_PATH", str(tmp_path / "raw"))
    get_settings.cache_clear()

    server = create_mcp_server()
    tools = await server.list_tools()
    tool_names = {tool.name for tool in tools}
    result = await server.call_tool(
        "ingest_source",
        {
            "path": str(source_path),
            "source_type": "markdown_doc",
            "canonical_key": f"markdown_doc:mcp-{uuid4().hex}",
        },
    )

    get_settings.cache_clear()
    assert "ingest_source" in tool_names
    body = json.loads(result[0].text)
    assert body["status"] == "completed"
    assert body["succeeded"][0]["chunks_created"] >= 1
