# PKCS M3D expanded diagnostic query set

## Goal

M3D 的目标是在 M3C 已建立 schema 和 comparison report 之后，创建第一批 expanded diagnostic query set，用报告证明 planned retrieval 在更宽的查询形态下表现如何。这个任务先扩诊断覆盖和报告基线，不直接改 `SearchService`、`PlannedSearchService`、`QueryPlanner`、Context Pack selection，也不引入 translation、LLM planner、embedding、pgvector、reranker 或 language analyzer。

## What I already know

* M3C 已完成 eval schema v2：`suite`、`language`、`query_style`、`expected_intent`、`expected_pass_names`、`diagnostic_tags`。
* M3C 已完成 `M3ComparisonEvaluator`，可以比较 simple search、planned search、planned Context Pack，并输出 pass diagnostics、failure classes、noise/source concentration。
* 当前 `tests/fixtures/m3_eval_queries.jsonl` 有 6 条 locked regression rows，必须继续保留并持续通过。
* M3C handoff 建议新增 `tests/fixtures/m3_diagnostic_queries.jsonl`，先作为 report-only diagnostic suite。
* 当前立即 follow-up 的 `M3D` 指 expanded diagnostic query set；旧父级规划里的 “M3D Context Pack v1” 延后到诊断覆盖之后。
* committed fixture 必须是 synthetic 或 public-reference metadata；private report 只写入 gitignored `data/private/eval-runs/`。

## Assumptions

* 第一批 diagnostic rows 可以引用当前本地 M3 corpus v1 已摄入的 public/reference canonical keys。
* Japanese coverage 可以先少量加入；如果当前 corpus 支持不足，用 `diagnostic_tags` 标记 `japanese_query` / `cross_language_gap`，不把失败直接当 CI regression。
* Diagnostic rows 在本任务中不设置硬阈值 gate；locked regression rows 仍然是必须通过的稳定回归集。

## Requirements

* 新增 `tests/fixtures/m3_diagnostic_queries.jsonl`，与 `tests/fixtures/m3_eval_queries.jsonl` 分离。
* Diagnostic rows 使用 schema v2，并设置 `suite="diagnostic"`。
* 覆盖 `language`: `zh`、`en`、`ja`、`mixed`。
* 覆盖 `query_style`: `exact_title`、`natural_question`、`paraphrase`、`broad_recall`、`negative_or_ambiguous`。
* 尽量覆盖当前 M3 corpus 的 query types：`official_doc_lookup`、`safety_report_lookup`、`broad_project_lookup`、`recent_technical_lookup`。
* 每行必须包含 `expected_canonical_keys`、`expected_evidence_terms`、`expected_intent`、`expected_pass_names`、`diagnostic_tags`。
* 新增或更新 tests，证明 diagnostic fixture 能被 `load_m3_eval_queries()` 加载，并且与 locked rows 一起能被 `M3ComparisonEvaluator` 的 fake services 处理。
* 生成本地 private comparison report，记录 locked + diagnostic rows 的 summary 和 failure classes。

## Acceptance Criteria

* [ ] `tests/fixtures/m3_eval_queries.jsonl` 保持 locked regression，不混入 diagnostic rows。
* [ ] `tests/fixtures/m3_diagnostic_queries.jsonl` 至少包含 20 条 diagnostic rows。
* [ ] Diagnostic rows 覆盖四种 `language` 和五种 `query_style`。
* [ ] Diagnostic fixture 通过 loader validation。
* [ ] Test 覆盖 locked + diagnostic rows 的 report-only comparison flow。
* [ ] 本地 private report 写入 `data/private/eval-runs/`，不提交 report 内容。
* [ ] Task report 总结 failure class 分布，并给出下一步建议。
* [ ] `uv run pytest` 和 `git diff --check` 通过。

## Definition of Done

* Fixture、tests、task report、Trellis task/spec notes 同步。
* Docker-backed `uv run pytest` 通过。
* `git diff --check` 通过。
* 每个 PR-sized step 提交一次。
* 不提交 private source content 或 private eval report。

## Technical Approach

M3D 先做 report-only diagnostic baseline：

```text
locked regression rows
  + diagnostic rows
  -> load_m3_eval_queries()
  -> M3ComparisonEvaluator
  -> local JSON report
  -> failure class summary
  -> next retrieval decision
```

Diagnostic rows 只描述期望和诊断标签，不直接改变 retrieval 行为。后续如果报告显示明显 `missing_alias`、`missing_glossary`、`evidence_selection_gap` 或 `semantic_gap`，再开独立任务处理。

## Proposed Implementation Plan

### PR1: Diagnostic fixture and validation tests

* Inspect current M3 corpus source titles/canonical keys.
* Add `tests/fixtures/m3_diagnostic_queries.jsonl`.
* Add tests for schema coverage and report-only loading with locked rows.
* Generate local private M3D comparison report.
* Write task report with summary and next recommendation.

Verification:

* `uv run pytest tests\test_m3_eval.py -q`
* `uv run pytest`
* `git diff --check`

### PR2: Follow-up retrieval decision task, only if report requires it

Depending on M3D report:

* Alias/glossary/evidence fix task, or
* translation adapter design task, or
* semantic/hybrid spike design task, or
* expand diagnostics further.

## Decision (ADR-lite)

**Context**: M3C restored confidence in the six locked regression rows but did not prove broader multilingual recall. Adding retrieval complexity before expanding diagnostics would risk optimizing for anecdotes.

**Decision**: M3D introduces an expanded diagnostic query set and report-only comparison baseline first. It does not change retrieval behavior or introduce new retrieval dependencies.

**Consequences**: This may reveal failures without immediately fixing them, but it creates the evidence needed to choose the next retrieval change defensibly.

## Out of Scope

* No retrieval algorithm changes in the first M3D PR.
* No translation adapter.
* No LLM planner.
* No embeddings, pgvector, OpenSearch, reranker, or language-specific analyzer.
* No hard CI threshold for diagnostic rows until accepted later.
* No private report or source content committed.

## Technical Notes

Files and context to inspect:

* `.trellis/tasks/06-22-pkcs-m3c-retrieval-quality-validation/m3d-diagnostic-query-set-handoff.md`
* `.trellis/tasks/06-22-pkcs-m3c-retrieval-quality-validation/multilingual-roadmap-adr.md`
* `tests/fixtures/m3_eval_queries.jsonl`
* `tests/test_m3_eval.py`
* `src/pkcs/eval/models.py`
* `src/pkcs/eval/m3_baseline.py`

Private output target:

* `data/private/eval-runs/m3d-diagnostic-<timestamp>.json`
