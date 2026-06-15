import json
import re
import shutil
import subprocess
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol


MARKDOWN_EXTENSIONS = {".md", ".markdown", ".mdx"}
DOCUMENT_EXTENSIONS_REQUIRING_DOCLING = {".pdf", ".docx", ".xlsx", ".html", ".htm"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".bmp", ".tiff", ".tif", ".avif"}
LARGE_TABLE_MAX_INLINE_ROWS = 20
LARGE_TABLE_MAX_INLINE_CHARS = 4000

_MARKDOWN_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\(([^)]*)\)")
_REFERENCE_DEFINITION_RE = re.compile(r"^(\s{0,3}\[([^\]]+)\]:\s*)(\S+)(.*)$")
_REFERENCE_IMAGE_RE = re.compile(r"!\[([^\]]+)\]\[([^\]]*)\]")
_SHORTCUT_REFERENCE_IMAGE_RE = re.compile(r"!\[([^\]]+)\](?![\[(])")
_HTML_IMG_SRC_RE = re.compile(r"(<img\b[^>]*?\bsrc=[\"'])([^\"']+)([\"'][^>]*>)", re.IGNORECASE)
_TABLE_SEPARATOR_RE = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$")


class PrepareIngestError(ValueError):
    pass


class DoclingRunner(Protocol):
    def __call__(self, *, input_path: Path, output_dir: Path, timeout_seconds: int) -> tuple[Path, str | None]:
        pass


@dataclass(frozen=True)
class PrepareIngestCounts:
    local_images: int = 0
    remote_images: int = 0
    missing_local_images: int = 0
    inline_tables: int = 0
    sidecar_tables: int = 0

    def to_dict(self) -> dict[str, int]:
        return asdict(self)


@dataclass(frozen=True)
class PrepareIngestIssue:
    code: str
    message: str
    step: str
    input_name: str | None = None
    detail: str | None = None

    def to_dict(self) -> dict[str, str]:
        payload = asdict(self)
        return {key: value for key, value in payload.items() if value is not None}


@dataclass(frozen=True)
class PrepareIngestStep:
    name: str
    status: str
    message: str | None = None

    def to_dict(self) -> dict[str, str]:
        payload = asdict(self)
        return {key: value for key, value in payload.items() if value is not None}


@dataclass(frozen=True)
class PrepareIngestReport:
    status: str
    prep_dir: str
    document_path: str | None
    source_info_path: str
    ingest_log_path: str
    counts: PrepareIngestCounts
    warnings: list[PrepareIngestIssue] = field(default_factory=list)
    errors: list[PrepareIngestIssue] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "prep_dir": self.prep_dir,
            "document_path": self.document_path,
            "source_info_path": self.source_info_path,
            "ingest_log_path": self.ingest_log_path,
            "counts": self.counts.to_dict(),
            "warnings": [warning.to_dict() for warning in self.warnings],
            "errors": [error.to_dict() for error in self.errors],
        }


@dataclass
class _NormalizationState:
    assets_dir: Path
    source_dir: Path
    used_asset_names: set[str] = field(default_factory=set)
    asset_paths_by_source: dict[Path, str] = field(default_factory=dict)
    asset_mappings: list[dict[str, str]] = field(default_factory=list)
    warnings: list[PrepareIngestIssue] = field(default_factory=list)
    reference_image_labels: set[str] = field(default_factory=set)
    local_images: int = 0
    remote_images: int = 0
    missing_local_images: int = 0


@dataclass(frozen=True)
class _TableNormalizationResult:
    markdown: str
    inline_tables: int
    sidecar_tables: int
    table_mappings: list[dict[str, Any]]


class PrepareIngestService:
    def __init__(self, *, docling_runner: DoclingRunner | None = None) -> None:
        self._docling_runner = docling_runner or self._run_docling_cli

    def prepare_source(
        self,
        *,
        path: Path | str,
        output_root: Path | str = Path("data/private/ingest-prep"),
        slug: str | None = None,
        timeout_seconds: int = 300,
        overwrite: bool = False,
    ) -> PrepareIngestReport:
        input_path = Path(path)
        output_root_path = Path(output_root)
        prep_dir = self._prepare_directory(
            output_root=output_root_path,
            input_path=input_path,
            slug=slug,
            overwrite=overwrite,
        )
        assets_dir = prep_dir / "assets"
        tables_dir = prep_dir / "tables"
        document_path = prep_dir / "document.md"
        source_info_path = prep_dir / "source-info.json"
        ingest_log_path = prep_dir / "ingest-log.json"
        assets_dir.mkdir(parents=True, exist_ok=True)
        tables_dir.mkdir(parents=True, exist_ok=True)

        steps: list[PrepareIngestStep] = []
        warnings: list[PrepareIngestIssue] = []
        errors: list[PrepareIngestIssue] = []
        counts = PrepareIngestCounts()
        table_mappings: list[dict[str, Any]] = []
        source_format = input_path.suffix.lower().lstrip(".")
        converter = "markdown-copy" if input_path.suffix.lower() in MARKDOWN_EXTENSIONS else "docling-cli"
        converter_version: str | None = None

        try:
            self._inspect_input(input_path)
            steps.append(PrepareIngestStep(name="inspect", status="success"))

            if input_path.suffix.lower() in MARKDOWN_EXTENSIONS:
                normalized_markdown, state = self._normalize_markdown(input_path=input_path, assets_dir=assets_dir)
                table_result = _normalize_tables(markdown=normalized_markdown, tables_dir=tables_dir)
                document_path.write_text(table_result.markdown, encoding="utf-8")
                table_mappings = table_result.table_mappings
                counts = PrepareIngestCounts(
                    local_images=state.local_images,
                    remote_images=state.remote_images,
                    missing_local_images=state.missing_local_images,
                    inline_tables=table_result.inline_tables,
                    sidecar_tables=table_result.sidecar_tables,
                )
                warnings.extend(state.warnings)
                asset_mappings = state.asset_mappings
                steps.append(PrepareIngestStep(name="convert", status="success", message="markdown copied"))
                steps.append(PrepareIngestStep(name="normalize_assets", status="success"))
                steps.append(PrepareIngestStep(name="normalize_tables", status="success"))
            elif input_path.suffix.lower() in DOCUMENT_EXTENSIONS_REQUIRING_DOCLING:
                docling_output_dir = prep_dir / "_docling"
                converted_markdown_path, converter_version = self._docling_runner(
                    input_path=input_path,
                    output_dir=docling_output_dir,
                    timeout_seconds=timeout_seconds,
                )
                normalized_markdown, state = self._normalize_markdown(
                    input_path=converted_markdown_path,
                    assets_dir=assets_dir,
                )
                table_result = _normalize_tables(markdown=normalized_markdown, tables_dir=tables_dir)
                document_path.write_text(table_result.markdown, encoding="utf-8")
                table_mappings = table_result.table_mappings
                counts = PrepareIngestCounts(
                    local_images=state.local_images,
                    remote_images=state.remote_images,
                    missing_local_images=state.missing_local_images,
                    inline_tables=table_result.inline_tables,
                    sidecar_tables=table_result.sidecar_tables,
                )
                warnings.extend(state.warnings)
                asset_mappings = state.asset_mappings
                steps.append(PrepareIngestStep(name="convert", status="success", message="docling-cli"))
                steps.append(PrepareIngestStep(name="normalize_assets", status="success"))
                steps.append(PrepareIngestStep(name="normalize_tables", status="success"))
                if docling_output_dir.exists():
                    shutil.rmtree(docling_output_dir)
            else:
                raise PrepareIngestError(f"unsupported prepare-ingest source format: {input_path.suffix.lower()}")

            self._validate_document(document_path)
            steps.append(PrepareIngestStep(name="validate", status="success"))
            status = "soft_fail" if counts.missing_local_images else "success"
        except Exception as exc:
            document_path_for_report = str(document_path) if document_path.exists() else None
            errors.append(
                PrepareIngestIssue(
                    code="prepare_ingest_failed",
                    message=str(exc),
                    step="prepare",
                    input_name=input_path.name or "input",
                )
            )
            steps.append(PrepareIngestStep(name="prepare", status="hard_fail", message=str(exc)))
            status = "hard_fail"
            asset_mappings = []
            self._write_source_info(
                source_info_path=source_info_path,
                input_path=input_path,
                source_format=source_format,
                converter=converter,
                converter_version=converter_version,
                timeout_seconds=timeout_seconds,
            )
            self._write_ingest_log(
                ingest_log_path=ingest_log_path,
                status=status,
                steps=steps,
                asset_mappings=asset_mappings,
                table_mappings=table_mappings,
                warnings=warnings,
                errors=errors,
            )
            return PrepareIngestReport(
                status=status,
                prep_dir=str(prep_dir),
                document_path=document_path_for_report,
                source_info_path=str(source_info_path),
                ingest_log_path=str(ingest_log_path),
                counts=counts,
                warnings=warnings,
                errors=errors,
            )

        self._write_source_info(
            source_info_path=source_info_path,
            input_path=input_path,
            source_format=source_format,
            converter=converter,
            converter_version=converter_version,
            timeout_seconds=timeout_seconds,
        )
        self._write_ingest_log(
            ingest_log_path=ingest_log_path,
            status=status,
            steps=steps,
            asset_mappings=asset_mappings,
            table_mappings=table_mappings,
            warnings=warnings,
            errors=errors,
        )
        return PrepareIngestReport(
            status=status,
            prep_dir=str(prep_dir),
            document_path=str(document_path),
            source_info_path=str(source_info_path),
            ingest_log_path=str(ingest_log_path),
            counts=counts,
            warnings=warnings,
            errors=errors,
        )

    def _inspect_input(self, input_path: Path) -> None:
        if "://" in str(input_path):
            raise PrepareIngestError("prepare-ingest accepts local file paths only")
        if not input_path.exists():
            raise PrepareIngestError("input path does not exist")
        if not input_path.is_file():
            raise PrepareIngestError("prepare-ingest accepts a single local file")

    def _normalize_markdown(self, *, input_path: Path, assets_dir: Path) -> tuple[str, _NormalizationState]:
        try:
            text = input_path.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError as exc:
            raise PrepareIngestError("input Markdown is not valid UTF-8") from exc

        state = _NormalizationState(
            assets_dir=assets_dir,
            source_dir=input_path.parent,
            reference_image_labels=_collect_reference_image_labels(text),
        )
        lines = []
        for line in text.splitlines(keepends=True):
            normalized_line = _MARKDOWN_IMAGE_RE.sub(
                lambda match: self._replace_markdown_image(match=match, state=state),
                line,
            )
            normalized_line = _REFERENCE_DEFINITION_RE.sub(
                lambda match: self._replace_reference_definition(match=match, state=state),
                normalized_line,
            )
            normalized_line = _HTML_IMG_SRC_RE.sub(
                lambda match: self._replace_html_img_src(match=match, state=state),
                normalized_line,
            )
            lines.append(normalized_line)
        return "".join(lines), state

    def _replace_markdown_image(self, *, match: re.Match[str], state: _NormalizationState) -> str:
        raw_destination = match.group(2)
        uri, suffix = _split_markdown_destination(raw_destination)
        normalized_uri = self._normalize_image_uri(uri=uri, state=state)
        return f"![{match.group(1)}]({normalized_uri}{suffix})"

    def _replace_reference_definition(self, *, match: re.Match[str], state: _NormalizationState) -> str:
        reference_label = _normalize_reference_label(match.group(2))
        raw_uri = match.group(3)
        uri = _strip_angle_destination(raw_uri)
        if reference_label not in state.reference_image_labels and not _has_image_extension(uri):
            return match.group(0)
        normalized_uri = self._normalize_image_uri(uri=uri, state=state)
        return f"{match.group(1)}{normalized_uri}{match.group(4)}"

    def _replace_html_img_src(self, *, match: re.Match[str], state: _NormalizationState) -> str:
        normalized_uri = self._normalize_image_uri(uri=match.group(2), state=state)
        return f"{match.group(1)}{normalized_uri}{match.group(3)}"

    def _normalize_image_uri(self, *, uri: str, state: _NormalizationState) -> str:
        if _is_remote_or_data_uri(uri):
            state.remote_images += 1
            return uri

        candidate = Path(uri)
        if not candidate.is_absolute():
            candidate = state.source_dir / candidate
        if not candidate.exists() or not candidate.is_file():
            state.missing_local_images += 1
            state.warnings.append(
                PrepareIngestIssue(
                    code="missing_local_image",
                    message="local image reference could not be resolved",
                    step="normalize_assets",
                    input_name=Path(uri).name or uri,
                    detail=str(candidate),
                )
            )
            return uri

        resolved_candidate = candidate.resolve()
        if resolved_candidate in state.asset_paths_by_source:
            normalized = state.asset_paths_by_source[resolved_candidate]
        else:
            asset_name = self._next_asset_name(candidate.name, state.used_asset_names)
            destination = state.assets_dir / asset_name
            shutil.copy2(candidate, destination)
            normalized = f"assets/{asset_name}"
            state.asset_paths_by_source[resolved_candidate] = normalized
        state.local_images += 1
        state.asset_mappings.append({"original": uri, "normalized": normalized})
        return normalized

    def _next_asset_name(self, filename: str, used_names: set[str]) -> str:
        path = Path(filename)
        stem = path.stem or "asset"
        suffix = path.suffix
        candidate = f"{stem}{suffix}"
        index = 2
        while candidate.lower() in used_names:
            candidate = f"{stem}-{index}{suffix}"
            index += 1
        used_names.add(candidate.lower())
        return candidate

    def _validate_document(self, document_path: Path) -> None:
        if not document_path.exists():
            raise PrepareIngestError("document.md was not created")
        if not document_path.read_text(encoding="utf-8-sig").strip():
            raise PrepareIngestError("document.md is empty")

    def _run_docling_cli(
        self,
        *,
        input_path: Path,
        output_dir: Path,
        timeout_seconds: int,
    ) -> tuple[Path, str | None]:
        output_dir.mkdir(parents=True, exist_ok=True)
        command = [
            "docling",
            "--to",
            "md",
            "--image-export-mode",
            "referenced",
            "--output",
            str(output_dir),
        ]
        if input_path.suffix.lower() in {".html", ".htm"}:
            command.extend(["--html-image-fetch", "local"])
        command.append(str(input_path))

        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                check=False,
            )
        except FileNotFoundError as exc:
            raise PrepareIngestError(
                "Docling CLI is not installed or not on PATH; install Docling and retry prepare-ingest"
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise PrepareIngestError(f"Docling conversion timed out after {timeout_seconds} seconds") from exc

        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "no output").strip().splitlines()
            short_detail = detail[-1] if detail else "no output"
            raise PrepareIngestError(f"Docling conversion failed: {short_detail[:500]}")

        markdown_outputs = sorted(output_dir.rglob("*.md"))
        if not markdown_outputs:
            raise PrepareIngestError("Docling conversion did not produce a Markdown file")
        return markdown_outputs[0], self._docling_version()

    def _docling_version(self) -> str | None:
        try:
            completed = subprocess.run(
                ["docling", "--version"],
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return None
        if completed.returncode != 0:
            return None
        return (completed.stdout or completed.stderr).strip() or None

    def _prepare_directory(
        self,
        *,
        output_root: Path,
        input_path: Path,
        slug: str | None,
        overwrite: bool,
    ) -> Path:
        output_root.mkdir(parents=True, exist_ok=True)
        base_slug = _slugify(slug or input_path.stem or "document")
        dated_slug = f"{datetime.now().date().isoformat()}-{base_slug}"
        candidate = output_root / dated_slug
        if overwrite and candidate.exists():
            shutil.rmtree(candidate)
        elif not overwrite:
            candidate = _available_directory(candidate)
        candidate.mkdir(parents=True, exist_ok=True)
        return candidate

    def _write_source_info(
        self,
        *,
        source_info_path: Path,
        input_path: Path,
        source_format: str,
        converter: str,
        converter_version: str | None,
        timeout_seconds: int,
    ) -> None:
        payload = {
            "source_kind": "local_file",
            "original_name": input_path.name or "input",
            "original_path_name": input_path.name or "input",
            "source_format": source_format,
            "normalized_format": "md",
            "converter": converter,
            "converter_version": converter_version,
            "prepared_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "timeout_seconds": timeout_seconds,
        }
        source_info_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _write_ingest_log(
        self,
        *,
        ingest_log_path: Path,
        status: str,
        steps: list[PrepareIngestStep],
        asset_mappings: list[dict[str, str]],
        table_mappings: list[dict[str, str]],
        warnings: list[PrepareIngestIssue],
        errors: list[PrepareIngestIssue],
    ) -> None:
        payload = {
            "status": status,
            "steps": [step.to_dict() for step in steps],
            "asset_mappings": asset_mappings,
            "table_mappings": table_mappings,
            "warnings": [warning.to_dict() for warning in warnings],
            "errors": [error.to_dict() for error in errors],
        }
        ingest_log_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _split_markdown_destination(raw_destination: str) -> tuple[str, str]:
    stripped = raw_destination.strip()
    if not stripped:
        return "", ""
    if stripped.startswith("<") and ">" in stripped:
        end_index = stripped.index(">")
        return stripped[1:end_index], stripped[end_index + 1 :]
    match = re.match(r"(\S+)(.*)", stripped, re.DOTALL)
    if match is None:
        return stripped, ""
    return match.group(1), match.group(2)


def _strip_angle_destination(uri: str) -> str:
    if uri.startswith("<") and uri.endswith(">"):
        return uri[1:-1]
    return uri


def _is_remote_or_data_uri(value: str) -> bool:
    return "://" in value or value.startswith(("data:", "mailto:", "#"))


def _looks_like_image_uri(value: str) -> bool:
    if _is_remote_or_data_uri(value):
        return True
    return _has_image_extension(value)


def _has_image_extension(value: str) -> bool:
    return Path(value).suffix.lower() in IMAGE_EXTENSIONS


def _collect_reference_image_labels(markdown: str) -> set[str]:
    labels: set[str] = set()
    for match in _REFERENCE_IMAGE_RE.finditer(markdown):
        alt_text = match.group(1).strip()
        explicit_label = match.group(2).strip()
        labels.add(_normalize_reference_label(explicit_label or alt_text))
    for match in _SHORTCUT_REFERENCE_IMAGE_RE.finditer(markdown):
        labels.add(_normalize_reference_label(match.group(1)))
    return labels


def _normalize_reference_label(value: str) -> str:
    return " ".join(value.strip().lower().split())


def _normalize_tables(*, markdown: str, tables_dir: Path) -> _TableNormalizationResult:
    lines = markdown.splitlines()
    output_lines: list[str] = []
    table_mappings: list[dict[str, Any]] = []
    inline_tables = 0
    sidecar_tables = 0
    table_index = 1
    index = 0
    while index < len(lines):
        if index + 1 >= len(lines) or "|" not in lines[index] or not _TABLE_SEPARATOR_RE.match(lines[index + 1]):
            output_lines.append(lines[index])
            index += 1
            continue

        table_start = index
        table_end = index + 2
        while table_end < len(lines) and lines[table_end].strip() and "|" in lines[table_end]:
            table_end += 1
        table_lines = lines[table_start:table_end]
        table_text = "\n".join(table_lines) + "\n"
        data_rows = max(0, len(table_lines) - 2)

        if data_rows > LARGE_TABLE_MAX_INLINE_ROWS or len(table_text) > LARGE_TABLE_MAX_INLINE_CHARS:
            sidecar_tables += 1
            table_filename = f"table-{sidecar_tables:03d}.md"
            table_path = tables_dir / table_filename
            table_path.write_text(table_text, encoding="utf-8")
            normalized_path = f"tables/{table_filename}"
            output_lines.append(f"Table: `{normalized_path}`")
            table_mappings.append(
                {
                    "original": f"table-{table_index:03d}",
                    "normalized": normalized_path,
                    "rows": data_rows,
                }
            )
        else:
            inline_tables += 1
            output_lines.extend(table_lines)
        table_index += 1
        index = table_end

    normalized_markdown = "\n".join(output_lines)
    if markdown.endswith("\n"):
        normalized_markdown += "\n"
    return _TableNormalizationResult(
        markdown=normalized_markdown,
        inline_tables=inline_tables,
        sidecar_tables=sidecar_tables,
        table_mappings=table_mappings,
    )


def _slugify(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip()).strip("-._")
    return normalized.lower() or "document"


def _available_directory(base_path: Path) -> Path:
    if not base_path.exists():
        return base_path
    index = 2
    while True:
        candidate = base_path.with_name(f"{base_path.name}-{index}")
        if not candidate.exists():
            return candidate
        index += 1
