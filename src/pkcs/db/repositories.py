from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from pkcs.db.models import Chunk, Citation, IngestJob, Source, SourceVersion


class SourceRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_by_canonical_key(self, canonical_key: str) -> Source | None:
        return self.session.scalar(select(Source).where(Source.canonical_key == canonical_key))

    def get(self, source_id: str) -> Source | None:
        return self.session.get(Source, source_id)

    def get_version_by_hash(self, *, source_id: str, content_hash: str) -> SourceVersion | None:
        return self.session.scalar(
            select(SourceVersion).where(
                SourceVersion.source_id == source_id,
                SourceVersion.content_hash == content_hash,
            )
        )

    def get_version(self, *, source_id: str, version_id: str) -> SourceVersion | None:
        return self.session.scalar(
            select(SourceVersion).where(
                SourceVersion.source_id == source_id,
                SourceVersion.id == version_id,
            )
        )

    def create_source(
        self,
        *,
        canonical_key: str,
        title: str,
        source_type: str,
        origin_uri: str | None = None,
    ) -> Source:
        source = Source(
            canonical_key=canonical_key,
            title=title,
            source_type=source_type,
            origin_uri=origin_uri,
        )
        self.session.add(source)
        self.session.flush()
        return source

    def create_version(
        self,
        *,
        source: Source,
        content_hash: str,
        file_path: str,
        raw_archive_path: str,
        version_id: str | None = None,
        status: str = "imported",
        metadata_json: dict[str, Any] | None = None,
    ) -> SourceVersion:
        version_number = len(source.versions) + 1
        supersedes_version_id = source.current_version_id
        version_kwargs: dict[str, Any] = {}
        if version_id is not None:
            version_kwargs["id"] = version_id
        version = SourceVersion(
            **version_kwargs,
            source_id=source.id,
            version_number=version_number,
            content_hash=content_hash,
            file_path=file_path,
            raw_archive_path=raw_archive_path,
            status=status,
            supersedes_version_id=supersedes_version_id,
            metadata_json=metadata_json or {},
        )
        self.session.add(version)
        self.session.flush()
        source.current_version_id = version.id
        self.session.flush()
        return version


class ChunkRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create_chunk(
        self,
        *,
        source_id: str,
        version_id: str,
        chunk_index: int,
        title: str,
        source_type: str,
        locator: str,
        line_start: int,
        line_end: int,
        content: str,
        heading_path: list[str] | None = None,
        token_count: int | None = None,
        metadata_json: dict[str, Any] | None = None,
    ) -> Chunk:
        chunk = Chunk(
            source_id=source_id,
            version_id=version_id,
            chunk_index=chunk_index,
            title=title,
            source_type=source_type,
            locator=locator,
            line_start=line_start,
            line_end=line_end,
            content=content,
            heading_path=heading_path or [],
            token_count=token_count,
            metadata_json=metadata_json or {},
        )
        self.session.add(chunk)
        self.session.flush()
        return chunk

    def get(self, chunk_id: str) -> Chunk | None:
        return self.session.get(Chunk, chunk_id)

    def get_by_locator(self, *, source_id: str, version_id: str, locator: str) -> Chunk | None:
        return self.session.scalar(
            select(Chunk).where(
                Chunk.source_id == source_id,
                Chunk.version_id == version_id,
                Chunk.locator == locator,
            )
        )


class CitationRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create_citation(
        self,
        *,
        source_id: str,
        version_id: str,
        chunk_id: str,
        locator: str,
        line_start: int,
        line_end: int,
        quote: str | None = None,
        metadata_json: dict[str, Any] | None = None,
    ) -> Citation:
        citation = Citation(
            source_id=source_id,
            version_id=version_id,
            chunk_id=chunk_id,
            locator=locator,
            line_start=line_start,
            line_end=line_end,
            quote=quote,
            metadata_json=metadata_json or {},
        )
        self.session.add(citation)
        self.session.flush()
        return citation


class IngestJobRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create_job(
        self,
        *,
        source_type: str,
        input_path: str,
        status: str = "started",
        summary_json: dict[str, Any] | None = None,
    ) -> IngestJob:
        job = IngestJob(
            source_type=source_type,
            input_path=input_path,
            status=status,
            summary_json=summary_json or {},
        )
        self.session.add(job)
        self.session.flush()
        return job

    def finish_job(
        self,
        job: IngestJob,
        *,
        status: str,
        summary_json: dict[str, Any],
        error_message: str | None = None,
    ) -> IngestJob:
        job.status = status
        job.summary_json = summary_json
        job.error_message = error_message
        job.completed_at = datetime.now(UTC)
        self.session.flush()
        return job
