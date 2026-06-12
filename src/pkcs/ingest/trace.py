import hashlib
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from pkcs.config import Settings, get_settings
from pkcs.db.models import Chunk, Citation, ImageArtifact, Source, SourceVersion, TableArtifact
from pkcs.db.session import create_session_factory
from pkcs.ingest.models import ParsedChunk, ParsedImageArtifact, ParsedSource, ParsedTableArtifact
from pkcs.ingest.parsers import parse_source_file
from pkcs.ingest.service import IngestService, SessionFactory
from pkcs.source_metadata import (
    knowledge_type_code_for_name,
    normalized_format_code_for_source_format,
    normalized_format_name,
    source_format_code_for_path,
    source_format_name,
)
from pkcs.storage.raw_archive import RawArchiveWriter


class ArtifactIngestTraceInputError(ValueError):
    pass


class ArtifactIngestTraceService:
    def __init__(
        self,
        *,
        session_factory: SessionFactory,
        raw_archive_writer: RawArchiveWriter,
        chunk_max_chars: int,
        chunk_overlap_lines: int,
    ) -> None:
        self.session_factory = session_factory
        self.raw_archive_writer = raw_archive_writer
        self.chunk_max_chars = chunk_max_chars
        self.chunk_overlap_lines = chunk_overlap_lines

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> "ArtifactIngestTraceService":
        resolved_settings = settings or get_settings()
        return cls(
            session_factory=create_session_factory(resolved_settings.database_url),
            raw_archive_writer=RawArchiveWriter(resolved_settings.raw_archive_path),
            chunk_max_chars=resolved_settings.ingest_chunk_max_chars,
            chunk_overlap_lines=resolved_settings.ingest_chunk_overlap_lines,
        )

    def trace_ingest(
        self,
        *,
        path: Path | str,
        knowledge_type: str,
        canonical_key: str | None = None,
    ) -> dict[str, Any]:
        input_path = Path(path)
        if not input_path.is_file():
            raise ArtifactIngestTraceInputError("trace-ingest requires a single local file")

        resolved_path = input_path.resolve()
        content_bytes = resolved_path.read_bytes()
        source_format_code = source_format_code_for_path(resolved_path)
        normalized_format_code = normalized_format_code_for_source_format(source_format_code)
        knowledge_type_code = knowledge_type_code_for_name(knowledge_type)

        parsed = parse_source_file(
            path=resolved_path,
            knowledge_type=knowledge_type,
            content_bytes=content_bytes,
            max_chars=self.chunk_max_chars,
            overlap_lines=self.chunk_overlap_lines,
        )
        ingest = IngestService(
            session_factory=self.session_factory,
            raw_archive_writer=self.raw_archive_writer,
            chunk_max_chars=self.chunk_max_chars,
            chunk_overlap_lines=self.chunk_overlap_lines,
        )
        report = ingest.ingest_source(
            path=resolved_path,
            knowledge_type=knowledge_type,
            canonical_key=canonical_key,
        )

        return {
            "trace_version": "artifact_ingest_trace_v1",
            "design_delta": _design_delta(),
            "stage_order": [
                "input",
                "parser",
                "asset_resolution",
                "ingest_report",
                "database",
            ],
            "input": _input_trace(
                path=resolved_path,
                content_bytes=content_bytes,
                knowledge_type=knowledge_type,
                knowledge_type_code=knowledge_type_code,
                source_format_code=source_format_code,
                normalized_format_code=normalized_format_code,
            ),
            "parser": _parsed_source_trace(parsed),
            "asset_resolution": _asset_resolution_trace(source_path=resolved_path, parsed=parsed),
            "ingest_report": report.to_dict(),
            "database": self._database_trace(source_id=report.source_id, version_id=report.version_id),
        }

    def _database_trace(self, *, source_id: str | None, version_id: str | None) -> dict[str, Any]:
        if source_id is None or version_id is None:
            return {"available": False, "reason": "ingest did not produce source_id/version_id"}

        with self.session_factory() as session:
            source = session.get(Source, source_id)
            version = session.get(SourceVersion, version_id)
            if source is None or version is None:
                return {"available": False, "reason": "source/version not found after ingest"}

            table_artifacts = session.scalars(
                select(TableArtifact)
                .where(TableArtifact.version_id == version_id)
                .order_by(TableArtifact.artifact_key)
            ).all()
            image_artifacts = session.scalars(
                select(ImageArtifact)
                .where(ImageArtifact.version_id == version_id)
                .order_by(ImageArtifact.artifact_key)
            ).all()
            chunks = session.scalars(
                select(Chunk).where(Chunk.version_id == version_id).order_by(Chunk.chunk_index)
            ).all()
            citation_count = session.scalar(
                select(func.count(Citation.id)).where(Citation.version_id == version_id)
            )

        return {
            "available": True,
            "source": {
                "id": source.id,
                "canonical_key": source.canonical_key,
                "title": source.title,
                "knowledge_type_code": source.knowledge_type_code,
                "current_version_id": source.current_version_id,
            },
            "version": {
                "id": version.id,
                "version_number": version.version_number,
                "content_hash": version.content_hash,
                "source_format": source_format_name(version.source_format_code),
                "normalized_format": normalized_format_name(version.normalized_format_code),
                "raw_archive_path": version.raw_archive_path,
                "raw_archive_exists": Path(version.raw_archive_path).exists(),
                "metadata": version.metadata_json,
            },
            "table_artifacts": [_table_artifact_row_trace(artifact) for artifact in table_artifacts],
            "image_artifacts": [_image_artifact_row_trace(artifact) for artifact in image_artifacts],
            "chunks": [_chunk_row_trace(chunk) for chunk in chunks],
            "counts": {
                "table_artifacts": len(table_artifacts),
                "image_artifacts": len(image_artifacts),
                "chunks": len(chunks),
                "citations": citation_count or 0,
                "narrative_chunks": sum(1 for chunk in chunks if chunk.metadata_json.get("chunk_kind") == "narrative"),
                "table_derived_chunks": sum(
                    1 for chunk in chunks if chunk.metadata_json.get("artifact_type") == "table"
                ),
                "image_derived_chunks": sum(
                    1 for chunk in chunks if chunk.metadata_json.get("artifact_type") == "image"
                ),
            },
            "link_checks": _link_checks(chunks=chunks),
        }


def _input_trace(
    *,
    path: Path,
    content_bytes: bytes,
    knowledge_type: str,
    knowledge_type_code: int,
    source_format_code: int,
    normalized_format_code: int,
) -> dict[str, Any]:
    text = content_bytes.decode("utf-8-sig", errors="replace")
    return {
        "path": str(path),
        "input_name": path.name,
        "bytes": len(content_bytes),
        "sha256": hashlib.sha256(content_bytes).hexdigest(),
        "line_count": len(text.splitlines()),
        "knowledge_type": knowledge_type,
        "knowledge_type_code": knowledge_type_code,
        "source_format": source_format_name(source_format_code),
        "normalized_format": normalized_format_name(normalized_format_code),
    }


def _parsed_source_trace(parsed: ParsedSource) -> dict[str, Any]:
    return {
        "title": parsed.title,
        "knowledge_type": parsed.knowledge_type,
        "metadata": parsed.metadata_json,
        "counts": {
            "chunks": len(parsed.chunks),
            "narrative_chunks": sum(1 for chunk in parsed.chunks if chunk.metadata_json.get("chunk_kind") == "narrative"),
            "table_artifacts": len(parsed.table_artifacts),
            "image_artifacts": len(parsed.image_artifacts),
            "table_derived_chunks": sum(
                1 for chunk in parsed.chunks if chunk.metadata_json.get("artifact_type") == "table"
            ),
            "image_derived_chunks": sum(
                1 for chunk in parsed.chunks if chunk.metadata_json.get("artifact_type") == "image"
            ),
        },
        "table_artifacts": [_parsed_table_trace(artifact) for artifact in parsed.table_artifacts],
        "image_artifacts": [_parsed_image_trace(artifact) for artifact in parsed.image_artifacts],
        "chunks": [_parsed_chunk_trace(chunk) for chunk in parsed.chunks],
    }


def _parsed_table_trace(artifact: ParsedTableArtifact) -> dict[str, Any]:
    return {
        "artifact_key": artifact.artifact_key,
        "locator": artifact.locator,
        "line_start": artifact.line_start,
        "line_end": artifact.line_end,
        "heading_path": artifact.heading_path,
        "columns": artifact.columns,
        "row_count": len(artifact.rows),
        "row_preview": artifact.rows[:3],
        "summary": artifact.summary,
        "normalized_markdown_preview": _preview(artifact.normalized_markdown),
    }


def _parsed_image_trace(artifact: ParsedImageArtifact) -> dict[str, Any]:
    return {
        "artifact_key": artifact.artifact_key,
        "locator": artifact.locator,
        "line_start": artifact.line_start,
        "line_end": artifact.line_end,
        "heading_path": artifact.heading_path,
        "original_uri": artifact.original_uri,
        "alt_text": artifact.alt_text,
        "caption": artifact.caption,
        "nearby_text": artifact.nearby_text,
    }


def _parsed_chunk_trace(chunk: ParsedChunk) -> dict[str, Any]:
    metadata = dict(chunk.metadata_json)
    return {
        "chunk_key": chunk.chunk_key,
        "chunk_kind": metadata.get("chunk_kind"),
        "artifact_type": metadata.get("artifact_type"),
        "artifact_key": metadata.get("artifact_key"),
        "parent_narrative_chunk_key": metadata.get("parent_narrative_chunk_key"),
        "title": chunk.title,
        "locator": chunk.locator,
        "line_start": chunk.line_start,
        "line_end": chunk.line_end,
        "heading_path": chunk.heading_path,
        "linked_artifacts": metadata.get("linked_artifacts", []),
        "metadata": metadata,
        "content_preview": _preview(chunk.content),
    }


def _asset_resolution_trace(*, source_path: Path, parsed: ParsedSource) -> list[dict[str, Any]]:
    return [
        _image_asset_resolution(source_path=source_path, artifact=artifact)
        for artifact in parsed.image_artifacts
    ]


def _image_asset_resolution(*, source_path: Path, artifact: ParsedImageArtifact) -> dict[str, Any]:
    if _is_remote_or_data_uri(artifact.original_uri):
        return {
            "artifact_key": artifact.artifact_key,
            "original_uri": artifact.original_uri,
            "mode": "remote_or_data_uri",
            "candidate_path": None,
            "exists": False,
        }

    candidate = Path(artifact.original_uri)
    if not candidate.is_absolute():
        candidate = source_path.parent / candidate
    return {
        "artifact_key": artifact.artifact_key,
        "original_uri": artifact.original_uri,
        "mode": "local_file",
        "candidate_path": str(candidate.resolve()),
        "exists": candidate.exists() and candidate.is_file(),
    }


def _table_artifact_row_trace(artifact: TableArtifact) -> dict[str, Any]:
    return {
        "id": artifact.id,
        "artifact_key": artifact.artifact_key,
        "locator": artifact.locator,
        "line_start": artifact.line_start,
        "line_end": artifact.line_end,
        "heading_path": artifact.heading_path,
        "columns": artifact.column_names,
        "row_count": len(artifact.rows),
        "row_preview": artifact.rows[:3],
        "summary": artifact.summary,
        "metadata": artifact.metadata_json,
    }


def _image_artifact_row_trace(artifact: ImageArtifact) -> dict[str, Any]:
    return {
        "id": artifact.id,
        "artifact_key": artifact.artifact_key,
        "locator": artifact.locator,
        "line_start": artifact.line_start,
        "line_end": artifact.line_end,
        "heading_path": artifact.heading_path,
        "original_uri": artifact.original_uri,
        "asset_path": artifact.asset_path,
        "asset_exists": Path(artifact.asset_path).exists() if artifact.asset_path else False,
        "alt_text": artifact.alt_text,
        "caption": artifact.caption,
        "nearby_text": artifact.nearby_text,
        "ocr_text_present": bool(artifact.ocr_text),
        "vision_summary_present": bool(artifact.vision_summary),
        "metadata": artifact.metadata_json,
    }


def _chunk_row_trace(chunk: Chunk) -> dict[str, Any]:
    metadata = dict(chunk.metadata_json)
    return {
        "id": chunk.id,
        "chunk_index": chunk.chunk_index,
        "chunk_kind": metadata.get("chunk_kind"),
        "artifact_type": metadata.get("artifact_type"),
        "artifact_key": metadata.get("artifact_key"),
        "artifact_id": metadata.get("artifact_id"),
        "artifact_locator": metadata.get("artifact_locator"),
        "parent_narrative_chunk_id": metadata.get("parent_narrative_chunk_id"),
        "title": chunk.title,
        "locator": chunk.locator,
        "line_start": chunk.line_start,
        "line_end": chunk.line_end,
        "heading_path": chunk.heading_path,
        "linked_artifacts": metadata.get("linked_artifacts", []),
        "metadata": metadata,
        "content_preview": _preview(chunk.content),
    }


def _link_checks(*, chunks: list[Chunk]) -> dict[str, Any]:
    linked_refs = [
        ref
        for chunk in chunks
        for ref in chunk.metadata_json.get("linked_artifacts", [])
        if isinstance(ref, dict)
    ]
    artifact_chunks = [
        chunk for chunk in chunks if isinstance(chunk.metadata_json.get("artifact_type"), str)
    ]
    return {
        "linked_artifacts_count": len(linked_refs),
        "linked_artifacts_with_artifact_id": sum(1 for ref in linked_refs if ref.get("artifact_id")),
        "artifact_chunks_count": len(artifact_chunks),
        "artifact_chunks_with_artifact_id": sum(1 for chunk in artifact_chunks if chunk.metadata_json.get("artifact_id")),
        "artifact_chunks_with_parent_narrative_chunk_id": sum(
            1 for chunk in artifact_chunks if chunk.metadata_json.get("parent_narrative_chunk_id")
        ),
    }


def _design_delta() -> dict[str, Any]:
    return {
        "implemented": [
            "Markdown section scanning by heading.",
            "Implicit block stream via rendered entries.",
            "Atomic Markdown table and single-line image reference detection.",
            "Table/image parsed artifacts.",
            "Narrative placeholders plus metadata linked_artifacts.",
            "Artifact-derived chunks for retrieval.",
            "Database rows for table_artifacts and image_artifacts.",
            "Metadata ID resolution after artifact rows and narrative chunks are flushed.",
        ],
        "not_yet_implemented": [
            "Explicit public MarkdownBlock AST with text/table/image block classes.",
            "Large table row-group chunk splitting.",
            "Image OCR or vision summary enrichment.",
            "PDF/HTML/docx artifact extraction.",
        ],
    }


def _is_remote_or_data_uri(value: str) -> bool:
    return "://" in value or value.startswith(("data:", "mailto:"))


def _preview(value: str, limit: int = 240) -> str:
    compact = " ".join(value.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3] + "..."


__all__ = ["ArtifactIngestTraceInputError", "ArtifactIngestTraceService"]
