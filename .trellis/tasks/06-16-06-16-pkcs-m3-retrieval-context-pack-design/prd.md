# brainstorm: PKCS M3 retrieval and Context Pack design

## Goal

敲定 PKCS M3 的设计细节：在 M1+M2 已有的 ingest、FTS search、read_source、Context Pack v0、artifact hydration 基础上，设计一版可实施的检索编排与 Context Pack v1 路线。M3 的目标不是新增更多资料类型，而是让现有资料搜得更准、证据更可靠、Context Pack 更适合主 Agent 使用。

## What I already know

* 用户希望接下来专注做 M3，并通过讨论最终敲定一版 M3 设计。
* M1+M2 已完成：CLI/HTTP/MCP、Raw Archive、PostgreSQL metadata、FTS search、read_source、Context Pack v0、synthetic eval corpus。
* 后续已完成：database modeling cleanup、Markdown block graph、table/image artifact、Context Pack artifact hydration、Docling-backed `prepare-ingest`、image enrichment sidecar、raw archive image link preservation。
* 当前 `SearchProvider` 只有 `PostgresFTSSearchProvider`，搜索结果已包含 `source_id`、`version_id`、`canonical_key`、format、knowledge type、score、citation、metadata。
* 当前 `ContextPackService` 流程是：单次 `search_knowledge` -> chunk dedup -> per-source cap -> `read_source` -> artifact hydration -> Markdown render。
* 当前 Context Pack v0 的 caveats 是固定模板，未做真正 source trust、freshness、conflict/caveat 推断。
* 当前测试覆盖 Context Pack shape、evidence cap、soft budget、artifact hydration、CLI/MCP smoke；acceptance eval 主要验证 top 5/top 10 检索阈值。
* 项目约束：不要让 LangChain/LlamaIndex/Haystack/pgvector/reranker 接管核心 source/version/chunk/citation/Raw Archive/read_source 模型。
* 用户指出：baseline 必须针对一批材料；当前项目还没有一批可作为 M3 baseline 的稳定材料。
* 现有 `tests/fixtures/` 只有 10 个小 Markdown/text 和 10 个小 conversation fixture，适合 MVP smoke，不足以代表 M3 检索质量。
* `data/private/acceptance-inputs/` 和 `data/private/ingest-prep/` 中已有若干真实/半真实验收材料，但它们是 gitignored private data，尚未整理成稳定 corpus manifest。

## Assumptions (temporary)

* M3 应优先提高现有 `document` 与 `ai_conversation` 的检索和 Context Pack 质量，不在 M3 第一阶段新增 code/email/entity 等知识类型。
* M3 不应破坏现有 MCP tool 名称；`get_context_pack` 可以向后兼容地增加返回字段。
* M3 的第一步应建立质量 baseline，否则后续 router/fusion/rerank 是否有效无法判断。
* pgvector / reranker 可以作为 M3 后段 spike，但不应成为 M3 的起点。

## Open Questions

* M3A baseline corpus 采用哪种来源组合：只做可提交 synthetic/curated corpus，还是同时维护 gitignored private corpus manifest？

## Requirements (evolving)

* M3 必须保持 evidence 可追溯：所有 Context Pack evidence 继续能映射到 `source_id`、`version_id`、`chunk_id` 或 locator。
* M3 必须有可重复运行的检索与 Context Pack 质量评测。
* M3 应设计内部 `RetrievalPlan`，用于记录 query intent、retrieval passes、filters、selection/fusion/caveat 策略。
* M3 应支持 multi-pass lexical retrieval，而不是每次只把原始 query 丢给 FTS。
* M3 应让 Context Pack 输出更明确的 source trust、freshness/caveat、follow-up read 建议。
* M3 应继续复用现有 `SearchService`、`ReadSourceService`、`ContextPackService`，避免把检索逻辑复制到 CLI/MCP。
* M3 已确认采用 baseline-first 路线：先建立可重复质量基线，再实现 QueryRouter / lexical fusion / Context Pack v1，最后才评估 semantic/rerank。
* M3A baseline 必须分开衡量 search quality 与 Context Pack quality；不能只用 top_k hit rate 代表上下文可用性。
* M3A baseline 必须保留当前 MVP marker-based eval 的确定性，同时新增更接近真实问题的 no-marker eval。
* M3A baseline 前必须先建设 corpus；没有稳定 corpus 时不实现 QueryRouter、fusion 或 reranker。
* M3 baseline corpus 至少分成 committed CI corpus 和 optional private local corpus 两层，避免把私密资料提交到仓库。

## Acceptance Criteria (evolving)

* [ ] M3 设计明确分期：baseline、router、fusion、Context Pack v1、semantic/rerank spike。
* [ ] M3 设计明确哪些字段可以加入 `retrieval_plan` 和 Context Pack response。
* [ ] M3 设计明确 eval schema 与质量指标。
* [ ] M3 设计明确不在第一阶段新增哪些重依赖或资料类型。
* [ ] 用户确认 M3 MVP 范围和第一批 PR 顺序。
* [x] 用户确认 M3 采用 baseline-first 总路线。

## Definition of Done (team quality bar)

* M3 PRD 被用户确认。
* M3 设计包含目标、范围、技术方案、分期、小 PR 顺序、验收标准、明确范围外。
* 如进入实现，先配置 Trellis context，再按 PR 粒度实现和验证。
* 实现阶段必须跑 Docker-backed tests；设计阶段只需 Trellis task validate 和 JSON/Markdown 基本检查。

## Research Notes

### Similar tools / patterns

* LlamaIndex 将 query engine 定义为面向自然语言 query 的接口，通常通过一个或多个 retriever / index 组合形成更复杂能力。
* Haystack 将 retrieval 与 reranking 作为显式 pipeline components；ranker 通常放在 retriever 后面，并建议控制 retriever `top_k` 以避免性能失控。
* MCP Resources 适合后续做 browseable source/context access，但主动搜索、证据读回、Context Pack 仍应通过 PKCS tools 完成。
* pgvector 可以在 PostgreSQL 内增加 vector similarity，但在 PKCS 中应作为 optional adapter，而不是替代 FTS/Raw Archive/citation 模型。

### Constraints from current repo

* 当前搜索只有 FTS provider，`SearchProvider` 已经是扩展点。
* 当前 Context Pack selection 非常简单，只按搜索顺序、chunk dedup、per-source cap 选 evidence。
* 当前 artifacts 已能被 Context Pack hydrate，因此 M3 不需要先补 artifact 基础链路。
* 当前 eval 重点是 search hit rate，尚未衡量 Context Pack 证据支持度、source trust、caveat 质量。

## Feasible Approaches

### Approach A: Baseline-first M3 (Recommended)

How it works:

* 先扩展 eval schema 和测试，记录当前 FTS + Context Pack v0 baseline。
* 再实现内部 `RetrievalPlan` / QueryRouter v1。
* 再实现 multi-pass lexical retrieval + fusion。
* 再升级 Context Pack v1 rendering/selection/caveats。
* 最后以 feature flag/spike 评估 pgvector 或 reranker。

Pros:

* 每一步都有质量对比，避免凭感觉加复杂检索。
* 依赖最少，符合当前轻量架构。
* 能复用现有 SearchProvider、ContextPackService 和 tests。
* 风险最低，适合 M3 第一版。

Cons:

* 语义召回不会立刻提升。
* 前期会花时间建设评测，而不是马上做“看起来更智能”的功能。

Status:

* Selected by user on 2026-06-17.

### Approach B: Router/fusion-first M3

How it works:

* 先实现 `RetrievalPlan` 和多路 FTS query。
* 后补 eval 和 Context Pack 质量指标。

Pros:

* 迭代体验更快，较快看到 Context Pack 内容变化。
* 可以直接围绕当前真实文档痛点调 query planning。

Cons:

* 没有 baseline 时很难判断改动是否真的变好。
* 容易把单个样例调优成通用逻辑。

### Approach C: Semantic-first M3

How it works:

* 先引入 pgvector 或 reranker，再围绕 hybrid retrieval 设计 router/fusion。

Pros:

* 自然语言宽查询可能更快改善。
* 更接近长期 hybrid retrieval 方向。

Cons:

* 依赖、资源、embedding model、reindex、测试成本都更高。
* 会过早引入模型选择和可重复性问题。
* 如果没有 baseline，无法证明 semantic/rerank 值得保留。

## Expansion Sweep

### Future evolution

* M3 的 `RetrievalPlan` 将成为 M4 code/email/entity profiles 的入口，因此字段要能表达 intent、source profile、retrieval passes、fusion method 和 caveat policy。
* M3 的 eval harness 将成为 M5 个人知识回归测试的基础，因此不应只服务当前 synthetic fixtures。

### Related scenarios

* `search_knowledge` 应继续作为基础工具；`get_context_pack` 可以内部使用更复杂 orchestration，但不应让调用方承担复杂参数。
* `read_source` 的证据读回合同不能因为 Context Pack v1 变化而变复杂。

### Failure and edge cases

* Router 误判时应退回 broad lexical retrieval，而不是返回空 evidence。
* Fusion 应保留来源/pass 信息，方便 debug。
* Context Pack caveats 应明确资料类型、过时风险、证据不足，而不是假装做了完整冲突检测。

## Proposed M3 MVP Shape

### M3A0: Baseline corpus bootstrap

Problem:

* 当前没有一批真正可用的 M3 baseline 材料。
* MVP fixtures 太短、太人工、带 anchor，能防回归但不能衡量真实检索质量。
* private 目录有真实验收资料，但未形成 manifest、query set、expected evidence，因此不能直接作为 baseline。

Corpus tiers:

1. **Tier 0: MVP regression corpus**
   * 位置：现有 `tests/fixtures/`。
   * 作用：继续验证基础 ingest/search/read/context-pack 不坏。
   * 特点：小、可提交、确定性强、marker/anchor query。
   * 不作为 M3 质量判断主依据。
2. **Tier 1: committed M3 curated corpus**
   * 位置建议：`tests/fixtures/m3_corpus/` 与 `tests/fixtures/m3_eval_queries.jsonl`。
   * 内容：非私密、可提交、较长、接近真实问题的材料。
   * 建议规模：第一版 12-20 份资料，30-50 条 no-marker query。
   * 类型覆盖：official docs 摘要/节选、项目设计笔记、AI conversation 摘要、artifact-heavy Markdown、冲突/过时示例。
   * 原则：不使用真实私密内容；可以手写 realistic synthetic docs，也可以使用允许提交的公开资料节选，但要避免大体积和版权风险。
3. **Tier 2: gitignored private acceptance corpus**
   * 位置建议：`data/private/m3-baseline/manifest.json` 与 `data/private/m3-baseline/eval_queries.jsonl`。
   * 内容：本机已有真实/半真实资料，例如官方技术文档、ML-For-Beginners Markdown、arXiv normalized package、真实 ingest-prep 输出。
   * 作用：人工/本地质量验收，不进入 CI，不提交原文。
   * 报告：只提交结构说明或手工验收摘要，不提交 private source content。

Recommended M3A0 output:

```text
tests/fixtures/m3_corpus/
  documents/
  conversations/
  artifacts/
tests/fixtures/m3_eval_queries.jsonl
data/private/m3-baseline/
  manifest.json
  eval_queries.jsonl
  reports/
```

Tier 1 eval row draft:

```json
{
  "query": "为什么 Context Pack 需要 caveats，而不是直接给最终答案？",
  "query_type": "context_pack_quality",
  "expected_fixture": "m3_corpus/documents/context-pack-trust.md",
  "expected_canonical_keys": ["m3:{run_id}:documents/context-pack-trust.md"],
  "expected_knowledge_types": ["document"],
  "expected_evidence_terms": ["caveats", "not final answer", "source traceability"],
  "must_not_canonical_keys": [],
  "support_required": true,
  "notes": "No-marker natural phrasing for Context Pack caveat behavior."
}
```

Tier 2 manifest draft:

```json
{
  "schema_version": 1,
  "sources": [
    {
      "path": "data/private/acceptance-inputs/2026-06-10-mcp-real-docs/openai-latest-model.md",
      "knowledge_type": "document",
      "canonical_key": "private-m3:openai-latest-model",
      "tags": ["official_doc", "openai"]
    }
  ]
}
```

M3A0 acceptance:

* Tier 1 committed corpus has at least 12 source files and 30 no-marker eval queries.
* Tier 1 query set covers at least: exact lookup, broad project memory, official doc lookup, AI conversation lookup, artifact lookup, caveat/trust behavior.
* Tier 2 private corpus manifest exists locally or is explicitly deferred; no private source content is committed.
* Each query defines expected source and at least one expected evidence term.
* Existing MVP eval remains unchanged and passing.

### M3A1: Retrieval and Context Pack quality baseline

* 扩展 `tests/fixtures/eval_queries.jsonl` 或新增 M3 eval fixture。
* 增加字段：`query_type`、`expected_evidence_terms`、`must_not_canonical_keys`、`preferred_knowledge_types`、`support_required`。
* 输出 baseline report：top 5、top 10、Context Pack evidence count、evidence support checks、must-not violations。

Detailed baseline design:

1. **Keep the MVP deterministic eval**
   * 保留现有 `tests/fixtures/eval_queries.jsonl` 的 marker-based 检索测试。
   * 目的：证明基础 ingest/search 没坏，继续作为 regression guard。
   * 不把它当 M3 质量上限，因为 marker query 太容易命中，不代表真实问题。
2. **Add M3 no-marker eval set over the new corpus**
   * 新增 `tests/fixtures/m3_eval_queries.jsonl` 或等价文件，并指向 M3A0 corpus。
   * query 不拼 marker，尽量模拟真实用户问法。
   * 每行包含 expected source、expected evidence terms、must-not source、query type、notes。
3. **Measure search quality**
   * `top_1_hit`
   * `top_5_hit`
   * `top_10_hit`
   * `expected_source_rank`
   * `must_not_violations`
   * `empty_result_count`
4. **Measure Context Pack quality**
   * `evidence_count`
   * `sources_count`
   * `expected_evidence_terms_found`
   * `all_evidence_traceable`
   * `must_not_sources_in_pack`
   * `followup_read_suggestions_count`
   * `caveats_present`
5. **Add a JSON baseline report**
   * 输出到 gitignored/private path 或 pytest captured output，不提交真实运行数据。
   * 报告字段包括 run id、query count、hit rates、context support rates、failed cases。
   * 后续 M3B/M3C/M3D 每次改变 retrieval/Context Pack 都对比该 report。

Draft M3 eval row:

```json
{
  "query": "为什么 Context Pack 需要 caveats，而不是直接给最终答案？",
  "query_type": "context_pack_quality",
  "expected_fixture": "markdown/context-pack-caveats.md",
  "expected_canonical_keys": ["eval:{run_id}:markdown/context-pack-caveats.md"],
  "expected_knowledge_types": ["document"],
  "expected_evidence_terms": ["Conflicts / Caveats", "未做真正冲突检测"],
  "must_not_canonical_keys": [],
  "support_required": true,
  "notes": "No-marker natural phrasing for Context Pack caveat behavior."
}
```

Proposed M3A acceptance thresholds:

* MVP marker-based eval continues to pass existing top 10 >= 80% and top 5 >= 60%.
* M3 no-marker eval initially records baseline without failing on strict thresholds.
* M3 no-marker eval must fail only on structural issues: invalid row shape, untraceable evidence, malformed Context Pack, or read_source mapping failure.
* After first baseline is recorded, later M3 PRs may set minimum non-regression thresholds.

Baseline command shape:

```text
uv run pytest tests/test_acceptance.py -k m3
```

or, if the logic grows beyond a test-only helper:

```text
uv run pkcs eval --suite m3 --output data/private/eval-runs/<run-id>.json
```

The first implementation should prefer pytest-only helpers unless the command-line report proves necessary.

## Decision (ADR-lite)

### ADR-001: M3 Starts With Baseline

**Context**: Current PKCS has a deterministic MVP retrieval eval, but it mostly measures marker-assisted search hit rate. M3 aims to improve real query handling and Context Pack usefulness, so adding router/fusion/rerank without a quality baseline would make regressions hard to detect.

**Decision**: M3 uses baseline-first sequencing. M3A establishes retrieval and Context Pack quality baselines before QueryRouter, lexical fusion, Context Pack v1, or semantic/rerank spike.

**Consequences**: Early M3 work spends time on eval design and reports instead of immediately changing retrieval behavior. In exchange, every later retrieval change can be judged against explicit search and Context Pack quality metrics.

### ADR-002: M3 Baseline Requires Corpus First

**Context**: Existing MVP fixtures are intentionally small and marker-heavy. They are useful regression tests but not a meaningful baseline for M3 retrieval and Context Pack quality. Current private data contains useful material, but it is not organized into a stable corpus and must not be committed.

**Decision**: M3A starts with corpus bootstrap. Build a committed, non-private M3 curated corpus for CI and optionally maintain a gitignored private corpus manifest for local quality checks.

**Consequences**: M3 implementation starts one step earlier than originally planned. QueryRouter, fusion, and reranker work wait until there is a stable batch of material and queries to measure against.

### M3B: RetrievalPlan / QueryRouter v1

Internal dataclass draft:

```python
@dataclass(frozen=True)
class RetrievalPlan:
    query: str
    intent: str
    filters: dict[str, str | None]
    passes: list[RetrievalPass]
    fusion: str
    evidence_policy: dict[str, Any]
    caveat_policy: dict[str, Any]
```

Initial intents:

* `exact_lookup`
* `project_memory`
* `official_doc_lookup`
* `ai_conversation_lookup`
* `artifact_lookup`
* `broad_recall`

### M3C: Multi-pass lexical retrieval + fusion

Candidate pass types:

* `original_query`: 当前 query 原样 FTS。
* `keyword_terms`: 提取更短关键词做 FTS。
* `title_heading`: 重点命中 title / heading_path。
* `artifact_text`: 重点命中 table/image summary、OCR、vision summary。
* `knowledge_type_scoped`: 在用户显式或 router 推断的 knowledge type 内搜索。

Fusion v1:

* 使用 deterministic score blending 或 reciprocal-rank style score。
* 保留 `retrieval_passes` metadata，说明每条 result 被哪些 pass 命中。
* 按 `source_id + chunk_id` 去重，source diversity 由 Context Pack selection 继续处理。

### M3D: Context Pack v1

Additive response fields:

* `retrieval_plan.intent`
* `retrieval_plan.passes`
* `retrieval_plan.fusion`
* `retrieval_plan.selection`
* optional `answer_hints`
* richer `followup_read_suggestions.reason`

Markdown sections:

```markdown
# Context Pack
## Query
## Retrieval Plan
## High-Level Answer Hints
## Sources
## Evidence
## Followup Read Suggestions
## Conflicts / Caveats
```

Caveat rules v1:

* AI conversation evidence is personal memory, not official truth.
* Low evidence count means answer should be treated as incomplete.
* Old source versions or ambiguous source types get explicit caveats where metadata supports it.
* Real contradiction detection remains out of scope unless M3 later explicitly adds it.

### M3E: Semantic/rerank spike

* Evaluate only after M3A-D.
* Must be feature-flagged or isolated as adapter.
* Must report eval delta, runtime cost, dependency cost, and rollback path.

## Out of Scope (explicit)

* 不在 M3 第一版新增 code repository ingest、email ingest、entity/wiki profile。
* 不把 pgvector、OpenSearch、reranker 作为 M3 起点。
* 不改变 Raw Archive、source/version/chunk/citation 的 source-of-truth 角色。
* 不让 Context Pack 自动生成最终答案；它只提供证据、提示、caveats 和后续阅读建议。
* 不做完整冲突检测；M3 v1 只做规则化 caveat。

## Technical Notes

Files inspected:

* `src/pkcs/search/models.py`
* `src/pkcs/search/providers.py`
* `src/pkcs/search/service.py`
* `src/pkcs/context_pack/models.py`
* `src/pkcs/context_pack/service.py`
* `tests/test_context_pack.py`
* `tests/test_acceptance.py`
* `tests/fixtures/eval_queries.jsonl`
* `tests/fixtures/`
* `data/private/acceptance-inputs/`
* `data/private/ingest-prep/`
* `.trellis/tasks/06-03-pkcs-project-plan/prd.md`
* `.trellis/tasks/06-03-pkcs-mvp-m1-m2/m1-m2-mvp-task-report.md`
* `.trellis/spec/backend/directory-structure.md`
* `.trellis/spec/backend/quality-guidelines.md`
