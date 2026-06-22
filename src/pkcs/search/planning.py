from collections.abc import Iterable
from dataclasses import dataclass, field
import re
from typing import Any


FUSION_RECIPROCAL_RANK_V1 = "reciprocal_rank_v1"

INTENT_BROAD_RECALL = "broad_recall"
INTENT_OFFICIAL_DOC_LOOKUP = "official_doc_lookup"
INTENT_SAFETY_REPORT_LOOKUP = "safety_report_lookup"
INTENT_BROAD_PROJECT_LOOKUP = "broad_project_lookup"
INTENT_RECENT_TECHNICAL_LOOKUP = "recent_technical_lookup"

PASS_ORIGINAL = "original"
PASS_ASCII_ENTITY = "ascii_entity"
PASS_GLOSSARY_EXPANSION = "glossary_expansion"
PASS_SOURCE_ALIAS = "source_alias"
PASS_COMBINED = "combined"

ASCII_ENTITY_RE = re.compile(
    r"[A-Za-z0-9][A-Za-z0-9+.#]*(?:[-_/][A-Za-z0-9+.#]+)*"
    r"(?:\s+[A-Za-z0-9][A-Za-z0-9+.#]*(?:[-_/][A-Za-z0-9+.#]+)*)*"
)

DEFAULT_TECHNICAL_GLOSSARY: dict[str, tuple[str, ...]] = {
    "工具调用": ("tools", "function tools", "tool calling", "function calling"),
    "函数调用": ("function calling", "function tools", "tool calling"),
    "函数工具": ("function tools", "tools"),
    "护栏": ("guardrails", "input guardrails", "output guardrails"),
    "安全评估": ("safety", "evaluations", "safety evaluations"),
    "评估类别": ("evaluations", "safety evaluations"),
    "观察": ("tracing", "workflow", "observability"),
    "观测": ("tracing", "workflow", "observability"),
    "追踪": ("tracing", "workflow", "observability"),
    "工作流事件": ("workflow", "events", "tracing"),
    "核心能力": ("features", "capabilities"),
    "重点": ("overview", "highlights"),
    "文档": ("docs", "documentation"),
}


class QueryPlanningInputError(ValueError):
    pass


@dataclass(frozen=True)
class RetrievalPass:
    name: str
    query: str
    weight: float = 1.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "query": self.query,
            "weight": self.weight,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class RetrievalPlan:
    query: str
    intent: str
    passes: list[RetrievalPass]
    fusion: str = FUSION_RECIPROCAL_RANK_V1
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "intent": self.intent,
            "passes": [item.to_dict() for item in self.passes],
            "fusion": self.fusion,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class SourceAlias:
    title: str
    aliases: tuple[str, ...] = ()
    terms: tuple[str, ...] = ()
    canonical_key: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "aliases": list(self.aliases),
            "terms": list(self.terms),
            "canonical_key": self.canonical_key,
        }


@dataclass(frozen=True)
class SourceAliasMatch:
    source_alias: SourceAlias
    score: int
    matched_aliases: list[str]
    matched_terms: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_alias": self.source_alias.to_dict(),
            "score": self.score,
            "matched_aliases": self.matched_aliases,
            "matched_terms": self.matched_terms,
        }


class QueryPlanner:
    def __init__(
        self,
        *,
        glossary: dict[str, tuple[str, ...]] | None = None,
        source_aliases: list[SourceAlias] | None = None,
        max_source_aliases: int = 3,
    ) -> None:
        if max_source_aliases < 1:
            raise QueryPlanningInputError("max_source_aliases must be at least 1")
        self.glossary = DEFAULT_TECHNICAL_GLOSSARY if glossary is None else glossary
        self.source_aliases = [] if source_aliases is None else source_aliases
        self.max_source_aliases = max_source_aliases

    def plan(self, query: str) -> RetrievalPlan:
        normalized_query = _normalize_query(query)
        if not normalized_query:
            raise QueryPlanningInputError("query must not be empty")

        ascii_entities = _extract_ascii_entities(normalized_query)
        glossary_matches = _expand_glossary(normalized_query, self.glossary)
        glossary_terms = _unique_terms(
            term
            for expansions in glossary_matches.values()
            for term in expansions
        )
        source_alias_matches = self._match_source_aliases(
            query=normalized_query,
            ascii_entities=ascii_entities,
            glossary_terms=glossary_terms,
        )

        passes = [
            RetrievalPass(
                name=PASS_ORIGINAL,
                query=normalized_query,
                weight=1.0,
                metadata={},
            )
        ]
        if ascii_entities:
            passes.append(
                RetrievalPass(
                    name=PASS_ASCII_ENTITY,
                    query=" ".join(ascii_entities),
                    weight=1.2,
                    metadata={"entities": ascii_entities},
                )
            )
        if glossary_terms:
            passes.append(
                RetrievalPass(
                    name=PASS_GLOSSARY_EXPANSION,
                    query=" ".join(glossary_terms),
                    weight=1.1,
                    metadata={"glossary_matches": _glossary_matches_to_dict(glossary_matches)},
                )
            )
        if source_alias_matches:
            passes.append(
                RetrievalPass(
                    name=PASS_SOURCE_ALIAS,
                    query=" ".join(_source_alias_queries(source_alias_matches)),
                    weight=1.4,
                    metadata={"source_alias_matches": [item.to_dict() for item in source_alias_matches]},
                )
            )

        combined_query = _combined_query(ascii_entities, glossary_terms, source_alias_matches)
        if combined_query:
            passes.append(
                RetrievalPass(
                    name=PASS_COMBINED,
                    query=combined_query,
                    weight=1.3,
                    metadata={
                        "entity_count": len(ascii_entities),
                        "glossary_term_count": len(glossary_terms),
                        "source_alias_count": len(source_alias_matches),
                    },
                )
            )

        return RetrievalPlan(
            query=normalized_query,
            intent=_infer_intent(normalized_query),
            passes=passes,
            fusion=FUSION_RECIPROCAL_RANK_V1,
            metadata={
                "ascii_entities": ascii_entities,
                "glossary_matches": _glossary_matches_to_dict(glossary_matches),
                "source_alias_matches": [item.to_dict() for item in source_alias_matches],
            },
        )

    def _match_source_aliases(
        self,
        *,
        query: str,
        ascii_entities: list[str],
        glossary_terms: list[str],
    ) -> list[SourceAliasMatch]:
        if not self.source_aliases:
            return []

        signal_text = " ".join([query, *ascii_entities, *glossary_terms]).casefold()
        matches: list[SourceAliasMatch] = []
        for source_alias in self.source_aliases:
            matched_aliases = [
                alias
                for alias in _source_alias_match_phrases(source_alias)
                if alias.casefold() in signal_text
            ]
            matched_terms = [term for term in source_alias.terms if term.casefold() in signal_text]
            score = len(matched_aliases) * 3 + len(matched_terms) * 2
            if score > 0:
                matches.append(
                    SourceAliasMatch(
                        source_alias=source_alias,
                        score=score,
                        matched_aliases=matched_aliases,
                        matched_terms=matched_terms,
                    )
                )

        if not matches:
            return []
        matches.sort(key=lambda item: (-item.score, item.source_alias.title.casefold()))
        top_score = matches[0].score
        return [item for item in matches if item.score == top_score][: self.max_source_aliases]


def _normalize_query(query: str) -> str:
    return " ".join(query.strip().split())


def _extract_ascii_entities(query: str) -> list[str]:
    return _unique_terms(match.group(0).strip() for match in ASCII_ENTITY_RE.finditer(query))


def _expand_glossary(query: str, glossary: dict[str, tuple[str, ...]]) -> dict[str, list[str]]:
    query_folded = query.casefold()
    matches: dict[str, list[str]] = {}
    for trigger, expansions in glossary.items():
        if trigger.casefold() in query_folded:
            matches[trigger] = _unique_terms(expansions)
    return matches


def _infer_intent(query: str) -> str:
    folded = query.casefold()
    if "system card" in folded or "安全评估" in query:
        return INTENT_SAFETY_REPORT_LOOKUP
    if "readme" in folded or "game engine" in folded:
        return INTENT_BROAD_PROJECT_LOOKUP
    if "nvidia" in folded or "diffusiongemma" in folded:
        return INTENT_RECENT_TECHNICAL_LOOKUP
    if "sdk" in folded or "docs" in folded or "文档" in query:
        return INTENT_OFFICIAL_DOC_LOOKUP
    return INTENT_BROAD_RECALL


def _source_alias_match_phrases(source_alias: SourceAlias) -> list[str]:
    return _unique_terms([source_alias.title, *source_alias.aliases])


def _source_alias_queries(matches: list[SourceAliasMatch]) -> list[str]:
    return _unique_terms(item.source_alias.title for item in matches)


def _combined_query(
    ascii_entities: list[str],
    glossary_terms: list[str],
    source_alias_matches: list[SourceAliasMatch],
) -> str:
    parts = _unique_terms(
        [
            *_source_alias_queries(source_alias_matches),
            *ascii_entities,
            *glossary_terms[:6],
        ]
    )
    if len(parts) <= 1:
        return ""
    return " ".join(parts)


def _glossary_matches_to_dict(matches: dict[str, list[str]]) -> list[dict[str, Any]]:
    return [{"trigger": trigger, "expansions": expansions} for trigger, expansions in matches.items()]


def _unique_terms(terms: Iterable[object]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for term in terms:
        normalized = str(term).strip()
        if not normalized:
            continue
        key = normalized.casefold()
        if key in seen:
            continue
        seen.add(key)
        unique.append(normalized)
    return unique
