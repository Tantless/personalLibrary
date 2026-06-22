# PKCS M3E targeted alias and evidence selection follow-up

## Goal

M3E 的目标是修复 M3D report-only baseline 暴露出的两个具体失败模式：中文 alias 召回缺口和 Context Pack 证据选择缺口。这个任务只做小范围、可解释、可测试的确定性改动，不引入 translation、LLM planner、embedding、pgvector、reranker 或 language-specific analyzer。

## What I already know

* M3D locked + diagnostic report 共 28 行，`planned_top_10_hit_rate=0.9643`，`locked_regression_pass_rate=1.0`。
* 剩余失败集中在 2 行：
  * `哪份报告总结了日本动画行业 2025 年的数据？` 没有命中 `m3-corpus:anime:aja-anime-industry-report-2025-summary`，failure class 为 `missing_alias`。
  * `哪个游戏引擎说明文档描述了实体组件系统能力？` 已命中 `m3-corpus:game:bevy-readme` rank 4，但 Context Pack 没选到包含 `ECS` / `game engine` 的证据，failure class 为 `evidence_selection_gap`。
* `QueryPlanner` 当前通过 `DEFAULT_TECHNICAL_GLOSSARY`、ASCII entity extraction、source alias metadata 生成 retrieval passes。
* source alias matching 使用 query、ASCII entities、glossary terms 组成的 signal text；只要中文触发词能扩展到英文标题/terms，就能进入 `source_alias` 和 `combined` pass。
* `ContextPackService._select_evidence()` 当前只按 search results 顺序、chunk 去重、per-source cap 选 evidence；它不看 query terms，也不优先选能覆盖 query/glossary/source alias 术语的 chunk。

## Assumptions

* M3E 第一版可以通过小型 glossary 扩展覆盖当前中文失败行，而不是建立固定 query 字典。
* Evidence selection 可以先做 deterministic lexical scoring：在 search rank 基础上，对 snippet/title/metadata 中包含 query terms、ASCII entities、glossary expansions、source alias titles 的 chunk 加分。
* Diagnostic rows 仍然是 report-only，不在本任务中设置硬 CI 阈值。

## Requirements

* 修复中文 AJA 行的 planned top-10 命中，不写固定 query-to-source 映射。
* 修复 Bevy 中文行的 planned Context Pack support，使返回 evidence 覆盖 `ECS` 和 `game engine`。
* 保持 locked regression rows 100% 通过。
* 保持 M3D diagnostic fixture 与 M3 comparison evaluator 可用。
* Context Pack selection 的逻辑必须稳定、可测试，并保持现有 evidence cap、per-source cap 和 chunk deduplication 约束。
* 不提交 private report 内容；新 report 只写入 `data/private/eval-runs/`。

## Acceptance Criteria

* [ ] 新增或更新 query planning 测试，证明中文行业报告问法会生成能命中 AJA report 的 alias/combined pass。
* [ ] 新增或更新 Context Pack 测试，证明当同一 source 有多个候选 chunk 时，能优先选择覆盖 query/expanded terms 的 evidence。
* [ ] 重新生成 M3E private comparison report，`missing_alias=0` 且 `evidence_selection_gap=0`，locked regression 仍为 100%。
* [ ] `uv run pytest tests\test_search_planning.py tests\test_context_pack.py tests\test_m3_eval.py -q` 通过。
* [ ] `uv run pytest` 通过。
* [ ] `git diff --check` 通过。

## Definition of Done

* PRD、task metadata、task report 与实现同步。
* Tests 覆盖 alias/glossary 和 Context Pack evidence selection 行为。
* 本地 private report 生成并在 task report 中只记录 summary/failure classes。
* 每个 PR-sized step 提交一次。

## Technical Approach

M3E 分两层做确定性修复：

1. Query planning alias/glossary:
   * 在 `DEFAULT_TECHNICAL_GLOSSARY` 中加入少量通用中文触发词，例如“动画行业”“日本动画”“行业报告”“数据”，扩展到 `Anime Industry Report`、`Japan Anime Data`、`AJA` 等公开 source/title 术语。
   * 不加入完整 query，也不把某个中文句子直接映射到 canonical key。

2. Context Pack evidence selection:
   * 从 normalized query 和 planned retrieval metadata 中提取 selection terms。
   * 对 search results 做稳定排序：先按 lexical coverage score，再保留原 search rank 作为 tie-breaker。
   * 仍然执行 chunk deduplication、per-source cap、max evidence cap。
   * retrieval plan 中记录 selection 策略，方便 report 和调试。

## Decision (ADR-lite)

**Context**: M3D 只剩两个失败模式，并且不是大规模 semantic gap。直接引入 translation 或 embedding 会扩大依赖和调试面。

**Decision**: M3E 先做 deterministic lexical follow-up：小范围 glossary/alias expansion 加 query-aware evidence selection。

**Consequences**: 这能解决当前报告里的具体问题，并保留可解释性；如果后续 diagnostic report 出现大量真正语义缺口，再单独设计 semantic/hybrid 或 translation spike。

## Out of Scope

* No translation adapter.
* No LLM planner.
* No embeddings, pgvector, OpenSearch, reranker, or language-specific analyzer.
* No fixed dictionary mapping full user queries to canonical keys.
* No hard CI threshold for all diagnostic rows.
* No private report content committed.

## Technical Notes

Relevant files:

* `.trellis/tasks/06-22-pkcs-m3d-diagnostic-query-set/m3d-diagnostic-report.md`
* `src/pkcs/search/planning.py`
* `src/pkcs/context_pack/service.py`
* `tests/test_search_planning.py`
* `tests/test_context_pack.py`
* `tests/test_m3_eval.py`
* `tests/fixtures/m3_diagnostic_queries.jsonl`

Private report target:

* `data/private/eval-runs/m3e-alias-evidence-20260622.json`
