from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class SearchCitation:
    locator: str
    line_start: int
    line_end: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SearchResult:
    result_id: str
    chunk_id: str
    source_id: str
    version_id: str
    canonical_key: str
    title: str
    source_type: str
    snippet: str
    score: float
    citation: SearchCitation
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "result_id": self.result_id,
            "chunk_id": self.chunk_id,
            "source_id": self.source_id,
            "version_id": self.version_id,
            "canonical_key": self.canonical_key,
            "title": self.title,
            "source_type": self.source_type,
            "snippet": self.snippet,
            "score": self.score,
            "citation": self.citation.to_dict(),
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class SearchResponse:
    query: str
    source_type: str | None
    canonical_key: str | None
    top_k: int
    results: list[SearchResult]

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "source_type": self.source_type,
            "canonical_key": self.canonical_key,
            "top_k": self.top_k,
            "results": [result.to_dict() for result in self.results],
        }
