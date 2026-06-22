import logging
from collections import Counter

from pkcs.config import Settings, get_settings
from pkcs.context_pack.models import (
    ContextPackEvidence,
    ContextPackResponse,
    ContextPackSource,
    FollowupReadSuggestion,
)
from pkcs.db.models import ImageArtifact, TableArtifact
from pkcs.db.repositories import ImageArtifactRepository, TableArtifactRepository
from pkcs.reader import ReadSourceService
from pkcs.search import PlannedSearchService, SearchService
from pkcs.search.models import SearchResult

logger = logging.getLogger(__name__)


class ContextPackInputError(ValueError):
    pass


class ContextPackService:
    def __init__(
        self,
        *,
        search_service: SearchService | PlannedSearchService,
        read_source_service: ReadSourceService,
        default_top_k: int,
        max_evidence: int,
        max_evidence_per_source: int,
    ) -> None:
        self.search_service = search_service
        self.read_source_service = read_source_service
        self.default_top_k = default_top_k
        self.max_evidence = max_evidence
        self.max_evidence_per_source = max_evidence_per_source

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> "ContextPackService":
        resolved_settings = settings or get_settings()
        return cls(
            search_service=PlannedSearchService.from_settings(resolved_settings),
            read_source_service=ReadSourceService.from_settings(resolved_settings),
            default_top_k=resolved_settings.default_top_k,
            max_evidence=resolved_settings.context_pack_max_evidence,
            max_evidence_per_source=resolved_settings.context_pack_max_evidence_per_source,
        )

    def get_context_pack(
        self,
        *,
        query: str,
        knowledge_type: str | None = None,
        canonical_key: str | None = None,
        top_k: int | None = None,
        budget_tokens: int | None = None,
    ) -> ContextPackResponse:
        normalized_query = query.strip()
        if not normalized_query:
            raise ContextPackInputError("query must not be empty")
        if top_k is not None and top_k < 1:
            raise ContextPackInputError("top_k must be at least 1")
        if budget_tokens is not None and budget_tokens < 1:
            raise ContextPackInputError("budget_tokens must be at least 1")

        search_top_k = top_k or self.default_top_k
        search_response = self.search_service.search_knowledge(
            query=normalized_query,
            knowledge_type=knowledge_type,
            canonical_key=canonical_key,
            top_k=search_top_k,
        )
        selected_results = self._select_evidence(search_response.results)
        evidence = self._read_evidence(selected_results)
        sources = self._build_sources(evidence)
        followups = self._build_followups(evidence)
        retrieval_plan = self._build_retrieval_plan(
            search_response=search_response,
            search_top_k=search_top_k,
            budget_tokens=budget_tokens,
        )
        markdown = self._render_markdown(
            query=normalized_query,
            retrieval_plan=retrieval_plan,
            sources=sources,
            evidence=evidence,
            followups=followups,
            budget_tokens=budget_tokens,
        )
        logger.info(
            "context_pack_completed",
            extra={
                "event": "context_pack_completed",
                "knowledge_type": knowledge_type,
                "top_k": search_top_k,
                "evidence_count": len(evidence),
            },
        )
        return ContextPackResponse(
            query=normalized_query,
            retrieval_plan=retrieval_plan,
            sources=sources,
            evidence=evidence,
            followup_read_suggestions=followups,
            context_pack_markdown=markdown,
        )

    def _build_retrieval_plan(
        self,
        *,
        search_response,
        search_top_k: int,
        budget_tokens: int | None,
    ) -> dict:
        query_plan = getattr(search_response, "retrieval_plan", None)
        pass_runs = getattr(search_response, "pass_runs", None)
        retrieval_plan = {
            "provider": "postgres_fts_planned" if query_plan is not None else "postgres_fts",
            "search_top_k": search_top_k,
            "max_evidence": self.max_evidence,
            "max_evidence_per_source": self.max_evidence_per_source,
            "budget_tokens": budget_tokens,
            "budget_is_soft_limit": True,
            "selection": "search_top_k + chunk deduplication + per-source evidence cap",
            "conflict_detection": "not_performed_in_mvp",
        }
        if query_plan is not None:
            retrieval_plan["query_plan"] = query_plan.to_dict()
            retrieval_plan["fusion"] = query_plan.fusion
        if pass_runs is not None:
            retrieval_plan["pass_runs"] = [item.to_dict() for item in pass_runs]
        return retrieval_plan

    def _select_evidence(self, results: list[SearchResult]) -> list[SearchResult]:
        selected: list[SearchResult] = []
        seen_chunks: set[str] = set()
        per_source: Counter[str] = Counter()

        for result in results:
            if result.chunk_id in seen_chunks:
                continue
            if per_source[result.source_id] >= self.max_evidence_per_source:
                continue
            selected.append(result)
            seen_chunks.add(result.chunk_id)
            per_source[result.source_id] += 1
            if len(selected) >= self.max_evidence:
                break
        return selected

    def _read_evidence(self, results: list[SearchResult]) -> list[ContextPackEvidence]:
        evidence: list[ContextPackEvidence] = []
        for index, result in enumerate(results, start=1):
            fragment = self.read_source_service.read_source(chunk_id=result.chunk_id)
            content = self._hydrate_artifacts(content=fragment.content, metadata=result.metadata)
            evidence.append(
                ContextPackEvidence(
                    evidence_id=f"evidence-{index}",
                    chunk_id=result.chunk_id,
                    source_id=result.source_id,
                    version_id=result.version_id,
                    canonical_key=result.canonical_key,
                    title=result.title,
                    source_format=result.source_format,
                    normalized_format=result.normalized_format,
                    knowledge_type=result.knowledge_type,
                    locator=result.citation.locator,
                    line_start=result.citation.line_start,
                    line_end=result.citation.line_end,
                    score=result.score,
                    snippet=result.snippet,
                    content=content,
                    metadata=result.metadata,
                )
            )
        return evidence

    def _hydrate_artifacts(self, *, content: str, metadata: dict) -> str:
        artifact_lines = self._artifact_chunk_lines(metadata)
        linked_lines = self._linked_artifact_lines(metadata)
        if not artifact_lines and not linked_lines:
            return content

        sections = [content]
        if artifact_lines:
            sections.extend(["", "Artifact Details:", *artifact_lines])
        if linked_lines:
            sections.extend(["", "Linked Artifacts:", *linked_lines])
        return "\n".join(sections)

    def _artifact_chunk_lines(self, metadata: dict) -> list[str]:
        artifact_type = metadata.get("artifact_type")
        artifact_id = metadata.get("artifact_id")
        if not isinstance(artifact_type, str) or not isinstance(artifact_id, str):
            return []

        with self.read_source_service.session_factory() as session:
            if artifact_type == "table":
                artifact = TableArtifactRepository(session).get(artifact_id)
                if artifact is None:
                    return []
                return self._table_artifact_lines(artifact)
            if artifact_type == "image":
                artifact = ImageArtifactRepository(session).get(artifact_id)
                if artifact is None:
                    return []
                return self._image_artifact_lines(artifact)
        return []

    def _linked_artifact_lines(self, metadata: dict) -> list[str]:
        linked_artifacts = metadata.get("linked_artifacts")
        if not isinstance(linked_artifacts, list) or not linked_artifacts:
            return []

        artifact_lines: list[str] = []
        with self.read_source_service.session_factory() as session:
            table_repo = TableArtifactRepository(session)
            image_repo = ImageArtifactRepository(session)
            for ref in linked_artifacts:
                if not isinstance(ref, dict):
                    continue
                artifact_type = ref.get("artifact_type")
                artifact_id = ref.get("artifact_id")
                if not isinstance(artifact_id, str):
                    continue
                if artifact_type == "table":
                    artifact = table_repo.get(artifact_id)
                    if artifact is None:
                        continue
                    artifact_lines.extend(self._table_artifact_lines(artifact))
                elif artifact_type == "image":
                    artifact = image_repo.get(artifact_id)
                    if artifact is None:
                        continue
                    artifact_lines.extend(self._image_artifact_lines(artifact))
        return artifact_lines

    def _table_artifact_lines(self, artifact: TableArtifact) -> list[str]:
        return [
            f"- Table {artifact.artifact_key} ({artifact.locator}): {artifact.summary or 'Markdown table'}",
            f"  Columns: {', '.join(artifact.column_names)}; rows: {len(artifact.rows)}",
        ]

    def _image_artifact_lines(self, artifact: ImageArtifact) -> list[str]:
        description = artifact.vision_summary or artifact.alt_text or artifact.caption or artifact.original_uri
        lines = [f"- Image {artifact.artifact_key} ({artifact.locator}): {description}"]
        if artifact.ocr_text:
            lines.append(f"  OCR: {artifact.ocr_text}")
        if artifact.asset_path:
            lines.append(f"  Asset: {artifact.asset_path}")
        if artifact.nearby_text:
            lines.append(f"  Nearby: {artifact.nearby_text}")
        enrichment = artifact.metadata_json.get("image_enrichment")
        if isinstance(enrichment, dict):
            visual_type = enrichment.get("visual_type")
            key_elements = enrichment.get("key_elements")
            confidence = enrichment.get("confidence")
            if isinstance(visual_type, str):
                lines.append(f"  Visual type: {visual_type}")
            if isinstance(key_elements, list) and key_elements:
                elements = [item for item in key_elements if isinstance(item, str)]
                if elements:
                    lines.append(f"  Key elements: {', '.join(elements)}")
            if isinstance(confidence, str):
                lines.append(f"  Vision confidence: {confidence}")
        return lines

    def _build_sources(self, evidence: list[ContextPackEvidence]) -> list[ContextPackSource]:
        source_counts = Counter(item.source_id for item in evidence)
        sources: list[ContextPackSource] = []
        seen: set[str] = set()
        for item in evidence:
            if item.source_id in seen:
                continue
            seen.add(item.source_id)
            sources.append(
                ContextPackSource(
                    source_id=item.source_id,
                    version_id=item.version_id,
                    canonical_key=item.canonical_key,
                    title=item.title,
                    source_format=item.source_format,
                    normalized_format=item.normalized_format,
                    knowledge_type=item.knowledge_type,
                    evidence_count=source_counts[item.source_id],
                )
            )
        return sources

    def _build_followups(self, evidence: list[ContextPackEvidence]) -> list[FollowupReadSuggestion]:
        return [
            FollowupReadSuggestion(
                chunk_id=item.chunk_id,
                source_id=item.source_id,
                version_id=item.version_id,
                locator=item.locator,
                context_lines=2,
                reason="Read surrounding source lines if more local context is needed.",
            )
            for item in evidence
        ]

    def _render_markdown(
        self,
        *,
        query: str,
        retrieval_plan: dict,
        sources: list[ContextPackSource],
        evidence: list[ContextPackEvidence],
        followups: list[FollowupReadSuggestion],
        budget_tokens: int | None,
    ) -> str:
        sections = [
            "# Context Pack",
            "",
            f"Query: {query}",
            "",
            "## Retrieval Plan",
            f"- Provider: {retrieval_plan['provider']}",
            f"- Search top_k: {retrieval_plan['search_top_k']}",
            f"- Evidence cap: {retrieval_plan['max_evidence']}",
            f"- Per-source evidence cap: {retrieval_plan['max_evidence_per_source']}",
            "- Budget: soft limit; no exact tokenizer is used.",
        ]
        if "query_plan" in retrieval_plan:
            query_plan = retrieval_plan["query_plan"]
            sections.append(f"- Intent: {query_plan['intent']}")
            sections.append(f"- Fusion: {retrieval_plan['fusion']}")
            for item in retrieval_plan.get("pass_runs", []):
                sections.append(
                    f"- Pass {item['name']}: results={item['result_count']}, error={item['error_type'] or 'none'}"
                )
        sections.extend(["", "## Sources"])
        if sources:
            for source in sources:
                sections.append(
                    f"- {source.title} ({source.knowledge_type}) - source_id={source.source_id}, "
                    f"version_id={source.version_id}, evidence={source.evidence_count}"
                )
        else:
            sections.append("- No sources matched the query.")
        sections.extend(["", "## Evidence"])

        base_text = "\n".join(sections)
        rendered_evidence: list[str] = []
        truncated = False
        for item in evidence:
            block = "\n".join(
                [
                    f"### {item.evidence_id}: {item.title}",
                    f"- source_id: {item.source_id}",
                    f"- version_id: {item.version_id}",
                    f"- chunk_id: {item.chunk_id}",
                    f"- locator: {item.locator}",
                    f"- score: {item.score:.4f}",
                    "",
                    item.content,
                    "",
                ]
            )
            candidate = "\n".join([base_text, *rendered_evidence, block])
            if budget_tokens is not None and rendered_evidence and self._estimate_tokens(candidate) > budget_tokens:
                truncated = True
                break
            rendered_evidence.append(block)

        if rendered_evidence:
            sections.extend(rendered_evidence)
        else:
            sections.append("- No evidence selected.")
        if truncated:
            sections.append("- Evidence list truncated by soft budget_tokens limit.")

        sections.extend(["", "## Followup Read Suggestions"])
        if followups:
            for item in followups[: len(rendered_evidence) or len(followups)]:
                sections.append(
                    f"- read_source(chunk_id={item.chunk_id}, context_lines={item.context_lines}) "
                    f"for {item.locator}"
                )
        else:
            sections.append("- No followup reads available.")

        sections.extend(
            [
                "",
                "## Conflicts / Caveats",
                "- MVP retrieval uses PostgreSQL full-text search only; semantic recall and reranking are not performed.",
                "- Real conflict detection is not performed in MVP.",
                "- budget_tokens is a soft Markdown length hint, not an exact token guarantee.",
            ]
        )
        return "\n".join(sections)

    def _estimate_tokens(self, text: str) -> int:
        return max(1, len(text) // 4)
