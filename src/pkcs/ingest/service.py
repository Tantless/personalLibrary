import hashlib
import logging
from collections.abc import Callable
from contextlib import AbstractContextManager
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from pkcs.config import Settings, get_settings
from pkcs.db.models import IngestJob, new_id
from pkcs.db.repositories import ChunkRepository, CitationRepository, IngestJobRepository, SourceRepository
from pkcs.db.session import create_session_factory
from pkcs.ingest.models import (
    SUPPORTED_EXTENSIONS,
    SUPPORTED_SOURCE_TYPES,
    IngestItemReport,
    IngestReport,
    canonical_key_for_path,
)
from pkcs.ingest.parsers import IngestParseError, parse_source_file
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
        source_type: str,
        canonical_key: str | None = None,
    ) -> IngestReport:
        self._reject_url(str(path))
        input_path = Path(path)
        self._validate_source_type(source_type)

        with self.session_factory() as session:
            job = IngestJobRepository(session).create_job(
                source_type=source_type,
                input_path=str(input_path),
            )
            session.commit()

            try:
                files, skipped = self._resolve_input_files(input_path, source_type, canonical_key)
            except Exception as exc:
                failed_item = IngestItemReport(input_path=str(input_path), status="failed", error=str(exc))
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
                        source_type=source_type,
                        canonical_key=canonical_key,
                    )
                    session.commit()
                except Exception as exc:
                    session.rollback()
                    item = IngestItemReport(input_path=str(file_path), status="failed", error=str(exc))
                    failed.append(item)
                    logger.exception(
                        "ingest_file_failed",
                        extra={"event": "ingest_file_failed", "path": str(file_path), "source_type": source_type},
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
                            "source_type": source_type,
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
                            "source_type": source_type,
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
        source_type: str,
        canonical_key: str | None,
    ) -> IngestItemReport:
        self._validate_file_extension(path, source_type)
        resolved_path = path.resolve()
        content_bytes = resolved_path.read_bytes()
        content_hash = hashlib.sha256(content_bytes).hexdigest()
        resolved_canonical_key = canonical_key or canonical_key_for_path(source_type, resolved_path)

        source_repo = SourceRepository(session)
        existing_source = source_repo.get_by_canonical_key(resolved_canonical_key)
        if existing_source is not None:
            existing_version = source_repo.get_version_by_hash(
                source_id=existing_source.id,
                content_hash=content_hash,
            )
            if existing_version is not None:
                return IngestItemReport(
                    input_path=str(path),
                    status="skipped",
                    source_id=existing_source.id,
                    version_id=existing_version.id,
                    canonical_key=resolved_canonical_key,
                    content_hash=content_hash,
                    error="duplicate content hash for canonical source",
                )

        parsed = parse_source_file(
            path=resolved_path,
            source_type=source_type,
            content_bytes=content_bytes,
            max_chars=self.chunk_max_chars,
            overlap_lines=self.chunk_overlap_lines,
        )

        created_new_source = existing_source is None
        source = existing_source or source_repo.create_source(
            canonical_key=resolved_canonical_key,
            title=parsed.title,
            source_type=source_type,
            origin_uri=resolved_path.as_posix(),
        )

        version_id = new_id()
        raw_archive_path = self.raw_archive_writer.write_bytes(
            source_type=source_type,
            source_id=source.id,
            version_id=version_id,
            original_path=resolved_path,
            content=content_bytes,
        )
        version = source_repo.create_version(
            source=source,
            version_id=version_id,
            content_hash=content_hash,
            file_path=resolved_path.as_posix(),
            raw_archive_path=raw_archive_path.as_posix(),
            metadata_json={
                **parsed.metadata_json,
                "canonical_key": resolved_canonical_key,
                "original_filename": resolved_path.name,
            },
        )

        chunk_repo = ChunkRepository(session)
        citation_repo = CitationRepository(session)
        for index, parsed_chunk in enumerate(parsed.chunks):
            chunk = chunk_repo.create_chunk(
                source_id=source.id,
                version_id=version.id,
                chunk_index=index,
                title=parsed_chunk.title,
                source_type=source_type,
                locator=parsed_chunk.locator,
                line_start=parsed_chunk.line_start,
                line_end=parsed_chunk.line_end,
                content=parsed_chunk.content,
                heading_path=parsed_chunk.heading_path,
                metadata_json=parsed_chunk.metadata_json,
            )
            citation_repo.create_citation(
                source_id=source.id,
                version_id=version.id,
                chunk_id=chunk.id,
                locator=parsed_chunk.locator,
                line_start=parsed_chunk.line_start,
                line_end=parsed_chunk.line_end,
                quote=parsed_chunk.content[:1000],
                metadata_json=parsed_chunk.metadata_json,
            )

        return IngestItemReport(
            input_path=str(path),
            status="succeeded",
            source_id=source.id,
            version_id=version.id,
            canonical_key=resolved_canonical_key,
            content_hash=content_hash,
            created_new_source=created_new_source,
            created_new_version=True,
            chunks_created=len(parsed.chunks),
        )

    def _resolve_input_files(
        self,
        input_path: Path,
        source_type: str,
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
                            input_path=str(child),
                            status="skipped",
                            error="recursive directory ingest is not supported",
                        )
                    )
                    continue
                if child.is_file() and child.suffix.lower() in SUPPORTED_EXTENSIONS[source_type]:
                    files.append(child)
                elif child.is_file():
                    skipped.append(
                        IngestItemReport(
                            input_path=str(child),
                            status="skipped",
                            error=f"unsupported extension for {source_type}: {child.suffix.lower()}",
                        )
                    )
            return files, skipped
        raise IngestInputError(f"input path does not exist: {input_path}")

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

    def _validate_source_type(self, source_type: str) -> None:
        if source_type not in SUPPORTED_SOURCE_TYPES:
            raise IngestInputError(f"unsupported source_type: {source_type}")

    def _validate_file_extension(self, path: Path, source_type: str) -> None:
        suffix = path.suffix.lower()
        if suffix not in SUPPORTED_EXTENSIONS[source_type]:
            raise IngestInputError(f"unsupported extension for {source_type}: {suffix}")

    def _reject_url(self, raw_path: str) -> None:
        if "://" in raw_path:
            raise IngestInputError("ingest_source accepts local file paths only")
