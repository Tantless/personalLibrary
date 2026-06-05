from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import Protocol

from sqlalchemy import text
from sqlalchemy.orm import Session

from pkcs.db.session import create_session_factory
from pkcs.search.models import SearchCitation, SearchResult
from pkcs.source_metadata import knowledge_type_code_for_name, knowledge_type_name, normalized_format_name, source_format_name

SessionFactory = Callable[[], AbstractContextManager[Session]]


class SearchProvider(Protocol):
    def search(
        self,
        *,
        query: str,
        top_k: int,
        knowledge_type: str | None = None,
        canonical_key: str | None = None,
    ) -> list[SearchResult]:
        pass


class PostgresFTSSearchProvider:
    def __init__(self, *, session_factory: SessionFactory) -> None:
        self.session_factory = session_factory

    @classmethod
    def from_database_url(cls, database_url: str) -> "PostgresFTSSearchProvider":
        return cls(session_factory=create_session_factory(database_url))

    def search(
        self,
        *,
        query: str,
        top_k: int,
        knowledge_type: str | None = None,
        canonical_key: str | None = None,
    ) -> list[SearchResult]:
        knowledge_type_code = knowledge_type_code_for_name(knowledge_type) if knowledge_type is not None else None
        sql = text(
            """
            with search_query as (
                select websearch_to_tsquery('simple', :query) as ts_query
            )
            select
                c.id as chunk_id,
                c.source_id as source_id,
                c.version_id as version_id,
                s.canonical_key as canonical_key,
                c.title as title,
                c.source_format_code as source_format_code,
                c.normalized_format_code as normalized_format_code,
                c.knowledge_type_code as knowledge_type_code,
                ts_headline(
                    'simple',
                    c.content,
                    search_query.ts_query,
                    'MaxFragments=2, MinWords=4, MaxWords=24'
                ) as snippet,
                (
                    ts_rank_cd(c.search_vector, search_query.ts_query)
                    + case
                        when to_tsvector('simple', coalesce(c.title, '')) @@ search_query.ts_query
                        then 0.5
                        else 0
                      end
                ) as score,
                c.locator as locator,
                c.line_start as line_start,
                c.line_end as line_end,
                c.heading_path as heading_path,
                c.metadata_json as metadata_json
            from chunks c
            join sources s on s.id = c.source_id
            cross join search_query
            where c.search_vector @@ search_query.ts_query
              and (cast(:knowledge_type_code as integer) is null or c.knowledge_type_code = cast(:knowledge_type_code as integer))
              and (cast(:canonical_key as text) is null or s.canonical_key = cast(:canonical_key as text))
            order by score desc, c.created_at asc, c.id asc
            limit :top_k
            """
        )
        params = {
            "query": query,
            "top_k": top_k,
            "knowledge_type_code": knowledge_type_code,
            "canonical_key": canonical_key,
        }
        with self.session_factory() as session:
            rows = session.execute(sql, params).mappings().all()

        results: list[SearchResult] = []
        for index, row in enumerate(rows, start=1):
            metadata = dict(row["metadata_json"] or {})
            metadata.setdefault("heading_path", row["heading_path"] or [])
            results.append(
                SearchResult(
                    result_id=f"result-{index}",
                    chunk_id=row["chunk_id"],
                    source_id=row["source_id"],
                    version_id=row["version_id"],
                    canonical_key=row["canonical_key"],
                    title=row["title"],
                    source_format=source_format_name(row["source_format_code"]),
                    normalized_format=normalized_format_name(row["normalized_format_code"]),
                    knowledge_type=knowledge_type_name(row["knowledge_type_code"]),
                    snippet=row["snippet"] or "",
                    score=float(row["score"] or 0),
                    citation=SearchCitation(
                        locator=row["locator"],
                        line_start=row["line_start"],
                        line_end=row["line_end"],
                    ),
                    metadata=metadata,
                )
            )
        return results
