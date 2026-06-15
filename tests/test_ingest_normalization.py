import json
from contextlib import nullcontext
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select
from typer.testing import CliRunner

from pkcs.cli import app as cli_app
from pkcs.db.models import ImageArtifact
from pkcs.ingest import IngestService, PrepareIngestService
from pkcs.storage.raw_archive import RawArchiveWriter


def make_ingest_service(db_session, raw_root: Path) -> IngestService:
    return IngestService(
        session_factory=lambda: nullcontext(db_session),
        raw_archive_writer=RawArchiveWriter(raw_root),
        chunk_max_chars=1000,
        chunk_overlap_lines=1,
    )


def test_prepare_ingest_markdown_package_normalizes_local_assets(tmp_path) -> None:
    source_dir = tmp_path / "source"
    (source_dir / "images").mkdir(parents=True)
    (source_dir / "more").mkdir()
    (source_dir / "images" / "logo.png").write_bytes(b"logo")
    (source_dir / "more" / "logo.png").write_bytes(b"other-logo")
    source_path = source_dir / "notes.md"
    source_path.write_text(
        "# Notes\n\n"
        "![Logo](images/logo.png \"Logo\")\n\n"
        "[![Thumb](more/logo.png)](https://example.com/video)\n\n"
        "![Remote](https://example.com/remote.png)\n\n"
        "<img alt=\"Logo again\" src=\"images/logo.png\"/>\n\n"
        "![Reference][diagram]\n\n"
        "[diagram]: images/logo.png \"Reference\"\n"
        "[docs]: https://example.com/docs\n\n"
        "| A | B |\n"
        "| --- | --- |\n"
        "| X | Y |\n",
        encoding="utf-8",
    )

    report = PrepareIngestService().prepare_source(
        path=source_path,
        output_root=tmp_path / "prep",
        slug="asset-case",
    )

    body = report.to_dict()
    prep_dir = Path(body["prep_dir"])
    document_path = Path(body["document_path"])
    document = document_path.read_text(encoding="utf-8")
    ingest_log = json.loads(Path(body["ingest_log_path"]).read_text(encoding="utf-8"))
    source_info = json.loads(Path(body["source_info_path"]).read_text(encoding="utf-8"))

    assert body["status"] == "success"
    assert body["counts"] == {
        "local_images": 4,
        "remote_images": 1,
        "missing_local_images": 0,
        "inline_tables": 1,
        "sidecar_tables": 0,
    }
    assert prep_dir.name.endswith("asset-case")
    assert "![Logo](assets/logo.png \"Logo\")" in document
    assert "[![Thumb](assets/logo-2.png)](https://example.com/video)" in document
    assert "![Remote](https://example.com/remote.png)" in document
    assert '<img alt="Logo again" src="assets/logo.png"/>' in document
    assert '[diagram]: assets/logo.png "Reference"' in document
    assert "[docs]: https://example.com/docs" in document
    assert (prep_dir / "assets" / "logo.png").read_bytes() == b"logo"
    assert (prep_dir / "assets" / "logo-2.png").read_bytes() == b"other-logo"
    assert source_info["converter"] == "markdown-copy"
    assert source_info["source_format"] == "md"
    assert ingest_log["status"] == "success"
    assert len(ingest_log["asset_mappings"]) == 4


def test_prepare_ingest_missing_local_image_is_soft_fail(tmp_path) -> None:
    source_path = tmp_path / "missing.md"
    source_path.write_text("# Missing\n\n![Missing](images/missing.png)\n", encoding="utf-8")

    report = PrepareIngestService().prepare_source(
        path=source_path,
        output_root=tmp_path / "prep",
        slug="missing-case",
    )

    body = report.to_dict()
    document = Path(body["document_path"]).read_text(encoding="utf-8")

    assert body["status"] == "soft_fail"
    assert body["counts"]["missing_local_images"] == 1
    assert body["warnings"][0]["code"] == "missing_local_image"
    assert "![Missing](images/missing.png)" in document


def test_prepare_ingest_cli_outputs_json_report(tmp_path) -> None:
    source_path = tmp_path / "cli.md"
    source_path.write_text("# CLI\n\nPrepare this Markdown file.\n", encoding="utf-8")

    result = CliRunner().invoke(
        cli_app,
        [
            "prepare-ingest",
            str(source_path),
            "--output-root",
            str(tmp_path / "prep"),
            "--slug",
            "cli-case",
        ],
    )

    assert result.exit_code == 0
    body = json.loads(result.stdout)
    assert body["status"] == "success"
    assert Path(body["document_path"]).exists()
    assert Path(body["source_info_path"]).exists()
    assert Path(body["ingest_log_path"]).exists()


def test_prepare_ingest_non_markdown_reports_hard_fail_until_docling_adapter_exists(tmp_path) -> None:
    source_path = tmp_path / "source.pdf"
    source_path.write_bytes(b"%PDF fake")

    result = CliRunner().invoke(
        cli_app,
        [
            "prepare-ingest",
            str(source_path),
            "--output-root",
            str(tmp_path / "prep"),
            "--slug",
            "pdf-case",
        ],
    )

    body = json.loads(result.stdout)
    assert result.exit_code == 1
    assert body["status"] == "hard_fail"
    assert body["document_path"] is None
    assert body["errors"][0]["code"] == "prepare_ingest_failed"


def test_prepared_markdown_package_can_be_ingested(db_session, tmp_path) -> None:
    source_dir = tmp_path / "source"
    (source_dir / "images").mkdir(parents=True)
    (source_dir / "images" / "diagram.png").write_bytes(b"diagram")
    source_path = source_dir / "package.md"
    source_path.write_text(
        "# Prepared Package\n\n"
        "The prepared package keeps image assets local.\n\n"
        "![Diagram](images/diagram.png)\n",
        encoding="utf-8",
    )
    prepare_report = PrepareIngestService().prepare_source(
        path=source_path,
        output_root=tmp_path / "prep",
        slug="ingest-case",
    )
    document_path = Path(prepare_report.document_path or "")

    ingest_report = make_ingest_service(db_session, tmp_path / "raw").ingest_source(
        path=document_path,
        knowledge_type="document",
        canonical_key=f"document:prepared-{uuid4().hex}",
    )

    image = db_session.scalars(select(ImageArtifact).where(ImageArtifact.version_id == ingest_report.version_id)).one()
    assert prepare_report.status == "success"
    assert ingest_report.status == "completed"
    assert image.original_uri == "assets/diagram.png"
    assert image.asset_path is not None
    assert Path(image.asset_path).read_bytes() == b"diagram"
