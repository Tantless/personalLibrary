from dataclasses import dataclass, field
from typing import Any

from pkcs.config import Settings, get_settings
from pkcs.ingest.models import SUPPORTED_KNOWLEDGE_TYPES
from pkcs.search.models import SearchCitation, SearchResult
from pkcs.search.planning import FUSION_RECIPROCAL_RANK_V1, QueryPlanner, RetrievalPlan
from pkcs.search.providers import (
    PostgresFTSSearchProvider,
    PostgresSourceAliasProvider,
    SearchProvider,
    SourceAliasProvider,
)


class PlannedSearchInputError(ValueError):
    pass


@dataclass(frozen=True)
class PlannedSearchPassRun:
    name: str
    query: str
    result_count: int
    error_type: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "query": self.query,
            "result_count": self.result_count,
            "error_type": self.error_type,
        }


@dataclass(frozen=True)
class PlannedSearchResponse:
    query: str
    knowledge_type: str | None
    canonical_key: str | None
    top_k: int
    retrieval_plan: RetrievalPlan
    pass_runs: list[PlannedSearchPassRun]
    results: list[SearchResult]

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "knowledge_type": self.knowledge_type,
            "canonical_key": self.canonical_key,
            "top_k": self.top_k,
            "retrieval_plan": self.retrieval_plan.to_dict(),
            "pass_runs": [item.to_dict() for item in self.pass_runs],
            "results": [result.to_dict() for result in self.results],
        }


@dataclass
class _PassHit:
    pass_name: str
    query: str
    rank: int
    score: float
    weight: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "pass_name": self.pass_name,
            "query": self.query,
            "rank": self.rank,
            "score": self.score,
            "weight": self.weight,
        }


@dataclass
class _FusionState:
    result: SearchResult
    fused_score: float = 0.0
    best_rank: int = 0
    hits: list[_PassHit] = field(default_factory=list)


class PlannedSearchService:
    def __init__(
        self,
        *,
        provider: SearchProvider,
        default_top_k: int,
        planner: QueryPlanner | None = None,
        source_alias_provider: SourceAliasProvider | None = None,
        source_alias_limit: int = 500,
        rank_constant: int = 60,
    ) -> None:
        if rank_constant < 1:
            raise PlannedSearchInputError("rank_constant must be at least 1")
        self.provider = provider
        self.default_top_k = default_top_k
        self.planner = planner or QueryPlanner()
        self.source_alias_provider = source_alias_provider
        self.source_alias_limit = source_alias_limit
        self.rank_constant = rank_constant

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> "PlannedSearchService":
        resolved_settings = settings or get_settings()
        return cls(
            provider=PostgresFTSSearchProvider.from_database_url(resolved_settings.database_url),
            source_alias_provider=PostgresSourceAliasProvider.from_database_url(resolved_settings.database_url),
            default_top_k=resolved_settings.default_top_k,
        )

    def search_knowledge(
        self,
        *,
        query: str,
        knowledge_type: str | None = None,
        canonical_key: str | None = None,
        top_k: int | None = None,
    ) -> PlannedSearchResponse:
        normalized_query = query.strip()
        if not normalized_query:
            raise PlannedSearchInputError("query must not be empty")
        if knowledge_type is not None and knowledge_type not in SUPPORTED_KNOWLEDGE_TYPES:
            raise PlannedSearchInputError(f"unsupported knowledge_type: {knowledge_type}")

        resolved_top_k = top_k or self.default_top_k
        if resolved_top_k < 1:
            raise PlannedSearchInputError("top_k must be at least 1")

        retrieval_plan = self._plan(
            query=normalized_query,
            knowledge_type=knowledge_type,
            canonical_key=canonical_key,
        )
        results_by_chunk: dict[str, _FusionState] = {}
        pass_runs: list[PlannedSearchPassRun] = []
        errors: list[Exception] = []
        for retrieval_pass in retrieval_plan.passes:
            try:
                pass_results = self.provider.search(
                    query=retrieval_pass.query,
                    knowledge_type=knowledge_type,
                    canonical_key=canonical_key,
                    top_k=resolved_top_k,
                )
            except Exception as exc:
                errors.append(exc)
                pass_runs.append(
                    PlannedSearchPassRun(
                        name=retrieval_pass.name,
                        query=retrieval_pass.query,
                        result_count=0,
                        error_type=type(exc).__name__,
                    )
                )
                continue

            pass_runs.append(
                PlannedSearchPassRun(
                    name=retrieval_pass.name,
                    query=retrieval_pass.query,
                    result_count=len(pass_results),
                )
            )
            for rank, result in enumerate(pass_results, start=1):
                state = results_by_chunk.get(result.chunk_id)
                if state is None:
                    state = _FusionState(result=result, best_rank=rank)
                    results_by_chunk[result.chunk_id] = state
                elif rank < state.best_rank:
                    state.best_rank = rank
                    state.result = result

                state.fused_score += retrieval_pass.weight / (self.rank_constant + rank)
                state.hits.append(
                    _PassHit(
                        pass_name=retrieval_pass.name,
                        query=retrieval_pass.query,
                        rank=rank,
                        score=result.score,
                        weight=retrieval_pass.weight,
                    )
                )

        if not results_by_chunk and errors and len(errors) == len(retrieval_plan.passes):
            raise PlannedSearchInputError("all retrieval passes failed") from errors[0]

        fused_results = self._rank_fused_results(results_by_chunk)[:resolved_top_k]
        return PlannedSearchResponse(
            query=normalized_query,
            knowledge_type=knowledge_type,
            canonical_key=canonical_key,
            top_k=resolved_top_k,
            retrieval_plan=retrieval_plan,
            pass_runs=pass_runs,
            results=fused_results,
        )

    def _plan(
        self,
        *,
        query: str,
        knowledge_type: str | None,
        canonical_key: str | None,
    ) -> RetrievalPlan:
        if self.source_alias_provider is None:
            return self.planner.plan(query)
        source_aliases = self.source_alias_provider.list_source_aliases(
            knowledge_type=knowledge_type,
            canonical_key=canonical_key,
            limit=self.source_alias_limit,
        )
        planner = QueryPlanner(
            glossary=self.planner.glossary,
            source_aliases=source_aliases,
            max_source_aliases=self.planner.max_source_aliases,
        )
        return planner.plan(query)

    def _rank_fused_results(self, results_by_chunk: dict[str, _FusionState]) -> list[SearchResult]:
        states = sorted(
            results_by_chunk.values(),
            key=lambda state: (
                -state.fused_score,
                state.best_rank,
                state.result.canonical_key,
                state.result.chunk_id,
            ),
        )
        return [
            _with_planned_metadata(
                state.result,
                fused_rank=index,
                fused_score=state.fused_score,
                pass_hits=state.hits,
            )
            for index, state in enumerate(states, start=1)
        ]


def _with_planned_metadata(
    result: SearchResult,
    *,
    fused_rank: int,
    fused_score: float,
    pass_hits: list[_PassHit],
) -> SearchResult:
    metadata = dict(result.metadata)
    metadata["planned_retrieval"] = {
        "fusion": FUSION_RECIPROCAL_RANK_V1,
        "fused_rank": fused_rank,
        "fused_score": fused_score,
        "pass_hits": [hit.to_dict() for hit in pass_hits],
    }
    return SearchResult(
        result_id=f"result-{fused_rank}",
        chunk_id=result.chunk_id,
        source_id=result.source_id,
        version_id=result.version_id,
        canonical_key=result.canonical_key,
        title=result.title,
        source_format=result.source_format,
        normalized_format=result.normalized_format,
        knowledge_type=result.knowledge_type,
        snippet=result.snippet,
        score=fused_score,
        citation=SearchCitation(
            locator=result.citation.locator,
            line_start=result.citation.line_start,
            line_end=result.citation.line_end,
        ),
        metadata=metadata,
    )
