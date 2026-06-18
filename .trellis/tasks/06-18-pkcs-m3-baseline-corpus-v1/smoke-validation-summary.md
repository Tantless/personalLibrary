# M3 baseline corpus v1 smoke validation summary

## Scope

本次 smoke 只验证 v1 manifest 的候选源是否能稳定下载并通过 `prepare-ingest` 生成可用 `document.md`。本步骤没有清库，也没有全量重摄入。

Smoke batch 覆盖 12 条样本：

* direct Markdown：`M3-AI-002`, `M3-GAME-030`
* PDF text-only fallback：`M3-AI-001`
* DOCX high-fidelity：`M3-AI-041`
* PDF high-fidelity：`M3-ANIME-005`, `M3-GAME-006`
* HTML/reader snapshot：`M3-AI-019`, `M3-ANIME-013`, `M3-GAME-002`, `M3-GAME-003`, `M3-GAME-015`, `M3-GAME-016`

## Result

Source validation:

* selected: 12
* downloaded: 12
* failed: 0
* reader Markdown snapshot: 6
* pdftotext Markdown snapshot: 1
* reject pattern rows: 0

Prepare quality gate:

* pass: 12
* soft pass: 0
* fail: 0
* hard fail: 0
* pending title override: 10

`pending_title_override` 表示准备包正文不一定包含最终入库应展示的 manifest 标题。这不是源内容失败，而是后续全量摄入时必须保留 manifest 标题/元数据的问题。

## Corrections Made During Smoke

* `M3-GAME-006`: public Unreal EULA HTML 对 CLI 抓取返回 challenge/403，已改为可直接下载的 EULA PDF。
* `M3-GAME-003`: `What's New` 概览页内容偏短，已改为具体的 Unreal Engine 5.8 Release Notes。
* `M3-GAME-015` / `M3-GAME-016`: Unity static HTML -> Docling 路径不产出 Markdown，已改为 reader Markdown snapshot。

## Next Gate

可以进入下一阶段：按 v1 manifest 执行清库后的全量重摄入。

执行前仍需保持两条约束：

* batch size <= 20，PDF/DOCX 等重格式每批 <= 5。
* 全量摄入报告必须记录每条 source 的下载状态、prepare 状态、最终 ingest 状态、质量门结果和失败队列。
