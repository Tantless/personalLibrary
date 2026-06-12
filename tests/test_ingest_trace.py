import json
from contextlib import nullcontext
from pathlib import Path
from uuid import uuid4

from typer.testing import CliRunner

from pkcs.cli import app as cli_app
from pkcs.config import get_settings
from pkcs.ingest import ArtifactIngestTraceService
from pkcs.storage.raw_archive import RawArchiveWriter


def make_trace_service(db_session, raw_root: Path) -> ArtifactIngestTraceService:
    return ArtifactIngestTraceService(
        session_factory=lambda: nullcontext(db_session),
        raw_archive_writer=RawArchiveWriter(raw_root),
        chunk_max_chars=1000,
        chunk_overlap_lines=1,
    )


def write_artifact_markdown(tmp_path: Path, token: str) -> Path:
    asset_dir = tmp_path / "images"
    asset_dir.mkdir()
    (asset_dir / "flow.png").write_bytes(b"fake-image")
    source_path = tmp_path / "artifact-flow.md"
    source_path.write_text(
        "# Artifact Flow\n\n"
        f"{token} introduces the artifact ingest flow.\n\n"
        "| Component | Role |\n"
        "| --- | --- |\n"
        "| Parser | Detects table and image blocks |\n"
        "| Ingest | Persists artifacts and chunks |\n\n"
        "![Flow diagram](images/flow.png)\n\n"
        "The narrative links both artifact objects.\n",
        encoding="utf-8",
    )
    return source_path


def test_artifact_ingest_trace_outputs_parse_to_database_flow(db_session, tmp_path) -> None:
    token = uuid4().hex
    source_path = write_artifact_markdown(tmp_path, token)
    service = make_trace_service(db_session, tmp_path / "raw")

    trace = service.trace_ingest(
        path=source_path,
        knowledge_type="document",
        canonical_key=f"document:trace-{token}",
    )

    assert trace["trace_version"] == "artifact_ingest_trace_v1"
    assert trace["stage_order"] == ["input", "parser", "asset_resolution", "ingest_report", "database"]
    assert "Explicit public MarkdownBlock AST" in " ".join(trace["design_delta"]["not_yet_implemented"])
    assert trace["input"]["line_count"] >= 10
    assert trace["parser"]["counts"]["table_artifacts"] == 1
    assert trace["parser"]["counts"]["image_artifacts"] == 1
    assert trace["parser"]["counts"]["table_derived_chunks"] == 2
    assert trace["parser"]["counts"]["image_derived_chunks"] == 1
    assert trace["asset_resolution"][0]["exists"] is True
    assert trace["ingest_report"]["status"] == "completed"

    database = trace["database"]
    assert database["available"] is True
    assert database["counts"]["table_artifacts"] == 1
    assert database["counts"]["image_artifacts"] == 1
    assert database["counts"]["table_derived_chunks"] == 2
    assert database["counts"]["image_derived_chunks"] == 1
    assert database["counts"]["citations"] == database["counts"]["chunks"]
    assert database["version"]["raw_archive_exists"] is True
    assert database["image_artifacts"][0]["asset_exists"] is True
    assert database["link_checks"]["linked_artifacts_count"] == 2
    assert database["link_checks"]["linked_artifacts_with_artifact_id"] == 2
    assert database["link_checks"]["artifact_chunks_count"] == 3
    assert database["link_checks"]["artifact_chunks_with_artifact_id"] == 3
    assert database["link_checks"]["artifact_chunks_with_parent_narrative_chunk_id"] == 3

    narrative = next(chunk for chunk in database["chunks"] if chunk["chunk_kind"] == "narrative")
    table_rows = next(chunk for chunk in database["chunks"] if chunk["chunk_kind"] == "table_rows")
    image_summary = next(chunk for chunk in database["chunks"] if chunk["chunk_kind"] == "image_summary")
    assert {item["artifact_type"] for item in narrative["linked_artifacts"]} == {"table", "image"}
    assert all(item["artifact_id"] for item in narrative["linked_artifacts"])
    assert table_rows["artifact_type"] == "table"
    assert table_rows["artifact_id"]
    assert table_rows["parent_narrative_chunk_id"] == narrative["id"]
    assert image_summary["artifact_type"] == "image"
    assert image_summary["artifact_id"]
    assert image_summary["parent_narrative_chunk_id"] == narrative["id"]


def test_cli_trace_ingest_outputs_trace(monkeypatch, migrated_database_url, tmp_path) -> None:
    token = uuid4().hex
    source_path = write_artifact_markdown(tmp_path, token)
    monkeypatch.setenv("PKCS_DATABASE_URL", migrated_database_url)
    monkeypatch.setenv("PKCS_RAW_ARCHIVE_PATH", str(tmp_path / "raw"))
    get_settings.cache_clear()
    output_path = tmp_path / "trace.json"

    result = CliRunner().invoke(
        cli_app,
        [
            "trace-ingest",
            str(source_path),
            "--knowledge-type",
            "document",
            "--canonical-key",
            f"document:cli-trace-{token}",
            "--output",
            str(output_path),
        ],
    )

    get_settings.cache_clear()
    assert result.exit_code == 0
    stdout = json.loads(result.stdout)
    body = json.loads(output_path.read_text(encoding="utf-8"))
    assert stdout == {"status": "written", "output": str(output_path)}
    assert body["trace_version"] == "artifact_ingest_trace_v1"
    assert body["parser"]["counts"]["table_artifacts"] == 1
    assert body["database"]["counts"]["image_artifacts"] == 1
    assert body["database"]["link_checks"]["artifact_chunks_with_artifact_id"] == 3
