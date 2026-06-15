import json
from contextlib import nullcontext
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select
from typer.testing import CliRunner

from pkcs.cli import app as cli_app
from pkcs.config import get_settings
from pkcs.context_pack import ContextPackService
from pkcs.db.models import Chunk, Citation, ImageArtifact, IngestJob, SourceVersion, TableArtifact
from pkcs.ingest import IngestService
from pkcs.mcp.server import create_mcp_server
from pkcs.reader import ReadSourceService
from pkcs.search import PostgresFTSSearchProvider, SearchService
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
        knowledge_type="document",
        canonical_key=f"document:test-{uuid4().hex}",
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
    assert version.metadata_json["input_name"] == "notes.md"

    chunks = db_session.scalars(select(Chunk).where(Chunk.version_id == report.version_id)).all()
    citations = db_session.scalars(select(Citation).where(Citation.version_id == report.version_id)).all()
    assert len(chunks) == report.chunks_created
    assert len(citations) == report.chunks_created
    assert any(chunk.heading_path == ["Project Notes", "Goals"] for chunk in chunks)
    assert all(citation.line_start <= citation.line_end for citation in citations)


def test_ingest_markdown_table_and_image_artifacts(db_session, tmp_path) -> None:
    asset_dir = tmp_path / "images"
    asset_dir.mkdir()
    image_path = asset_dir / "rag.png"
    image_path.write_bytes(b"fake-png")
    source_path = tmp_path / "artifact-notes.md"
    source_path.write_text(
        "# Artifact Notes\n\n"
        "The table summarizes the retrieval flow.\n\n"
        "| Component | Role |\n"
        "| --- | --- |\n"
        "| Retriever | Finds chunks |\n"
        "| Reranker | Orders evidence |\n\n"
        "The image shows the same architecture.\n\n"
        "![RAG architecture](images/rag.png)\n\n"
        "The system reads both objects through artifact links.\n",
        encoding="utf-8",
    )
    service = make_service(db_session, tmp_path / "raw", chunk_max_chars=1000)

    report = service.ingest_source(
        path=source_path,
        knowledge_type="document",
        canonical_key=f"document:artifacts-{uuid4().hex}",
    )

    assert report.status == "completed"
    table = db_session.scalars(select(TableArtifact).where(TableArtifact.version_id == report.version_id)).one()
    image = db_session.scalars(select(ImageArtifact).where(ImageArtifact.version_id == report.version_id)).one()
    chunks = db_session.scalars(select(Chunk).where(Chunk.version_id == report.version_id)).all()
    narrative = next(chunk for chunk in chunks if chunk.metadata_json["chunk_kind"] == "narrative")
    table_rows = next(chunk for chunk in chunks if chunk.metadata_json.get("chunk_kind") == "table_rows")
    image_summary = next(chunk for chunk in chunks if chunk.metadata_json.get("chunk_kind") == "image_summary")

    assert report.chunks_created == len(chunks)
    assert table.artifact_key == "tbl_001"
    assert table.locator == "line 5-8"
    assert table.column_names == ["Component", "Role"]
    assert table.rows[0] == {"Component": "Retriever", "Role": "Finds chunks"}
    assert "| Component | Role |" in table.normalized_markdown
    assert image.artifact_key == "img_001"
    assert image.locator == "line 12-12"
    assert image.original_uri == "images/rag.png"
    assert image.alt_text == "RAG architecture"
    assert image.asset_path is not None
    assert Path(image.asset_path).read_bytes() == b"fake-png"

    linked = narrative.metadata_json["linked_artifacts"]
    assert {item["artifact_type"] for item in linked} == {"table", "image"}
    assert {item["artifact_id"] for item in linked} == {table.id, image.id}
    assert "[Table tbl_001" in narrative.content
    assert "[Image img_001" in narrative.content
    assert table_rows.metadata_json["artifact_id"] == table.id
    assert table_rows.metadata_json["parent_narrative_chunk_id"] == narrative.id
    assert image_summary.metadata_json["artifact_id"] == image.id
    assert image_summary.metadata_json["parent_narrative_chunk_id"] == narrative.id


def test_ingest_markdown_image_enrichment_sidecar(db_session, tmp_path) -> None:
    assets_dir = tmp_path / "assets"
    assets_dir.mkdir()
    (assets_dir / "diagram.png").write_bytes(b"diagram")
    source_path = tmp_path / "document.md"
    source_path.write_text(
        "# Enriched Image\n\n"
        "The diagram explains the retrieval pipeline.\n\n"
        "![Retrieval architecture](assets/diagram.png)\n",
        encoding="utf-8",
    )
    (tmp_path / "image-enrichment.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "images": [
                    {
                        "asset_path": "assets/diagram.png",
                        "vision_summary": "A retrieval architecture diagram with search, ranking, and context assembly.",
                        "ocr_text": "Search -> Rank -> Context",
                        "visual_type": "diagram",
                        "key_elements": ["Search", "Rank", "Context"],
                        "confidence": "high",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    service = make_service(db_session, tmp_path / "raw", chunk_max_chars=1000)

    report = service.ingest_source(
        path=source_path,
        knowledge_type="document",
        canonical_key=f"document:enriched-image-{uuid4().hex}",
    )

    image = db_session.scalars(select(ImageArtifact).where(ImageArtifact.version_id == report.version_id)).one()
    version = db_session.get(SourceVersion, report.version_id)
    chunks = db_session.scalars(select(Chunk).where(Chunk.version_id == report.version_id)).all()
    image_summary = next(chunk for chunk in chunks if chunk.metadata_json.get("chunk_kind") == "image_summary")

    assert report.status == "completed"
    assert version is not None
    assert version.metadata_json["image_enrichment"]["status"] == "loaded"
    assert version.metadata_json["image_enrichment"]["entry_count"] == 1
    assert image.vision_summary == "A retrieval architecture diagram with search, ranking, and context assembly."
    assert image.ocr_text == "Search -> Rank -> Context"
    assert image.metadata_json["image_enrichment"] == {
        "status": "matched",
        "asset_path": "assets/diagram.png",
        "visual_type": "diagram",
        "key_elements": ["Search", "Rank", "Context"],
        "confidence": "high",
    }
    assert "Vision summary: A retrieval architecture diagram" in image_summary.content
    assert "OCR text: Search -> Rank -> Context" in image_summary.content
    assert "Visual type: diagram" in image_summary.content
    assert "Key elements: Search, Rank, Context" in image_summary.content


def test_ingest_invalid_image_enrichment_sidecar_degrades(db_session, tmp_path) -> None:
    assets_dir = tmp_path / "assets"
    assets_dir.mkdir()
    (assets_dir / "diagram.png").write_bytes(b"diagram")
    source_path = tmp_path / "document.md"
    source_path.write_text("# Invalid Sidecar\n\n![Diagram](assets/diagram.png)\n", encoding="utf-8")
    (tmp_path / "image-enrichment.json").write_text("{not-json", encoding="utf-8")
    service = make_service(db_session, tmp_path / "raw", chunk_max_chars=1000)

    report = service.ingest_source(
        path=source_path,
        knowledge_type="document",
        canonical_key=f"document:invalid-image-sidecar-{uuid4().hex}",
    )

    image = db_session.scalars(select(ImageArtifact).where(ImageArtifact.version_id == report.version_id)).one()
    version = db_session.get(SourceVersion, report.version_id)

    assert report.status == "completed"
    assert version is not None
    assert version.metadata_json["image_enrichment"]["status"] == "invalid"
    assert version.metadata_json["image_enrichment"]["issues"][0]["code"] == "invalid_image_enrichment_json"
    assert image.vision_summary is None
    assert image.ocr_text is None
    assert "image_enrichment" not in image.metadata_json


def test_ingest_per_image_enrichment_failure_degrades(db_session, tmp_path) -> None:
    assets_dir = tmp_path / "assets"
    assets_dir.mkdir()
    (assets_dir / "broken.png").write_bytes(b"broken")
    source_path = tmp_path / "document.md"
    source_path.write_text("# Failed Image\n\n![Broken](assets/broken.png)\n", encoding="utf-8")
    (tmp_path / "image-enrichment.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "images": [
                    {
                        "asset_path": "assets/broken.png",
                        "failure_code": "image_unreadable",
                        "failure_message": "image could not be decoded",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    service = make_service(db_session, tmp_path / "raw", chunk_max_chars=1000)

    report = service.ingest_source(
        path=source_path,
        knowledge_type="document",
        canonical_key=f"document:failed-image-enrichment-{uuid4().hex}",
    )

    image = db_session.scalars(select(ImageArtifact).where(ImageArtifact.version_id == report.version_id)).one()
    chunks = db_session.scalars(select(Chunk).where(Chunk.version_id == report.version_id)).all()
    image_summary = next(chunk for chunk in chunks if chunk.metadata_json.get("chunk_kind") == "image_summary")

    assert report.status == "completed"
    assert image.vision_summary is None
    assert image.ocr_text is None
    assert image.metadata_json["image_enrichment"] == {
        "status": "failed",
        "asset_path": "assets/broken.png",
        "failure_code": "image_unreadable",
        "failure_message": "image could not be decoded",
    }
    assert "Vision enrichment failed: image_unreadable" in image_summary.content


def test_ingest_markdown_common_image_syntax_artifacts(db_session, tmp_path) -> None:
    asset_dir = tmp_path / "images"
    asset_dir.mkdir()
    (asset_dir / "slope.png").write_bytes(b"slope")
    (asset_dir / "chart.png").write_bytes(b"chart")
    (asset_dir / "reference.png").write_bytes(b"reference")
    source_path = tmp_path / "image-syntax.md"
    source_path.write_text(
        "# Image Syntax\n\n"
        "> ![Calculate the slope](images/slope.png)\n\n"
        "[![ML for beginners - Understanding Linear Regression](https://img.youtube.com/vi/CRxFT8oTDMg/0.jpg)](https://youtu.be/CRxFT8oTDMg \"ML for beginners - Understanding Linear Regression\")\n\n"
        "> 🎥 Click the image above for a short video overview of linear regression.\n\n"
        "> Throughout this curriculum, we assume minimal knowledge of math.\n\n"
        "<img alt=\"Average price\" src=\"images/chart.png\" width=\"50%\"/>\n\n"
        "![Reference diagram][diagram]\n\n"
        "[diagram]: images/reference.png \"Reference diagram\"\n",
        encoding="utf-8",
    )
    service = make_service(db_session, tmp_path / "raw", chunk_max_chars=1000)

    report = service.ingest_source(
        path=source_path,
        knowledge_type="document",
        canonical_key=f"document:image-syntax-{uuid4().hex}",
    )

    images = db_session.scalars(
        select(ImageArtifact).where(ImageArtifact.version_id == report.version_id).order_by(ImageArtifact.artifact_key)
    ).all()
    assert report.status == "completed"
    assert [image.original_uri for image in images] == [
        "images/slope.png",
        "https://img.youtube.com/vi/CRxFT8oTDMg/0.jpg",
        "images/chart.png",
        "images/reference.png",
    ]
    assert [image.metadata_json["image_syntax"] for image in images] == [
        "blockquote_markdown_image",
        "linked_markdown_image",
        "html_img",
        "reference_image",
    ]
    assert images[0].asset_path is not None
    assert Path(images[0].asset_path).read_bytes() == b"slope"
    assert images[1].asset_path is None
    assert images[1].metadata_json["outer_link_url"] == "https://youtu.be/CRxFT8oTDMg"
    assert images[1].caption == "> 🎥 Click the image above for a short video overview of linear regression."
    assert images[1].nearby_text == "> Throughout this curriculum, we assume minimal knowledge of math."
    assert len(images[1].metadata_json["bound_block_ids"]) == 3
    assert images[2].metadata_json["html_attrs"]["width"] == "50%"
    assert Path(images[2].asset_path).read_bytes() == b"chart"
    assert images[3].metadata_json["reference_id"] == "diagram"

    chunks = db_session.scalars(select(Chunk).where(Chunk.version_id == report.version_id)).all()
    image_summaries = [chunk for chunk in chunks if chunk.metadata_json.get("chunk_kind") == "image_summary"]
    assert len(image_summaries) == 4
    linked_summary = next(chunk for chunk in image_summaries if chunk.metadata_json["artifact_key"] == "img_002")
    assert linked_summary.metadata_json["bound_block_ids"] == images[1].metadata_json["bound_block_ids"]


def test_ingest_duplicate_hash_skips_and_new_hash_creates_new_version(db_session, tmp_path) -> None:
    source_path = tmp_path / "versioned.md"
    source_path.write_text("# Versioned\n\nOriginal body.\n", encoding="utf-8")
    canonical_key = f"document:versioned-{uuid4().hex}"
    service = make_service(db_session, tmp_path / "raw")

    first = service.ingest_source(path=source_path, knowledge_type="document", canonical_key=canonical_key)
    duplicate = service.ingest_source(path=source_path, knowledge_type="document", canonical_key=canonical_key)
    source_path.write_text("# Versioned\n\nChanged body.\n", encoding="utf-8")
    changed = service.ingest_source(path=source_path, knowledge_type="document", canonical_key=canonical_key)

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

    report = service.ingest_source(path=root, knowledge_type="document")

    assert report.status == "completed_with_errors"
    assert len(report.succeeded) == 1
    assert len(report.failed) == 1
    assert len(report.skipped) == 2
    assert report.succeeded[0].input_name == "good.md"
    assert report.failed[0].input_name == "bad.md"
    assert {item.input_name for item in report.skipped} == {"ignore.bin", "nested"}


def test_ingest_without_canonical_key_uses_prefix_key_and_reads_archive_after_input_deleted(
    db_session,
    tmp_path,
) -> None:
    token = uuid4().hex
    source_path = tmp_path / "auto-key.md"
    source_path.write_text("# Auto Key\n\n" f"Raw archive keeps {token} readable.\n", encoding="utf-8")
    service = make_service(db_session, tmp_path / "raw")

    report = service.ingest_source(path=source_path, knowledge_type="document")
    job = db_session.get(IngestJob, report.ingest_job_id)
    source_path.unlink()
    search_service = SearchService(
        provider=PostgresFTSSearchProvider(session_factory=lambda: nullcontext(db_session)),
        default_top_k=10,
    )
    read_service = ReadSourceService(session_factory=lambda: nullcontext(db_session))
    context_pack_service = ContextPackService(
        search_service=search_service,
        read_source_service=read_service,
        default_top_k=10,
        max_evidence=10,
        max_evidence_per_source=3,
    )
    search_result = search_service.search_knowledge(query=token, top_k=1).results[0]
    fragment = read_service.read_source(chunk_id=search_result.chunk_id)
    context_pack = context_pack_service.get_context_pack(query=token, top_k=1)

    assert report.status == "completed"
    assert report.canonical_key is not None
    assert report.canonical_key.startswith("D")
    assert len(report.canonical_key) == 6
    assert report.canonical_key[1:].isdigit()
    assert report.succeeded[0].input_name == "auto-key.md"
    assert job is not None
    assert job.input_name == "auto-key.md"
    assert search_result.canonical_key == report.canonical_key
    assert token in fragment.content
    assert context_pack.evidence
    assert token in context_pack.evidence[0].content


def test_ingest_ai_conversation_transcript_and_jsonl_metadata(db_session, tmp_path) -> None:
    service = make_service(db_session, tmp_path / "raw")
    transcript = Path("tests/fixtures/conversations/support-thread.md")
    jsonl = Path("tests/fixtures/conversations/codex-session.jsonl")

    transcript_report = service.ingest_source(
        path=transcript,
        knowledge_type="ai_conversation",
        canonical_key=f"ai_conversation:transcript-{uuid4().hex}",
    )
    jsonl_report = service.ingest_source(
        path=jsonl,
        knowledge_type="ai_conversation",
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

    chunks = db_session.scalars(
        select(Chunk).where(Chunk.version_id == transcript_report.version_id).order_by(Chunk.chunk_index)
    ).all()
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
            "--knowledge-type",
            "document",
            "--canonical-key",
            f"document:cli-{uuid4().hex}",
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
            "knowledge_type": "document",
            "canonical_key": f"document:mcp-{uuid4().hex}",
        },
    )

    get_settings.cache_clear()
    assert "ingest_source" in tool_names
    body = json.loads(result[0].text)
    assert body["status"] == "completed"
    assert body["succeeded"][0]["chunks_created"] >= 1
