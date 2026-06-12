import json
from contextlib import nullcontext
from pathlib import Path
from uuid import uuid4

from typer.testing import CliRunner

from pkcs.cli import app as cli_app
from pkcs.config import get_settings
from pkcs.ingest import ArtifactIngestTraceService
from pkcs.ingest.parsers import parse_source_file
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

    assert trace["trace_version"] == "artifact_ingest_trace_v2"
    assert trace["stage_order"] == ["input", "block_graph", "parser", "asset_resolution", "ingest_report", "database"]
    assert "Transient explicit MarkdownBlock graph" in " ".join(trace["design_delta"]["implemented"])
    assert "Persisted source_blocks table" in " ".join(trace["design_delta"]["not_yet_implemented"])
    assert trace["input"]["line_count"] >= 10
    assert trace["block_graph"]["available"] is True
    assert trace["block_graph"]["counts"]["block_types"]["table"] == 1
    assert trace["block_graph"]["counts"]["block_types"]["image"] == 1
    assert trace["block_graph"]["counts"]["artifact_bindings"] == 2
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
    assert table_rows["source_block_id"]
    assert table_rows["bound_block_ids"]
    assert table_rows["parent_narrative_chunk_id"] == narrative["id"]
    assert image_summary["artifact_type"] == "image"
    assert image_summary["artifact_id"]
    assert image_summary["source_block_id"]
    assert image_summary["bound_block_ids"]
    assert image_summary["parent_narrative_chunk_id"] == narrative["id"]


def test_markdown_block_graph_marks_overlap_artifact_links_as_context(tmp_path) -> None:
    source_path = tmp_path / "overlap.md"
    source_path.write_text(
        "# Overlap\n"
        "Intro before table.\n"
        "| A | B |\n"
        "| --- | --- |\n"
        "| x | y |\n"
        "This following paragraph is intentionally long enough to force a second chunk while the table placeholder is retained as overlap context.\n",
        encoding="utf-8",
    )

    parsed = parse_source_file(
        path=source_path,
        knowledge_type="document",
        content_bytes=source_path.read_bytes(),
        max_chars=90,
        overlap_lines=1,
    )

    graph = parsed.markdown_block_graph
    assert graph is not None
    assert [block.block_type for block in graph.blocks].count("table") == 1
    assert graph.artifact_bindings[0].source_block_id

    narrative_chunks = [chunk for chunk in parsed.chunks if chunk.metadata_json.get("chunk_kind") == "narrative"]
    primary_chunk = next(
        chunk
        for chunk in narrative_chunks
        if any(ref["role"] == "primary_reference" for ref in chunk.metadata_json["linked_artifacts"])
    )
    context_chunk = next(
        chunk
        for chunk in narrative_chunks
        if any(ref["role"] == "context_reference" for ref in chunk.metadata_json["linked_artifacts"])
    )
    table_rows = next(chunk for chunk in parsed.chunks if chunk.metadata_json.get("chunk_kind") == "table_rows")

    primary_ref = primary_chunk.metadata_json["linked_artifacts"][0]
    context_ref = context_chunk.metadata_json["linked_artifacts"][0]
    assert primary_ref["source_block_id"] == context_ref["source_block_id"]
    assert primary_ref["source_block_id"] in primary_chunk.metadata_json["primary_block_ids"]
    assert context_ref["source_block_id"] in context_chunk.metadata_json["overlap_block_ids"]
    assert table_rows.metadata_json["parent_narrative_chunk_key"] == primary_chunk.chunk_key


def test_markdown_block_graph_detects_common_image_block_syntax(tmp_path) -> None:
    source_path = tmp_path / "image-syntax.md"
    source_path.write_text(
        "# Image Syntax\n\n"
        "> ![Calculate the slope](images/slope.png)\n\n"
        "[![ML for beginners - Understanding Linear Regression](https://img.youtube.com/vi/CRxFT8oTDMg/0.jpg)](https://youtu.be/CRxFT8oTDMg \"ML for beginners - Understanding Linear Regression\")\n\n"
        "> 🎥 Click the image above for a short video overview of linear regression.\n\n"
        "> Throughout this curriculum, we assume minimal knowledge of math.\n\n"
        "<img alt=\"Average price\" src=\"images/chart.png\" width=\"50%\"/>\n\n"
        "![Reference diagram][diagram]\n\n"
        "[diagram]: images/reference.png \"Reference diagram\"\n\n"
        "```md\n"
        "![Not an artifact](images/code.png)\n"
        "```\n",
        encoding="utf-8",
    )

    parsed = parse_source_file(
        path=source_path,
        knowledge_type="document",
        content_bytes=source_path.read_bytes(),
        max_chars=1000,
        overlap_lines=1,
    )

    graph = parsed.markdown_block_graph
    assert graph is not None
    image_blocks = [block for block in graph.blocks if block.block_type == "image"]
    image_syntaxes = {block.metadata_json["image_syntax"] for block in image_blocks}
    assert image_syntaxes == {
        "blockquote_markdown_image",
        "linked_markdown_image",
        "html_img",
        "reference_image",
    }
    assert not any(item["code"] == "unsupported_linked_markdown_image" for item in graph.diagnostics)
    assert not any(item["code"] == "unsupported_html_image" for item in graph.diagnostics)

    linked = next(artifact for artifact in parsed.image_artifacts if artifact.metadata_json["image_syntax"] == "linked_markdown_image")
    assert linked.original_uri == "https://img.youtube.com/vi/CRxFT8oTDMg/0.jpg"
    assert linked.metadata_json["outer_link_url"] == "https://youtu.be/CRxFT8oTDMg"
    assert linked.caption == "> 🎥 Click the image above for a short video overview of linear regression."
    assert linked.nearby_text == "> Throughout this curriculum, we assume minimal knowledge of math."
    assert linked.locator == "line 5-9"
    assert len(linked.metadata_json["bound_block_ids"]) == 3

    html_image = next(artifact for artifact in parsed.image_artifacts if artifact.metadata_json["image_syntax"] == "html_img")
    assert html_image.original_uri == "images/chart.png"
    assert html_image.alt_text == "Average price"
    assert html_image.metadata_json["html_attrs"]["width"] == "50%"

    reference_image = next(artifact for artifact in parsed.image_artifacts if artifact.metadata_json["image_syntax"] == "reference_image")
    assert reference_image.original_uri == "images/reference.png"
    assert reference_image.metadata_json["reference_id"] == "diagram"


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
    assert body["trace_version"] == "artifact_ingest_trace_v2"
    assert body["block_graph"]["available"] is True
    assert body["parser"]["counts"]["table_artifacts"] == 1
    assert body["database"]["counts"]["image_artifacts"] == 1
    assert body["database"]["link_checks"]["artifact_chunks_with_artifact_id"] == 3
