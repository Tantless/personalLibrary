from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class ContextPackEvidence:
    evidence_id: str
    chunk_id: str
    source_id: str
    version_id: str
    canonical_key: str
    title: str
    source_type: str
    locator: str
    line_start: int
    line_end: int
    score: float
    snippet: str
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ContextPackSource:
    source_id: str
    version_id: str
    canonical_key: str
    title: str
    source_type: str
    evidence_count: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class FollowupReadSuggestion:
    chunk_id: str
    source_id: str
    version_id: str
    locator: str
    context_lines: int
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ContextPackResponse:
    query: str
    retrieval_plan: dict[str, Any]
    sources: list[ContextPackSource]
    evidence: list[ContextPackEvidence]
    followup_read_suggestions: list[FollowupReadSuggestion]
    context_pack_markdown: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "retrieval_plan": self.retrieval_plan,
            "sources": [source.to_dict() for source in self.sources],
            "evidence": [item.to_dict() for item in self.evidence],
            "followup_read_suggestions": [item.to_dict() for item in self.followup_read_suggestions],
            "context_pack_markdown": self.context_pack_markdown,
        }
