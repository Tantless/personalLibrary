# M3D Diagnostic Query Set Report

## 本步完成

本步建立了 M3D 的第一批 report-only diagnostic baseline：

* 新增 `tests/fixtures/m3_diagnostic_queries.jsonl`，包含 22 条 diagnostic rows。
* 保留 `tests/fixtures/m3_eval_queries.jsonl` 作为 6 条 locked regression rows，不混入 diagnostic suite。
* Diagnostic rows 覆盖 `zh`、`en`、`ja`、`mixed` 四类语言标记。
* Diagnostic rows 覆盖 `exact_title`、`natural_question`、`paraphrase`、`broad_recall`、`negative_or_ambiguous` 五类查询形态。
* 新增测试，验证 diagnostic fixture 的 schema v2 覆盖，以及 locked + diagnostic rows 可以一起进入 `M3ComparisonEvaluator` 的 report-only flow。

## 本地报告

本地 private report 已生成到：

* `data/private/eval-runs/m3d-diagnostic-pr1-20260622.json`

该目录在 `data/` 下，属于 gitignored private output，本任务不提交报告内容。

Report 输入：

* locked regression rows: 6
* diagnostic rows: 22
* total rows: 28

Summary：

* `simple_top_10_hit_rate`: 0.1071
* `planned_top_10_hit_rate`: 0.9643
* `simple_to_planned_top_10_delta`: +0.8571
* `planned_context_support_rate`: 0.9286
* `locked_regression_pass_rate`: 1.0
* `planned_empty_result_count`: 0
* `context_support_miss_count`: 2
* `noisy_result_query_count`: 4
* `source_concentration_query_count`: 20

Pass diagnostics：

* `original_hit_count`: 3
* `ascii_entity_hit_count`: 20
* `glossary_hit_count`: 5
* `source_alias_hit_count`: 25
* `combined_hit_count`: 25
* `pass_error_counts`: none

Failure classes：

* `evidence_selection_gap`: 1
* `missing_alias`: 1
* `missing_glossary`: 0
* `semantic_gap`: 0

## 失败行

1. `哪份报告总结了日本动画行业 2025 年的数据？`
   * expected: `m3-corpus:anime:aja-anime-industry-report-2025-summary`
   * planned top-10 hit: false
   * context support: false
   * missing terms: `Anime Industry Report`
   * failure class: `missing_alias`

2. `哪个游戏引擎说明文档描述了实体组件系统能力？`
   * expected: `m3-corpus:game:bevy-readme`
   * planned rank: 4
   * context support: false
   * missing terms: `ECS`, `game engine`
   * failure class: `evidence_selection_gap`

## 结论

M3D 第一批诊断结果支持 M3C 的方向：planned retrieval 相比 simple FTS 有明显改善，并且 locked regression 仍然 100% 通过。当前不应直接上 translation、LLM planner 或 embedding；更小的下一步是处理两个具体缺口：

* source alias 覆盖：中文行业报告问法没有桥接到 `AJA Anime Industry Report 2025 Summary`。
* evidence selection：Bevy 源已进入 top-10，但 Context Pack 没选到包含 `ECS` / `game engine` 的证据。

建议下一步开 M3E：小范围 alias/glossary + evidence selection 诊断修复。M3E 只针对 M3D 报告中的失败模式改动，不扩大到完整多语言语义检索。
