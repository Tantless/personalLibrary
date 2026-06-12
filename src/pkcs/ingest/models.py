from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from pkcs.source_metadata import (
    KNOWLEDGE_TYPE_AI_CONVERSATION,
    KNOWLEDGE_TYPE_DOCUMENT,
    SOURCE_FORMAT_CODES_BY_EXTENSION,
    SUPPORTED_SOURCE_FORMAT_CODES_BY_KNOWLEDGE_TYPE,
    knowledge_type_name,
    source_format_name,
)

KNOWLEDGE_TYPE_NAME_AI_CONVERSATION = knowledge_type_name(KNOWLEDGE_TYPE_AI_CONVERSATION)
KNOWLEDGE_TYPE_NAME_DOCUMENT = knowledge_type_name(KNOWLEDGE_TYPE_DOCUMENT)
SUPPORTED_KNOWLEDGE_TYPES = {KNOWLEDGE_TYPE_NAME_AI_CONVERSATION, KNOWLEDGE_TYPE_NAME_DOCUMENT}

SUPPORTED_EXTENSIONS = {
    knowledge_type_name(knowledge_type_code): {
        extension
        for extension, source_format_code in SOURCE_FORMAT_CODES_BY_EXTENSION.items()
        if source_format_code in source_format_codes
    }
    for knowledge_type_code, source_format_codes in SUPPORTED_SOURCE_FORMAT_CODES_BY_KNOWLEDGE_TYPE.items()
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
    chunk_key: str | None = None

    @property
    def locator(self) -> str:
        return f"line {self.line_start}-{self.line_end}"


@dataclass(frozen=True)
class ParsedTableArtifact:
    artifact_key: str
    line_start: int
    line_end: int
    heading_path: list[str]
    columns: list[str]
    rows: list[dict[str, str]]
    normalized_markdown: str
    summary: str | None = None
    metadata_json: dict[str, Any] = field(default_factory=dict)

    @property
    def locator(self) -> str:
        return f"line {self.line_start}-{self.line_end}"


@dataclass(frozen=True)
class ParsedImageArtifact:
    artifact_key: str
    line_start: int
    line_end: int
    heading_path: list[str]
    original_uri: str
    alt_text: str | None = None
    caption: str | None = None
    nearby_text: str | None = None
    metadata_json: dict[str, Any] = field(default_factory=dict)

    @property
    def locator(self) -> str:
        return f"line {self.line_start}-{self.line_end}"


@dataclass(frozen=True)
class ParsedSource:
    title: str
    knowledge_type: str
    metadata_json: dict[str, Any]
    chunks: list[ParsedChunk]
    table_artifacts: list[ParsedTableArtifact] = field(default_factory=list)
    image_artifacts: list[ParsedImageArtifact] = field(default_factory=list)
    markdown_block_graph: "ParsedMarkdownBlockGraph | None" = None


@dataclass(frozen=True)
class ParsedMarkdownBlock:
    block_id: str
    block_type: str
    line_start: int
    line_end: int
    heading_path: list[str]
    raw_text: str
    normalized_text: str | None = None
    parent_block_id: str | None = None
    metadata_json: dict[str, Any] = field(default_factory=dict)

    @property
    def locator(self) -> str:
        return f"line {self.line_start}-{self.line_end}"


@dataclass(frozen=True)
class ParsedMarkdownBlockEdge:
    source_block_id: str
    target_block_id: str
    edge_type: str


@dataclass(frozen=True)
class ParsedArtifactBinding:
    artifact_type: Literal["table", "image"]
    artifact_key: str
    source_block_id: str
    bound_block_ids: list[str]
    role: str
    locator: str


@dataclass(frozen=True)
class ParsedMarkdownBlockGraph:
    title: str
    blocks: list[ParsedMarkdownBlock]
    edges: list[ParsedMarkdownBlockEdge] = field(default_factory=list)
    artifact_bindings: list[ParsedArtifactBinding] = field(default_factory=list)
    diagnostics: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class IngestItemReport:
    input_name: str
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


__all__ = [
    "KNOWLEDGE_TYPE_NAME_AI_CONVERSATION",
    "KNOWLEDGE_TYPE_NAME_DOCUMENT",
    "SUPPORTED_EXTENSIONS",
    "SUPPORTED_KNOWLEDGE_TYPES",
    "IngestItemReport",
    "IngestReport",
    "ParsedChunk",
    "ParsedArtifactBinding",
    "ParsedImageArtifact",
    "ParsedMarkdownBlock",
    "ParsedMarkdownBlockEdge",
    "ParsedMarkdownBlockGraph",
    "ParsedSource",
    "ParsedTableArtifact",
    "source_format_name",
]
