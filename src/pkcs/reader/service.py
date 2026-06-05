import logging
from collections.abc import Callable
from contextlib import AbstractContextManager
from pathlib import Path

from sqlalchemy.orm import Session

from pkcs.config import Settings, get_settings
from pkcs.db.models import Chunk, Source, SourceVersion
from pkcs.db.repositories import ChunkRepository, SourceRepository
from pkcs.db.session import create_session_factory
from pkcs.reader.locators import LocatorError, format_line_locator, parse_line_locator
from pkcs.reader.models import SourceFragment, SourceReference
from pkcs.source_metadata import knowledge_type_name, normalized_format_name, source_format_name

SessionFactory = Callable[[], AbstractContextManager[Session]]

logger = logging.getLogger(__name__)


class ReadSourceError(ValueError):
    pass


class ReadSourceService:
    def __init__(self, *, session_factory: SessionFactory) -> None:
        self.session_factory = session_factory

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> "ReadSourceService":
        resolved_settings = settings or get_settings()
        return cls(session_factory=create_session_factory(resolved_settings.database_url))

    def read_source(
        self,
        *,
        chunk_id: str | None = None,
        source_id: str | None = None,
        version_id: str | None = None,
        locator: str | None = None,
        context_lines: int = 0,
    ) -> SourceFragment:
        if context_lines < 0:
            raise ReadSourceError("context_lines must be non-negative")

        with self.session_factory() as session:
            chunk, source, version = self._resolve_address(
                session=session,
                chunk_id=chunk_id,
                source_id=source_id,
                version_id=version_id,
                locator=locator,
            )

        line_start = chunk.line_start if chunk is not None else parse_line_locator(locator or "")[0]
        line_end = chunk.line_end if chunk is not None else parse_line_locator(locator or "")[1]
        normalized_locator = chunk.locator if chunk is not None else format_line_locator(line_start, line_end)
        content, context_line_start, context_line_end = self._read_line_fragment(
            raw_archive_path=version.raw_archive_path,
            line_start=line_start,
            line_end=line_end,
            context_lines=context_lines,
        )
        metadata = dict(chunk.metadata_json if chunk is not None else version.metadata_json)
        if chunk is not None:
            metadata.setdefault("heading_path", chunk.heading_path or [])

        logger.info(
            "read_source_completed",
            extra={
                "event": "read_source_completed",
                "source_id": source.id,
                "version_id": version.id,
                "chunk_id": chunk.id if chunk is not None else None,
                "context_lines": context_lines,
            },
        )
        return SourceFragment(
            source=SourceReference(
                source_id=source.id,
                version_id=version.id,
                chunk_id=chunk.id if chunk is not None else None,
                canonical_key=source.canonical_key,
                title=source.title,
                source_format=source_format_name(
                    chunk.source_format_code if chunk is not None else version.source_format_code
                ),
                normalized_format=normalized_format_name(
                    chunk.normalized_format_code if chunk is not None else version.normalized_format_code
                ),
                knowledge_type=knowledge_type_name(
                    chunk.knowledge_type_code if chunk is not None else source.knowledge_type_code
                ),
            ),
            locator=normalized_locator,
            line_start=line_start,
            line_end=line_end,
            context_line_start=context_line_start,
            context_line_end=context_line_end,
            content=content,
            metadata=metadata,
        )

    def _resolve_address(
        self,
        *,
        session: Session,
        chunk_id: str | None,
        source_id: str | None,
        version_id: str | None,
        locator: str | None,
    ) -> tuple[Chunk | None, Source, SourceVersion]:
        chunk_repo = ChunkRepository(session)
        source_repo = SourceRepository(session)

        if chunk_id:
            chunk = chunk_repo.get(chunk_id)
            if chunk is None:
                raise ReadSourceError(f"chunk not found: {chunk_id}")
            source = source_repo.get(chunk.source_id)
            if source is None:
                raise ReadSourceError(f"source not found: {chunk.source_id}")
            version = source_repo.get_version(source_id=chunk.source_id, version_id=chunk.version_id)
            if version is None:
                raise ReadSourceError(f"version not found: {chunk.version_id}")
            return chunk, source, version

        if not source_id or not version_id or not locator:
            raise ReadSourceError("provide chunk_id or source_id, version_id, and locator")

        try:
            locator_start, locator_end = parse_line_locator(locator)
        except LocatorError as exc:
            raise ReadSourceError(str(exc)) from exc
        normalized_locator = format_line_locator(locator_start, locator_end)

        source = source_repo.get(source_id)
        if source is None:
            raise ReadSourceError(f"source not found: {source_id}")
        version = source_repo.get_version(source_id=source_id, version_id=version_id)
        if version is None:
            raise ReadSourceError(f"version not found: {version_id}")
        chunk = chunk_repo.get_by_locator(source_id=source_id, version_id=version_id, locator=normalized_locator)
        return chunk, source, version

    def _read_line_fragment(
        self,
        *,
        raw_archive_path: str,
        line_start: int,
        line_end: int,
        context_lines: int,
    ) -> tuple[str, int, int]:
        path = Path(raw_archive_path)
        if not path.exists():
            raise ReadSourceError(f"raw archive file not found: {raw_archive_path}")

        lines = path.read_text(encoding="utf-8-sig").splitlines()
        if line_start > len(lines):
            raise ReadSourceError("locator starts beyond source line count")
        if line_end > len(lines):
            raise ReadSourceError("locator ends beyond source line count")

        context_line_start = max(1, line_start - context_lines)
        context_line_end = min(len(lines), line_end + context_lines)
        selected_lines = lines[context_line_start - 1 : context_line_end]
        return "\n".join(selected_lines), context_line_start, context_line_end
