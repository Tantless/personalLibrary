from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class SourceReference:
    source_id: str
    version_id: str
    chunk_id: str | None
    canonical_key: str
    title: str
    source_format: str
    normalized_format: str
    knowledge_type: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SourceFragment:
    source: SourceReference
    locator: str
    line_start: int
    line_end: int
    context_line_start: int
    context_line_end: int
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source.to_dict(),
            "locator": self.locator,
            "line_start": self.line_start,
            "line_end": self.line_end,
            "context_line_start": self.context_line_start,
            "context_line_end": self.context_line_end,
            "content": self.content,
            "metadata": self.metadata,
        }
