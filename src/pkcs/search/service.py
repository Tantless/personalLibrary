import logging

from pkcs.config import Settings, get_settings
from pkcs.ingest.models import SUPPORTED_KNOWLEDGE_TYPES
from pkcs.search.models import SearchResponse
from pkcs.search.providers import PostgresFTSSearchProvider, SearchProvider

logger = logging.getLogger(__name__)


class SearchInputError(ValueError):
    pass


class SearchService:
    def __init__(self, *, provider: SearchProvider, default_top_k: int) -> None:
        self.provider = provider
        self.default_top_k = default_top_k

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> "SearchService":
        resolved_settings = settings or get_settings()
        return cls(
            provider=PostgresFTSSearchProvider.from_database_url(resolved_settings.database_url),
            default_top_k=resolved_settings.default_top_k,
        )

    def search_knowledge(
        self,
        *,
        query: str,
        knowledge_type: str | None = None,
        canonical_key: str | None = None,
        top_k: int | None = None,
    ) -> SearchResponse:
        normalized_query = query.strip()
        if not normalized_query:
            raise SearchInputError("query must not be empty")
        if knowledge_type is not None and knowledge_type not in SUPPORTED_KNOWLEDGE_TYPES:
            raise SearchInputError(f"unsupported knowledge_type: {knowledge_type}")

        resolved_top_k = top_k or self.default_top_k
        if resolved_top_k < 1:
            raise SearchInputError("top_k must be at least 1")

        results = self.provider.search(
            query=normalized_query,
            knowledge_type=knowledge_type,
            canonical_key=canonical_key,
            top_k=resolved_top_k,
        )
        logger.info(
            "search_knowledge_completed",
            extra={
                "event": "search_knowledge_completed",
                "knowledge_type": knowledge_type,
                "top_k": resolved_top_k,
                "result_count": len(results),
            },
        )
        return SearchResponse(
            query=normalized_query,
            knowledge_type=knowledge_type,
            canonical_key=canonical_key,
            top_k=resolved_top_k,
            results=results,
        )
