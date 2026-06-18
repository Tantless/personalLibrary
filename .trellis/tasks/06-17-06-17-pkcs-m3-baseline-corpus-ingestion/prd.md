# PKCS M3 baseline corpus ingestion

## Goal

把 `.trellis/tasks/06-17-06-17-pkcs-m3-baseline-corpus-source-selection/selected-sources.jsonl` 中的 100 条候选公开资料源，按 `pkcs-ingest` skill 约定下载、规范化并摄入 PKCS，形成 M3 baseline corpus 的第一版本地数据集。

## Requirements

* 先启动 Docker/PostgreSQL。
* 将 `data/private/` 和 `data/raw/` 恢复到初始状态，即清空现有测试资料。
* 为避免数据库中残留旧 source 指向已删除 Raw Archive，同步重置本地 `pkcs` database schema 并重新执行 Alembic migration。
* 读取已确认的 100 条候选源 manifest。
* 下载资料到 `data/private/m3-baseline/source-downloads/`。
* 按 skill 对每个下载成功的本地单文件执行 `uv run pkcs prepare-ingest`。
* 对 `success` 和 `success_with_warnings` 的 package 执行知识库摄入。
* 优先通过 PKCS MCP `ingest_source(path=document.md, knowledge_type=document, canonical_key=...)`；如当前 Codex 环境没有暴露外部 MCP tool，则使用同一项目 service/CLI 的等价摄入，并在报告中说明。
* 生成机器可读阶段报告，保存在 `data/private/m3-baseline/reports/`。
* 不提交下载文件、Raw Archive、ingest-prep package 或 private report。

## Acceptance Criteria

* [x] Docker/PostgreSQL 启动且 `pkcs health` 返回 ok。
* [x] `data/private/` 和 `data/raw/` 旧测试资料被清空并重建目录。
* [x] 数据库 schema 已重置并迁移到 head。
* [x] 100 条 manifest 被读取并尝试下载。
* [x] 每条下载、prepare、ingest 的状态都有 report。
* [x] 成功摄入项可被 `pkcs search` 抽样命中。
* [x] 成功摄入项可用 `pkcs read` 抽样读回 evidence。
* [x] 抽样 `pkcs context-pack` 可生成可追溯 evidence。

## Out of Scope

* 不在本任务中修改 PKCS 代码。
* 不补写 M3 eval queries。
* 不提交 private 下载资料或 raw archive。
* 不为所有图片生成视觉 enrichment；本批次先按 skill 允许的普通图片 metadata 降级摄入。
