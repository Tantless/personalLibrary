# brainstorm: PKCS M3B mixed-language query planner

## Goal

设计 M3B：在不引入向量库、LLM、机翻依赖的第一步里，让 PKCS 从“原句直接丢给 PostgreSQL FTS”升级为“先生成可解释的检索计划，再多路 lexical retrieval + fusion”。M3B 要解决 M3A1 baseline 暴露的 0 召回问题，同时为后续 multilingual embeddings / LLM query planner 留接口。

## What I already know

* M3A1 baseline evaluator 已完成，并已在本地 M3 corpus v1 上跑过。
* M3 corpus v1 当前有 100 sources、4248 chunks，英文 title-style smoke queries 能命中预期 sources。
* `tests/fixtures/m3_eval_queries.jsonl` 的 6 条中文/混合语言自然问题在当前 `simple` FTS 下全部 empty result。
* 当前 `SearchService.search_knowledge()` 只接受单个 query，调用 `PostgresFTSSearchProvider` 单路 FTS。
* 当前 `ContextPackService` 只做一次 search，然后按 search 顺序选 evidence。
* 项目约束仍然是：不要让 LangChain/LlamaIndex/Haystack/pgvector/OpenSearch/reranker 接管核心 source/version/chunk/citation/Raw Archive/read_source 模型。
* 用户关心“治本”：未来知识库可能有中文、英文、日文资料，不能长期靠手写中文词典。

## Assumptions

* M3B MVP 先解决“明显可修的 query 表达问题”，不把 semantic/vector 检索提前塞进同一个 PR。
* M3B 的关键产物不是最终答案，而是可审计的 `RetrievalPlan`：系统为什么搜这些 query、每个结果来自哪些 pass、fusion 怎么算。
* 小型术语表可以作为第一版 lexical expansion 的一个组件，但不能成为长期跨语言方案。
* 长期“语言无关召回”需要 multilingual semantic retrieval + lexical hybrid fusion；M3B 应保留这个扩展点。

## Requirements (evolving)

* 新增 query planning 层，把用户 query 转成显式 `RetrievalPlan`。
* `RetrievalPlan` 至少包含：
  * 原始 query
  * intent
  * passes
  * fusion method
  * generated terms / entities / aliases 的调试信息
* 第一版 passes 建议包括：
  * `original`: 原句
  * `ascii_entity`: query 中显式英文实体、缩写、版本号
  * `glossary_expansion`: 小型技术术语扩展
  * `source_alias`: 从 corpus title / canonical_key / heading 中得到的 source/product alias
  * `combined`: entity + alias + expansion terms
* 新增 multi-pass lexical retrieval，复用现有 `SearchService` 或 `SearchProvider`，不能在 CLI/MCP/Context Pack 里复制 SQL。
* Fusion 必须按 chunk/source 去重，并保留每个结果被哪些 pass 命中。
* M3B 完成后，用同一套 `tests/fixtures/m3_eval_queries.jsonl` 对比 M3A1 baseline。
* M3B 必须保持 evidence 可追溯：所有 Context Pack evidence 仍能 read back 到 `chunk_id/source_id/version_id/locator`。

## Acceptance Criteria (evolving)

* [x] M3B 设计明确 `RetrievalPlan` 和 `RetrievalPass` 的字段。
* [x] M3B 设计明确 first-pass lexical planner 的规则来源：entity extractor、glossary、source alias。
* [ ] M3B 设计明确 fusion 方法和去重 key。
* [ ] M3B 设计明确哪些功能延期到 semantic/vector 阶段。
* [x] 用户确认 M3B MVP 范围。
* [ ] 实现阶段必须跑 M3A1 baseline，对比 top_10 hit / context_support / empty_result_count。

## Technical Approach

### First principle

当前失败不是 corpus 不存在，而是 query 表达和 corpus 表达不在同一语言/词面空间。M3B 不尝试“理解所有语言”，而是先让 query 进入多个更可能命中的词面空间：

```text
用户原句
  -> 原句 pass
  -> 英文实体 pass
  -> 术语扩展 pass
  -> source/title alias pass
  -> combined pass
  -> FTS 多路搜索
  -> fusion / dedup
  -> Context Pack evidence selection
```

### Example

Input:

```text
Agents SDK 如何处理工具调用？
```

Planned output:

```json
{
  "intent": "official_doc_lookup",
  "passes": [
    {"name": "original", "query": "Agents SDK 如何处理工具调用？"},
    {"name": "ascii_entity", "query": "Agents SDK"},
    {"name": "glossary_expansion", "query": "tools function tools tool calling function calling"},
    {"name": "source_alias", "query": "OpenAI Agents Python Tools docs"},
    {"name": "combined", "query": "OpenAI Agents Python tools function tools"}
  ],
  "fusion": "reciprocal_rank_v1"
}
```

### Why not fixed whole-sentence dictionary

Do not map entire questions to searches. That would overfit the eval set.

Allowed:

* Small technical term mapping: `工具调用 -> tools/function tools/tool calling`.
* Product/entity extraction from query text.
* Alias discovery from corpus metadata.

Not allowed:

* `Agents SDK 如何处理工具调用？ -> OpenAI Agents Python Tools docs` as a hardcoded full-query rule.

## Feasible Approaches

### Approach A: Deterministic lexical planner first (Recommended)

How it works:

* Add `pkcs.retrieval` or `pkcs.search.planning` module.
* Build `RetrievalPlan` from regex/entity extraction, small glossary, and source-title aliases.
* Run multiple FTS passes.
* Fuse results deterministically.
* Feed fused results into Context Pack selection.

Pros:

* Low dependency and privacy risk.
* Deterministic, easy to test, easy to debug.
* Directly addresses current M3A1 empty-result baseline.
* Creates the same orchestration shell needed for later embeddings/LLM passes.

Cons:

* Not a complete cross-language solution.
* Needs small curated terminology for current corpus.
* Japanese/general multilingual recall remains limited until semantic retrieval.

Status:

* Selected by user on 2026-06-22. M3B MVP will implement Approach A only.

### Approach B: Add query-only translation as one pass

How it works:

* Add a translation/rewrite adapter that produces English query variants.
* The translated query becomes one retrieval pass beside deterministic passes.
* If translation fails or is disabled, deterministic planner still runs.

Pros:

* Better coverage for natural Chinese/Japanese queries over English docs.
* Can improve recall before embedding infrastructure exists.

Cons:

* Adds model/API dependency, latency, privacy questions, caching, and failure handling.
* Translation can erase exact product/API terms or introduce wrong terms.
* Harder to keep tests deterministic unless the translated output is stubbed.

### Approach C: Jump straight to multilingual semantic + hybrid search

How it works:

* Add embeddings for chunks.
* Store vectors, likely with pgvector.
* Search query by vector similarity and fuse with lexical FTS.

Pros:

* This is closer to the long-term answer for Chinese/English/Japanese mixed corpora.
* Handles semantic paraphrase and cross-language query/document mismatch better than lexical rules.

Cons:

* Bigger schema, dependency, reindex, model-selection, and cost surface.
* Requires a stronger eval suite before rollout.
* Delays fixing the known M3A1 zero-recall baseline with a smaller PR.

## Research Notes

* PostgreSQL full text search is term/configuration based: documents become `tsvector`, user input becomes `tsquery`, and ranking depends on matched query terms. This explains why mixed-language natural questions can fail even when English title queries work. Source: https://www.postgresql.org/docs/current/textsearch-controls.html
* PostgreSQL text search configurations bind parsers and dictionaries, so language behavior is explicitly configuration-dependent. Source: https://www.postgresql.org/docs/current/textsearch-configuration.html
* Search systems often use language-aware analyzers/tokenizers for CJK text; Elastic's ICU tokenizer explicitly targets better tokenization for Chinese/Japanese/Korean among other languages. Source: https://www.elastic.co/guide/en/elasticsearch/plugins/8.19/analysis-icu-tokenizer.html
* OpenSearch describes hybrid search as combining keyword and semantic search, with score normalization/combination at search time. This matches the long-term PKCS direction after M3B. Source: https://docs.opensearch.org/latest/vector-search/ai-search/hybrid-search/index/
* pgvector stores vectors in Postgres and supports exact/approximate nearest-neighbor search. It is a plausible future adapter because PKCS already uses PostgreSQL. Source: https://github.com/pgvector/pgvector

## Expansion Sweep

### Future evolution

* M3B planner should allow future pass types such as `translation`, `embedding`, `rerank`, or `source_profile` without changing Context Pack's external tool contract.
* M4 source profiles can reuse `intent` and pass metadata to treat official docs, AI conversation memory, and code docs differently.

### Related scenarios

* `search_knowledge` should remain a simple basic search tool.
* `get_context_pack` can use planned/fused retrieval internally because it is already the higher-level evidence assembly tool.

### Failure and edge cases

* If planning produces no useful terms, fallback to original query.
* If one pass errors or returns no rows, the full retrieval should continue.
* Fusion must avoid returning many duplicate chunks from one source unless evidence policy intentionally allows it.
* Planner must not log raw query text by default because query text can contain private intent.

## Proposed MVP Scope

Include:

* Query planner dataclasses.
* Deterministic entity extractor.
* Small glossary extension point with a starter technical glossary.
* Source alias pass using source titles/canonical keys/headings where available.
* Multi-pass FTS orchestration.
* Deterministic fusion with per-result pass metadata.
* M3 eval comparison against M3A1.

Exclude:

* Embeddings / pgvector.
* LLM query planner.
* Machine translation adapter.
* Reranker.
* Full language-specific analyzers for Chinese/Japanese.

## Open Questions

* None for MVP scope. User selected Approach A on 2026-06-22.

## Decision (ADR-lite)

### ADR-003: M3B Starts With Deterministic Lexical Planning

**Context**: M3A1 baseline shows Chinese natural questions over mostly English corpus content return 6/6 empty results with current PostgreSQL `simple` FTS, while English title-style smoke queries hit the expected sources. The project needs a concrete improvement path before introducing translation, embeddings, LLM query planning, or reranking.

**Decision**: M3B MVP implements deterministic query planning and multi-pass lexical retrieval only. It includes entity extraction, a starter technical glossary, corpus/source alias expansion, multi-pass FTS, deterministic fusion, and retrieval-plan debug metadata. It does not implement machine translation, LLM query planning, embeddings, pgvector, reranking, or language-specific analyzer changes.

**Consequences**: This is not the final cross-language retrieval architecture, but it is low-risk, testable, private, and directly targets the current baseline failure. The planned data structures and pass metadata must leave room for later `translation`, `embedding`, and `rerank` pass types.

## Implementation Plan

### PR1: Planner data structures and deterministic planning

* Add retrieval planning models, likely under `src/pkcs/search/planning.py` or `src/pkcs/retrieval/`.
* Implement `RetrievalPlan`, `RetrievalPass`, and conservative intent labels.
* Implement ASCII/entity extraction and starter glossary expansion.
* Add unit tests for example queries from `tests/fixtures/m3_eval_queries.jsonl`.

Verification:

* Planner tests assert pass names, query strings, intent fallback, and no whole-query hardcoding.

Status:

* Completed on 2026-06-22 in `src/pkcs/search/planning.py`.
* Tests added in `tests/test_search_planning.py`.
* This PR-sized step does not execute multi-pass search yet; PR2 will wire planned passes into retrieval and fusion.

### PR2: Multi-pass lexical retrieval and fusion

* Add orchestration that runs planned passes through existing search provider/service boundaries.
* Deduplicate by `chunk_id` first, then preserve `source_id` diversity signals.
* Add deterministic fusion metadata showing pass hits and fused score/rank.

Verification:

* Search tests use synthetic fixtures to prove multiple passes can recover expected sources where original query alone fails.
* M3 baseline report improves empty-result count and top_10 hit rate for current M3 eval fixture.

### PR3: Context Pack integration

* Let `ContextPackService` use planned/fused retrieval internally while preserving the existing MCP/CLI outward contract.
* Add retrieval plan details to Context Pack response/Markdown only as additive fields/sections.
* Preserve `read_source` traceability for every evidence item.

Verification:

* Context Pack tests assert evidence remains traceable and `retrieval_plan` includes pass/fusion metadata.
* Full Docker-backed pytest passes.

## Definition of Done

* PRD scope confirmed by user.
* Implementation PR must include tests for planning output, multi-pass fusion, and M3 eval improvement.
* Docker-backed tests pass.
* No search evidence traceability regression.
