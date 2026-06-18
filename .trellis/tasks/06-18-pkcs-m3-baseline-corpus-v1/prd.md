# PKCS M3 baseline corpus v1 manifest and reingestion

## Goal

把 M3 baseline 从 v0 的“100 篇摄入压力测试语料”升级为 v1 的“可评测、可复现、可信赖 baseline corpus”。本任务先构造 v1 corpus manifest 和质量门槛，再在 manifest 通过验证后清库重新摄入。

## Requirements

* 基于 v0 的 100 篇来源、prepare/ingest 报告和抽样检查，生成 v1 质量审计报告。
* 构造 v1 manifest，逐条标注：
  * `quality_tier`: `high_fidelity` / `text_only` / `artifact_ready`
  * `decision`: `keep` / `repair` / `replace`
  * `expected_title`
  * `conversion_strategy`
  * `fallback_policy`
  * `validation_queries`
  * `minimum_quality_gate`
* 明确高质量 baseline 的门槛：
  * 不允许页面壳、spinner、JS/cookie challenge、403/404/空首页进入正式 corpus。
  * 不允许 DB title 被 `Source Snapshot`、`License`、`Home Page` 等 wrapper/正文误标题污染。
  * `text_only` PDF 可以用于正文检索评测，但不能计入 artifact-ready 样本。
  * `artifact_ready` 样本必须实际保留本地图片或表格证据。
* 明确清库重摄入前置条件：
  * v1 manifest 已生成。
  * replacement/repair 列表已明确。
  * smoke batch 已覆盖 MD/HTML/PDF/DOCX 和三大领域。
  * quality gate 脚本/报告能指出 pass/fail 原因。
* 按 `pkcs-ingest` skill 新规则执行批量摄入：
  * 先 source validation。
  * 再 10-12 条 smoke batch。
  * 再分批 prepare/ingest。
  * 每条 append-only 记录状态、耗时、warning、fallback、document_path。

## Acceptance Criteria

* [ ] v1 manifest 包含 100 条候选记录，且每条有质量等级、处理策略和检索验证查询。
* [ ] v0 质量审计报告列出不合格、需修复、可保留、仅文本可用的条目。
* [ ] 明显坏源被替换或标为 `replace`，不进入正式重摄入。
* [ ] 清库重摄入前有 smoke batch 结果。
* [ ] 重摄入后：
  * `100/100` ingest completed。
  * `0` 个 blocked/challenge/spinner/空首页文档。
  * `0` 个 title 污染项。
  * `>=95/100` 通过 title/keyword 检索 smoke。
  * 至少 `10-15` 个 artifact-ready 样本。

## Definition of Done

* v1 manifest、质量审计、重摄入报告写入 Trellis 任务目录。
* 清库和重摄入只在 manifest/smoke gate 通过后执行。
* 最终报告明确哪些资料是 high-fidelity、text-only、artifact-ready。
* 文档变更提交到 git。

## Out of Scope

* 不在本任务中新增 PKCS runtime 功能。
* 不把所有 PDF 都强行做 artifact-ready。
* 不绕过反爬或登录限制；受阻来源应替换。

## Technical Notes

* v0 ingestion result: `.trellis/tasks/06-17-06-17-pkcs-m3-baseline-corpus-ingestion/ingestion-result.md`
* v0 selected sources: `.trellis/tasks/06-17-06-17-pkcs-m3-baseline-corpus-source-selection/selected-sources.jsonl`
* Current ingest rules: `.agents/skills/pkcs-ingest/SKILL.md`
