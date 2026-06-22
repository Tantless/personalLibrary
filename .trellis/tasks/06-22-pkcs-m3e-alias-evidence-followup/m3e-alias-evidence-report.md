# M3E Alias and Evidence Selection Report

## 本步完成

M3E 针对 M3D report-only baseline 的两个失败模式做了小范围确定性修复：

* 扩展 `DEFAULT_TECHNICAL_GLOSSARY`，让中文“日本动画行业 / 行业报告 / 实体组件系统 / 游戏引擎”等触发词能桥接到英文 source/title terms。
* 新增 `query_signal_terms()`，把 query 中的 ASCII entities 和 glossary expansions 作为可复用 query signal。
* 修改 Context Pack evidence selection：先按 query signal terms 对 search top_k candidates 做 lexical support 排序，再执行 chunk deduplication、per-source cap 和 evidence cap。
* 新增 query planning 测试，覆盖 AJA industry report 和 Bevy ECS 中文问法。
* 新增 Context Pack fake-service 测试，证明同源多个候选 chunk 时会优先选支持 query terms 的 evidence。
* 同步 backend code-spec，记录新的 Context Pack selection 契约。

## 本地报告

本地 private report 已生成到：

* `data/private/eval-runs/m3e-alias-evidence-20260622.json`

该目录在 `data/` 下，属于 gitignored private output，本任务不提交报告内容。

Report 输入：

* locked regression rows: 6
* diagnostic rows: 22
* total rows: 28

Summary：

* `simple_top_10_hit_rate`: 0.1071
* `planned_top_10_hit_rate`: 1.0
* `simple_to_planned_top_10_delta`: +0.8929
* `planned_context_support_rate`: 1.0
* `locked_regression_pass_rate`: 1.0
* `planned_empty_result_count`: 0
* `context_support_miss_count`: 0
* `noisy_result_query_count`: 5
* `source_concentration_query_count`: 19

Failure classes：

* `evidence_selection_gap`: 0
* `missing_alias`: 0
* `missing_glossary`: 0
* `semantic_gap`: 0

## 与 M3D 对比

M3D report：

* `planned_top_10_hit_rate`: 0.9643
* `planned_context_support_rate`: 0.9286
* `missing_alias`: 1
* `evidence_selection_gap`: 1

M3E report：

* `planned_top_10_hit_rate`: 1.0
* `planned_context_support_rate`: 1.0
* `missing_alias`: 0
* `evidence_selection_gap`: 0

## 结论

M3E 证明当前失败更像 deterministic alias/glossary 和 evidence selection 问题，而不是必须引入 translation、LLM planner 或 semantic backend 的问题。

下一步建议先不要继续加 retrieval dependency。更合理的 M3F 是扩大诊断集或把部分 diagnostic rows 升级成接受阈值前的 monitored gate：例如保留 locked regression 硬门槛，同时为 diagnostic suite 记录趋势指标。
