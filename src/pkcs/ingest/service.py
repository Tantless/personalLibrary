import hashlib
import logging
from collections.abc import Callable
from contextlib import AbstractContextManager
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from pkcs.config import Settings, get_settings
from pkcs.db.models import IngestJob, new_id
from pkcs.db.repositories import (
    ChunkRepository,
    CitationRepository,
    ImageArtifactRepository,
    IngestJobRepository,
    SourceKeyCounterRepository,
    SourceRepository,
    TableArtifactRepository,
)
from pkcs.db.session import create_session_factory
from pkcs.ingest.models import (
    SUPPORTED_EXTENSIONS,
    SUPPORTED_KNOWLEDGE_TYPES,
    IngestItemReport,
    IngestReport,
    ParsedSource,
)
from pkcs.ingest.parsers import IngestParseError, parse_source_file
from pkcs.source_metadata import (
    canonical_key_prefix_for_knowledge_type,
    knowledge_type_code_for_name,
    knowledge_type_name,
    normalized_format_code_for_source_format,
    normalized_format_name,
    source_format_code_for_path,
    source_format_name,
    validate_source_format_for_knowledge_type,
)
from pkcs.storage.raw_archive import RawArchiveWriter

SessionFactory = Callable[[], AbstractContextManager[Session]]

logger = logging.getLogger(__name__)


class IngestInputError(ValueError):
    pass


class IngestService:
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
    def from_settings(cls, settings: Settings | None = None) -> "IngestService":
        resolved_settings = settings or get_settings()
        return cls(
            session_factory=create_session_factory(resolved_settings.database_url),
            raw_archive_writer=RawArchiveWriter(resolved_settings.raw_archive_path),
            chunk_max_chars=resolved_settings.ingest_chunk_max_chars,
            chunk_overlap_lines=resolved_settings.ingest_chunk_overlap_lines,
        )

    def ingest_source(
        self,
        *,
        path: Path | str,
        knowledge_type: str,
        canonical_key: str | None = None,
    ) -> IngestReport:
        self._reject_url(str(path))
        input_path = Path(path)
        knowledge_type_code = self._validate_knowledge_type(knowledge_type)

        with self.session_factory() as session:
            job = IngestJobRepository(session).create_job(
                knowledge_type_code=knowledge_type_code,
                input_name=self._input_name(input_path),
            )
            session.commit()

            try:
                files, skipped = self._resolve_input_files(input_path, knowledge_type, canonical_key)
            except Exception as exc:
                failed_item = IngestItemReport(input_name=self._input_name(input_path), status="failed", error=str(exc))
                report = self._build_report(
                    job_id=job.id,
                    status="failed",
                    succeeded=[],
                    skipped=[],
                    failed=[failed_item],
                )
                self._finish_job(session, job, report, error_message=str(exc))
                return report

            succeeded: list[IngestItemReport] = []
            failed: list[IngestItemReport] = []

            for file_path in files:
                try:
                    item = self._ingest_file(
                        session=session,
                        path=file_path,
                        knowledge_type=knowledge_type,
                        knowledge_type_code=knowledge_type_code,
                        canonical_key=canonical_key,
                    )
                    session.commit()
                except Exception as exc:
                    session.rollback()
                    item = IngestItemReport(input_name=self._input_name(file_path), status="failed", error=str(exc))
                    failed.append(item)
                    logger.exception(
                        "ingest_file_failed",
                        extra={
                            "event": "ingest_file_failed",
                            "input_name": self._input_name(file_path),
                            "knowledge_type": knowledge_type,
                        },
                    )
                    continue

                if item.status == "succeeded":
                    succeeded.append(item)
                    logger.info(
                        "ingest_file_succeeded",
                        extra={
                            "event": "ingest_file_succeeded",
                            "source_id": item.source_id,
                            "version_id": item.version_id,
                            "knowledge_type": knowledge_type,
                            "chunks_created": item.chunks_created,
                        },
                    )
                else:
                    skipped.append(item)
                    logger.info(
                        "ingest_file_skipped",
                        extra={
                            "event": "ingest_file_skipped",
                            "source_id": item.source_id,
                            "version_id": item.version_id,
                            "knowledge_type": knowledge_type,
                            "reason": item.error,
                        },
                    )

            status = self._overall_status(succeeded=succeeded, skipped=skipped, failed=failed)
            report = self._build_report(
                job_id=job.id,
                status=status,
                succeeded=succeeded,
                skipped=skipped,
                failed=failed,
            )
            self._finish_job(
                session,
                job,
                report,
                error_message=f"{len(failed)} file(s) failed" if failed else None,
            )
            return report

    def _ingest_file(
        self,
        *,
        session: Session,
        path: Path,
        knowledge_type: str,
        knowledge_type_code: int,
        canonical_key: str | None,
    ) -> IngestItemReport:
        source_format_code = self._validate_file_extension(path, knowledge_type, knowledge_type_code)
        normalized_format_code = normalized_format_code_for_source_format(source_format_code)
        resolved_path = path.resolve()
        content_bytes = resolved_path.read_bytes()
        content_hash = hashlib.sha256(content_bytes).hexdigest()
        resolved_canonical_key = canonical_key or self._allocate_canonical_key(session, knowledge_type_code)

        source_repo = SourceRepository(session)
        existing_source = source_repo.get_by_canonical_key(resolved_canonical_key)
        if existing_source is not None:
            if existing_source.knowledge_type_code != knowledge_type_code:
                existing_knowledge_type = knowledge_type_name(existing_source.knowledge_type_code)
                raise IngestInputError(
                    f"canonical source knowledge_type mismatch: {existing_knowledge_type} != {knowledge_type}"
                )
            existing_version = source_repo.get_version_by_hash(
                source_id=existing_source.id,
                content_hash=content_hash,
            )
            if existing_version is not None:
                return IngestItemReport(
                    input_name=self._input_name(path),
                    status="skipped",
                    source_id=existing_source.id,
                    version_id=existing_version.id,
                    canonical_key=resolved_canonical_key,
                    content_hash=content_hash,
                    error="duplicate content hash for canonical source",
                )

        parsed = parse_source_file(
            path=resolved_path,
            knowledge_type=knowledge_type,
            content_bytes=content_bytes,
            max_chars=self.chunk_max_chars,
            overlap_lines=self.chunk_overlap_lines,
        )

        created_new_source = existing_source is None
        source = existing_source or source_repo.create_source(
            canonical_key=resolved_canonical_key,
            title=parsed.title,
            knowledge_type_code=knowledge_type_code,
        )

        version_id = new_id()
        raw_archive_path = self.raw_archive_writer.write_bytes(
            knowledge_type=knowledge_type,
            source_id=source.id,
            version_id=version_id,
            original_path=resolved_path,
            content=content_bytes,
        )
        version = source_repo.create_version(
            source=source,
            version_id=version_id,
            content_hash=content_hash,
            source_format_code=source_format_code,
            normalized_format_code=normalized_format_code,
            raw_archive_path=raw_archive_path.as_posix(),
            metadata_json={
                **parsed.metadata_json,
                "canonical_key": resolved_canonical_key,
                "input_name": resolved_path.name,
                "source_format": source_format_name(source_format_code),
                "normalized_format": normalized_format_name(normalized_format_code),
                "knowledge_type": knowledge_type,
            },
        )

        table_artifacts_by_key = self._create_table_artifacts(
            session=session,
            parsed=parsed,
            source_id=source.id,
            version_id=version.id,
        )
        image_artifacts_by_key = self._create_image_artifacts(
            session=session,
            parsed=parsed,
            source_id=source.id,
            version_id=version.id,
            source_path=resolved_path,
            knowledge_type=knowledge_type,
        )
        artifacts_by_type_and_key = {
            "table": table_artifacts_by_key,
            "image": image_artifacts_by_key,
        }

        chunk_repo = ChunkRepository(session)
        citation_repo = CitationRepository(session)
        chunk_ids_by_key: dict[str, str] = {}
        for index, parsed_chunk in enumerate(parsed.chunks):
            chunk_metadata = self._chunk_metadata_with_artifact_refs(
                metadata_json=parsed_chunk.metadata_json,
                artifacts_by_type_and_key=artifacts_by_type_and_key,
                chunk_ids_by_key=chunk_ids_by_key,
            )
            chunk = chunk_repo.create_chunk(
                source_id=source.id,
                version_id=version.id,
                chunk_index=index,
                title=parsed_chunk.title,
                source_format_code=source_format_code,
                normalized_format_code=normalized_format_code,
                knowledge_type_code=knowledge_type_code,
                locator=parsed_chunk.locator,
                line_start=parsed_chunk.line_start,
                line_end=parsed_chunk.line_end,
                content=parsed_chunk.content,
                heading_path=parsed_chunk.heading_path,
                metadata_json=chunk_metadata,
            )
            if parsed_chunk.chunk_key is not None:
                chunk_ids_by_key[parsed_chunk.chunk_key] = chunk.id
            citation_repo.create_citation(
                source_id=source.id,
                version_id=version.id,
                chunk_id=chunk.id,
                locator=parsed_chunk.locator,
                line_start=parsed_chunk.line_start,
                line_end=parsed_chunk.line_end,
                quote=parsed_chunk.content[:1000],
                metadata_json=chunk_metadata,
            )

        return IngestItemReport(
            input_name=self._input_name(path),
            status="succeeded",
            source_id=source.id,
            version_id=version.id,
            canonical_key=resolved_canonical_key,
            content_hash=content_hash,
            created_new_source=created_new_source,
            created_new_version=True,
            chunks_created=len(parsed.chunks),
        )

    def _create_table_artifacts(
        self,
        *,
        session: Session,
        parsed: ParsedSource,
        source_id: str,
        version_id: str,
    ) -> dict[str, str]:
        table_repo = TableArtifactRepository(session)
        artifacts_by_key: dict[str, str] = {}
        for artifact in parsed.table_artifacts:
            row = table_repo.create_table_artifact(
                source_id=source_id,
                version_id=version_id,
                artifact_key=artifact.artifact_key,
                locator=artifact.locator,
                line_start=artifact.line_start,
                line_end=artifact.line_end,
                heading_path=artifact.heading_path,
                columns=artifact.columns,
                rows=artifact.rows,
                normalized_markdown=artifact.normalized_markdown,
                summary=artifact.summary,
                metadata_json={
                    **artifact.metadata_json,
                    "artifact_key": artifact.artifact_key,
                    "artifact_type": "table",
                },
            )
            artifacts_by_key[artifact.artifact_key] = row.id
        return artifacts_by_key

    def _create_image_artifacts(
        self,
        *,
        session: Session,
        parsed: ParsedSource,
        source_id: str,
        version_id: str,
        source_path: Path,
        knowledge_type: str,
    ) -> dict[str, str]:
        image_repo = ImageArtifactRepository(session)
        artifacts_by_key: dict[str, str] = {}
        for artifact in parsed.image_artifacts:
            asset_path = self._archive_image_asset(
                knowledge_type=knowledge_type,
                source_id=source_id,
                version_id=version_id,
                artifact_key=artifact.artifact_key,
                source_path=source_path,
                original_uri=artifact.original_uri,
            )
            row = image_repo.create_image_artifact(
                source_id=source_id,
                version_id=version_id,
                artifact_key=artifact.artifact_key,
                locator=artifact.locator,
                line_start=artifact.line_start,
                line_end=artifact.line_end,
                heading_path=artifact.heading_path,
                original_uri=artifact.original_uri,
                asset_path=asset_path,
                alt_text=artifact.alt_text,
                caption=artifact.caption,
                nearby_text=artifact.nearby_text,
                metadata_json={
                    **artifact.metadata_json,
                    "artifact_key": artifact.artifact_key,
                    "artifact_type": "image",
                    "asset_copied": asset_path is not None,
                },
            )
            artifacts_by_key[artifact.artifact_key] = row.id
        return artifacts_by_key

    def _archive_image_asset(
        self,
        *,
        knowledge_type: str,
        source_id: str,
        version_id: str,
        artifact_key: str,
        source_path: Path,
        original_uri: str,
    ) -> str | None:
        if self._is_remote_or_data_uri(original_uri):
            return None
        candidate = Path(original_uri)
        if not candidate.is_absolute():
            candidate = source_path.parent / candidate
        if not candidate.exists() or not candidate.is_file():
            return None
        return self.raw_archive_writer.write_asset(
            knowledge_type=knowledge_type,
            source_id=source_id,
            version_id=version_id,
            artifact_key=artifact_key,
            original_path=candidate,
        ).as_posix()

    def _chunk_metadata_with_artifact_refs(
        self,
        *,
        metadata_json: dict[str, Any],
        artifacts_by_type_and_key: dict[str, dict[str, str]],
        chunk_ids_by_key: dict[str, str],
    ) -> dict[str, Any]:
        metadata = dict(metadata_json)
        if "linked_artifacts" in metadata:
            metadata["linked_artifacts"] = [
                self._artifact_ref_with_id(ref, artifacts_by_type_and_key)
                for ref in metadata["linked_artifacts"]
            ]

        artifact_type = metadata.get("artifact_type")
        artifact_key = metadata.get("artifact_key")
        if isinstance(artifact_type, str) and isinstance(artifact_key, str):
            artifact_id = artifacts_by_type_and_key.get(artifact_type, {}).get(artifact_key)
            if artifact_id is not None:
                metadata["artifact_id"] = artifact_id

        parent_key = metadata.get("parent_narrative_chunk_key")
        if isinstance(parent_key, str):
            parent_id = chunk_ids_by_key.get(parent_key)
            if parent_id is not None:
                metadata["parent_narrative_chunk_id"] = parent_id
        return metadata

    def _artifact_ref_with_id(
        self,
        ref: dict[str, Any],
        artifacts_by_type_and_key: dict[str, dict[str, str]],
    ) -> dict[str, Any]:
        resolved = dict(ref)
        artifact_type = resolved.get("artifact_type")
        artifact_key = resolved.get("artifact_key")
        if isinstance(artifact_type, str) and isinstance(artifact_key, str):
            artifact_id = artifacts_by_type_and_key.get(artifact_type, {}).get(artifact_key)
            if artifact_id is not None:
                resolved["artifact_id"] = artifact_id
        return resolved

    def _is_remote_or_data_uri(self, value: str) -> bool:
        return "://" in value or value.startswith(("data:", "mailto:"))

    def _resolve_input_files(
        self,
        input_path: Path,
        knowledge_type: str,
        canonical_key: str | None,
    ) -> tuple[list[Path], list[IngestItemReport]]:
        if input_path.is_file():
            return [input_path], []
        if input_path.is_dir():
            if canonical_key is not None:
                raise IngestInputError("canonical_key is only supported for single-file ingest")
            files: list[Path] = []
            skipped: list[IngestItemReport] = []
            for child in sorted(input_path.iterdir(), key=lambda item: item.name):
                if child.is_dir():
                    skipped.append(
                        IngestItemReport(
                            input_name=self._input_name(child),
                            status="skipped",
                            error="recursive directory ingest is not supported",
                        )
                    )
                    continue
                if child.is_file() and child.suffix.lower() in SUPPORTED_EXTENSIONS[knowledge_type]:
                    files.append(child)
                elif child.is_file():
                    skipped.append(
                        IngestItemReport(
                            input_name=self._input_name(child),
                            status="skipped",
                            error=f"unsupported extension for {knowledge_type}: {child.suffix.lower()}",
                        )
                    )
            return files, skipped
        raise IngestInputError("input path does not exist")

    def _finish_job(
        self,
        session: Session,
        job: IngestJob,
        report: IngestReport,
        *,
        error_message: str | None,
    ) -> None:
        persisted_job = session.get(IngestJob, job.id) or job
        IngestJobRepository(session).finish_job(
            persisted_job,
            status=report.status,
            summary_json=report.to_dict(),
            error_message=error_message,
        )
        session.commit()

    def _build_report(
        self,
        *,
        job_id: str,
        status: str,
        succeeded: list[IngestItemReport],
        skipped: list[IngestItemReport],
        failed: list[IngestItemReport],
    ) -> IngestReport:
        primary = (succeeded or skipped or failed or [None])[0]
        chunks_created = sum(item.chunks_created for item in succeeded)
        return IngestReport(
            ingest_job_id=job_id,
            status=status,
            source_id=primary.source_id if primary else None,
            version_id=primary.version_id if primary else None,
            canonical_key=primary.canonical_key if primary else None,
            content_hash=primary.content_hash if primary else None,
            created_new_source=primary.created_new_source if primary else False,
            created_new_version=primary.created_new_version if primary else False,
            chunks_created=chunks_created,
            succeeded=succeeded,
            skipped=skipped,
            failed=failed,
        )

    def _overall_status(
        self,
        *,
        succeeded: list[IngestItemReport],
        skipped: list[IngestItemReport],
        failed: list[IngestItemReport],
    ) -> str:
        if failed and not succeeded and not skipped:
            return "failed"
        if failed:
            return "completed_with_errors"
        if succeeded:
            return "completed"
        if skipped:
            return "skipped"
        return "completed"

    def _validate_knowledge_type(self, knowledge_type: str) -> int:
        if knowledge_type not in SUPPORTED_KNOWLEDGE_TYPES:
            raise IngestInputError(f"unsupported knowledge_type: {knowledge_type}")
        try:
            return knowledge_type_code_for_name(knowledge_type)
        except ValueError as exc:
            raise IngestInputError(str(exc)) from exc

    def _validate_file_extension(self, path: Path, knowledge_type: str, knowledge_type_code: int) -> int:
        try:
            source_format_code = source_format_code_for_path(path)
            validate_source_format_for_knowledge_type(
                source_format_code=source_format_code,
                knowledge_type_code=knowledge_type_code,
            )
        except ValueError as exc:
            raise IngestInputError(str(exc)) from exc
        return source_format_code

    def _reject_url(self, raw_path: str) -> None:
        if "://" in raw_path:
            raise IngestInputError("ingest_source accepts local file paths only")

    def _allocate_canonical_key(self, session: Session, knowledge_type_code: int) -> str:
        prefix = canonical_key_prefix_for_knowledge_type(knowledge_type_code)
        return SourceKeyCounterRepository(session).allocate(prefix)

    def _input_name(self, path: Path | str) -> str:
        return Path(path).name or "input"
