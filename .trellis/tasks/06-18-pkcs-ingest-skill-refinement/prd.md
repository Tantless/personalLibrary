# brainstorm: refine pkcs-ingest skill from M3 corpus ingestion

## Goal

基于 M3 baseline 100 篇真实资料摄入暴露的问题，精进 `.agents/skills/pkcs-ingest/SKILL.md`，让它在单文件摄入和较大批量语料摄入时都能给 agent 明确、稳健、可恢复的执行边界。

## What I Already Know

* 当前 `pkcs-ingest` skill 的主链路是 `uv run pkcs prepare-ingest` -> 可选 `image-enrichment.json` -> MCP `ingest_source`。
* 这条说明对小规模本地单文件摄入是准确的，但对 100 篇公网资料批量摄入缺少分阶段、批量、timeout、fallback 和 MCP 不可用时的处理规则。
* 本次 M3 任务首次直接下载 `74/100` 成功，墙钟约 117 秒；主要耗时不在下载和 ingest，而在失败源替换、PDF/HTML/DOCX 转换和反复重跑。
* Docling PDF 路径是主要瓶颈：23 个 PDF prepare 约 23.9 分钟，13 个 hard fail 失败前已消耗约 15.2 分钟。
* 最终完成依赖了实际降级策略：HTML -> pandoc Markdown snapshot，部分 PDF -> pdftotext plain Markdown snapshot，长批量调用使用 `.venv\Scripts\pkcs.exe` 更稳定。

## Requirements

* 保留现有 skill 的核心职责：把本地单文件或已准备好的 `document.md` package 摄入 PKCS。
* 在 skill 中明确区分小规模单文件摄入和大规模批量/公网语料摄入。
* 针对本次真实失败点修正描述失准：
  * 不再把 `uv run` 写成所有场景的默认执行方式。
  * 不再暗示 PDF/DOCX/HTML 经 Docling 总是可稳定完成。
  * 不再暗示 MCP `ingest_source` 永远可作为当前 agent 的唯一写入路径。
  * 不再把 `soft_fail` 机械定义为必须暂停；允许在批量 degraded text baseline 中按预设策略继续。
* 添加批量 ingest 的最小流程门槛：下载验证、smoke batch、分批执行、每文件 timeout、append-only 报告、失败队列。
* 添加实际 fallback 策略：公网 HTML 优先转 Markdown snapshot；Docling PDF 超时/失败后允许 `pdftotext` degraded path；DOCX 可用 pandoc degraded path。
* 不新增代码，不改变 PKCS runtime 行为。

## Skill Gap Analysis

本次慢任务不完全是 skill 描述失准，也有执行经验问题。但以下点确实应由 `pkcs-ingest` 入口承担：

* 原描述把 `uv run pkcs prepare-ingest` 写成默认主命令。对单次摄入没问题，但对 Windows 长批处理有误导；应提示长批处理优先使用 `.venv\Scripts\pkcs.exe`。
* 原描述只说 PDF/DOCX/XLSX/HTML 依赖 Docling，没有说明 Docling 是高保真首选但不是稳定保证；这导致 HTML/PDF 失败后没有明确 fallback 决策边界。
* 原描述只面向本地单文件，没有说明 URL manifest/公网 corpus 必须先下载验证，不能直接进入 prepare/ingest。
* 原描述把 `soft_fail` 定义为默认暂停，适合单文件高保真摄入；但对 degraded text baseline 批量任务过于保守，应允许记录 warning 后继续。
* 原描述把 MCP `ingest_source` 写成唯一写入路径。实际当前 agent 会话可能没有暴露 MCP tool，skill 应允许同一 service 的 CLI 等价路径并要求报告差异。

以下点更多是执行策略问题，不应塞成大量反向提示词：

* 没有在任务开始就严格按 10-12 条 smoke batch 验证。
* 没有一开始就为每个文件写 append-only 状态报告。
* 对 403/404/反爬源的替换决策过晚。

## Acceptance Criteria

* [x] `pkcs-ingest` skill 仍然清楚说明单文件 prepare -> ingest 主链路。
* [x] skill 明确批量 ingest 不能直接跑 100 文件大批处理。
* [x] skill 说明何时使用 `.venv\Scripts\pkcs.exe`，何时可以使用 `uv run`。
* [x] skill 说明 MCP 不可用时可以使用同一 project service 的 CLI 等价摄入，并必须报告差异。
* [x] skill 说明 Docling 与 Markdown snapshot / pdftotext / pandoc fallback 的选择边界。
* [x] 文档不堆砌反向提示词，而是用少量决策规则覆盖本次真实问题。

## Definition of Done

* `.agents/skills/pkcs-ingest/SKILL.md` 更新完成。
* PRD 记录本次 skill 精进原因和验收标准。
* Git working tree 检查完成。
* 本文档类变更提交到 git。

## Out of Scope

* 不修改 `prepare-ingest` CLI 实现。
* 不新增批量 ingest 命令。
* 不修改 `.codex/config.toml` 的 MCP 配置。
* 不重新摄入 M3 baseline corpus。

## Technical Notes

* 主要依据：
  * `.agents/skills/pkcs-ingest/SKILL.md`
  * `.trellis/tasks/06-17-06-17-pkcs-m3-baseline-corpus-ingestion/ingestion-result.md`
  * `data/private/m3-baseline/reports/download-report.json`
  * `data/private/m3-baseline/reports/prepare-final-report.jsonl`
* 本次改动属于 agent skill 文档/流程修正，不涉及后端代码实现。
