import json
import re
import subprocess
from contextlib import nullcontext
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select
from typer.testing import CliRunner

from pkcs.cli import app as cli_app
from pkcs.config import get_settings
from pkcs.db.models import ImageArtifact, SourceVersion
from pkcs.ingest import IngestService, PrepareIngestService
from pkcs.ingest.normalization import _find_docling_executable
from pkcs.mcp.server import create_mcp_server
from pkcs.storage.raw_archive import RawArchiveWriter

_MARKDOWN_IMAGE_LINK_RE = re.compile(r"!\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")


def make_ingest_service(db_session, raw_root: Path) -> IngestService:
    return IngestService(
        session_factory=lambda: nullcontext(db_session),
        raw_archive_writer=RawArchiveWriter(raw_root),
        chunk_max_chars=1000,
        chunk_overlap_lines=1,
    )


def markdown_image_links(document_path: Path) -> list[str]:
    return _MARKDOWN_IMAGE_LINK_RE.findall(document_path.read_text(encoding="utf-8"))


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


def test_prepare_ingest_docling_runner_normalizes_converted_markdown(tmp_path) -> None:
    def fake_docling_runner(*, input_path: Path, output_dir: Path, timeout_seconds: int) -> tuple[Path, str]:
        artifact_dir = output_dir / "source_artifacts"
        artifact_dir.mkdir(parents=True)
        (artifact_dir / "figure.png").write_bytes(b"figure")
        output_path = output_dir / f"{input_path.stem}.md"
        output_path.write_text(
            "# Converted\n\n"
            "![Figure](source_artifacts/figure.png)\n\n"
            "| A | B |\n"
            "| --- | --- |\n"
            "| X | Y |\n",
            encoding="utf-8",
        )
        return output_path, "docling fake"

    source_path = tmp_path / "source.pdf"
    source_path.write_bytes(b"%PDF fake")

    report = PrepareIngestService(docling_runner=fake_docling_runner).prepare_source(
        path=source_path,
        output_root=tmp_path / "prep",
        slug="pdf-case",
    )

    body = report.to_dict()
    prep_dir = Path(body["prep_dir"])
    document = Path(body["document_path"]).read_text(encoding="utf-8")
    source_info = json.loads(Path(body["source_info_path"]).read_text(encoding="utf-8"))

    assert body["status"] == "success"
    assert body["counts"]["local_images"] == 1
    assert body["counts"]["inline_tables"] == 1
    assert "![Figure](assets/figure.png)" in document
    assert (prep_dir / "assets" / "figure.png").read_bytes() == b"figure"
    assert not (prep_dir / "_docling").exists()
    assert source_info["converter"] == "docling-cli"
    assert source_info["converter_version"] == "docling fake"


def test_prepare_ingest_docling_cli_uses_absolute_paths_and_pdf_fast_defaults(monkeypatch, tmp_path) -> None:
    source_path = tmp_path / "source.pdf"
    source_path.write_bytes(b"%PDF fake")
    output_dir = tmp_path / "prep" / "_docling"
    commands: list[list[str]] = []

    def fake_run(command, *, capture_output, text, timeout, check):
        commands.append(command)
        if len(command) == 2 and command[1] == "--version":
            return subprocess.CompletedProcess(command, 0, stdout="docling fake", stderr="")

        command_output_dir = Path(command[command.index("--output") + 1])
        command_output_dir.mkdir(parents=True, exist_ok=True)
        (command_output_dir / "source.md").write_text("# Converted\n", encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    converted_path, converter_version = PrepareIngestService()._run_docling_cli(
        input_path=source_path,
        output_dir=output_dir,
        timeout_seconds=123,
    )

    docling_command = commands[0]
    assert Path(docling_command[docling_command.index("--output") + 1]).is_absolute()
    assert Path(docling_command[-1]).is_absolute()
    assert "--no-ocr" in docling_command
    assert docling_command[docling_command.index("--table-mode") + 1] == "fast"
    assert converted_path == output_dir.resolve() / "source.md"
    assert converter_version == "docling fake"


def test_find_docling_executable_falls_back_to_uv_tool_bin(monkeypatch, tmp_path) -> None:
    local_bin = tmp_path / ".local" / "bin"
    local_bin.mkdir(parents=True)
    docling = local_bin / "docling.exe"
    docling.write_text("", encoding="utf-8")
    monkeypatch.setattr("pkcs.ingest.normalization.shutil.which", lambda name: None)
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))

    assert _find_docling_executable() == str(docling)


def test_prepare_ingest_xlsx_large_table_uses_sidecar(tmp_path) -> None:
    def fake_docling_runner(*, input_path: Path, output_dir: Path, timeout_seconds: int) -> tuple[Path, str]:
        output_dir.mkdir(parents=True)
        output_path = output_dir / f"{input_path.stem}.md"
        rows = "\n".join(f"| Row {index} | Value {index} |" for index in range(1, 23))
        output_path.write_text(
            "# Workbook\n\n"
            "| Name | Value |\n"
            "| --- | --- |\n"
            f"{rows}\n",
            encoding="utf-8",
        )
        return output_path, "docling fake"

    source_path = tmp_path / "workbook.xlsx"
    source_path.write_bytes(b"fake-xlsx")

    report = PrepareIngestService(docling_runner=fake_docling_runner).prepare_source(
        path=source_path,
        output_root=tmp_path / "prep",
        slug="xlsx-case",
    )

    body = report.to_dict()
    prep_dir = Path(body["prep_dir"])
    document = Path(body["document_path"]).read_text(encoding="utf-8")
    sidecar = prep_dir / "tables" / "table-001.md"
    ingest_log = json.loads(Path(body["ingest_log_path"]).read_text(encoding="utf-8"))

    assert body["status"] == "success"
    assert body["counts"]["inline_tables"] == 0
    assert body["counts"]["sidecar_tables"] == 1
    assert "Table: `tables/table-001.md`" in document
    assert "| Row 22 | Value 22 |" in sidecar.read_text(encoding="utf-8")
    assert ingest_log["table_mappings"] == [
        {"original": "table-001", "normalized": "tables/table-001.md", "rows": 22}
    ]


def test_prepare_ingest_docling_missing_reports_hard_fail(monkeypatch, tmp_path) -> None:
    source_path = tmp_path / "source.pdf"
    source_path.write_bytes(b"%PDF fake")
    monkeypatch.setenv("PATH", "")
    monkeypatch.setattr("pkcs.ingest.normalization._find_docling_executable", lambda: "docling")

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
    assert "Docling CLI is not installed" in body["errors"][0]["message"]


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
    version = db_session.get(SourceVersion, ingest_report.version_id)
    assert version is not None
    raw_document_path = Path(version.raw_archive_path)
    raw_image_links = markdown_image_links(raw_document_path)

    assert prepare_report.status == "success"
    assert ingest_report.status == "completed"
    assert image.original_uri == "assets/diagram.png"
    assert image.asset_path is not None
    assert Path(image.asset_path).read_bytes() == b"diagram"
    assert raw_image_links == ["assets/diagram.png"]
    assert [(raw_document_path.parent / link).exists() for link in raw_image_links] == [True]


async def test_prepared_markdown_package_can_be_ingested_through_mcp(
    monkeypatch,
    migrated_database_url,
    tmp_path,
) -> None:
    source_path = tmp_path / "mcp-package.md"
    source_path.write_text("# MCP Package\n\nPrepared Markdown reaches MCP ingest.\n", encoding="utf-8")
    prepare_report = PrepareIngestService().prepare_source(
        path=source_path,
        output_root=tmp_path / "prep",
        slug="mcp-case",
    )
    monkeypatch.setenv("PKCS_DATABASE_URL", migrated_database_url)
    monkeypatch.setenv("PKCS_RAW_ARCHIVE_PATH", str(tmp_path / "raw"))
    get_settings.cache_clear()

    try:
        server = create_mcp_server()
        result = await server.call_tool(
            "ingest_source",
            {
                "path": prepare_report.document_path,
                "knowledge_type": "document",
                "canonical_key": f"document:prepared-mcp-{uuid4().hex}",
            },
        )
    finally:
        get_settings.cache_clear()

    body = json.loads(result[0].text)
    assert prepare_report.status == "success"
    assert body["status"] == "completed"
    assert body["succeeded"][0]["chunks_created"] >= 1
