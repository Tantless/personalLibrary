from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal


SOURCE_TYPE_AI_CONVERSATION = "ai_conversation"
SOURCE_TYPE_MARKDOWN_DOC = "markdown_doc"
SUPPORTED_SOURCE_TYPES = {SOURCE_TYPE_AI_CONVERSATION, SOURCE_TYPE_MARKDOWN_DOC}

SUPPORTED_EXTENSIONS = {
    SOURCE_TYPE_AI_CONVERSATION: {".jsonl", ".md", ".txt"},
    SOURCE_TYPE_MARKDOWN_DOC: {".md", ".txt"},
}

ItemStatus = Literal["succeeded", "skipped", "failed"]


@dataclass(frozen=True)
class ParsedChunk:
    title: str
    content: str
    line_start: int
    line_end: int
    heading_path: list[str] = field(default_factory=list)
    metadata_json: dict[str, Any] = field(default_factory=dict)

    @property
    def locator(self) -> str:
        return f"line {self.line_start}-{self.line_end}"


@dataclass(frozen=True)
class ParsedSource:
    title: str
    source_type: str
    metadata_json: dict[str, Any]
    chunks: list[ParsedChunk]


@dataclass(frozen=True)
class IngestItemReport:
    input_path: str
    status: ItemStatus
    source_id: str | None = None
    version_id: str | None = None
    canonical_key: str | None = None
    content_hash: str | None = None
    created_new_source: bool = False
    created_new_version: bool = False
    chunks_created: int = 0
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class IngestReport:
    ingest_job_id: str
    status: str
    source_id: str | None
    version_id: str | None
    canonical_key: str | None
    content_hash: str | None
    created_new_source: bool
    created_new_version: bool
    chunks_created: int
    succeeded: list[IngestItemReport] = field(default_factory=list)
    skipped: list[IngestItemReport] = field(default_factory=list)
    failed: list[IngestItemReport] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ingest_job_id": self.ingest_job_id,
            "status": self.status,
            "source_id": self.source_id,
            "version_id": self.version_id,
            "canonical_key": self.canonical_key,
            "content_hash": self.content_hash,
            "created_new_source": self.created_new_source,
            "created_new_version": self.created_new_version,
            "chunks_created": self.chunks_created,
            "succeeded": [item.to_dict() for item in self.succeeded],
            "skipped": [item.to_dict() for item in self.skipped],
            "failed": [item.to_dict() for item in self.failed],
        }


def canonical_key_for_path(source_type: str, path: Path) -> str:
    return f"{source_type}:{path.resolve().as_posix()}"
