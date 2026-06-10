# PKCS MCP Real-Document Acceptance Refresh

## Goal

清理本地 PKCS 测试数据后，使用真实、近期仍有维护价值的技术文档作为测试语料，严格通过 PKCS MCP tools 完成摄入、检索、证据读回与 Context Pack 验收，确认当前最终实现规则与 M1+M2 MVP 行为一致。

## What I Already Know

* M1+M2 MVP 已实现并通过 generic FastMCP fallback 自动化验收。
* 真实 Codex CLI MCP 人工验收已可行，但首次裸搜命中过 pytest 残留记录，暴露出旧数据库记录与 Raw Archive 文件不同步的问题。
* 当前项目仅支持本地单文件或非递归目录摄入，文档格式支持 `.md` 与 `.txt`。
* 本轮验收必须避免直接调用 application service 或 CLI 完成业务动作；`ingest_source`、`search_knowledge`、`read_source`、`get_context_pack` 均通过 MCP tool 入口调用。
* `.codex/config.toml` 是本地 Codex MCP 配置，当前工作树已有该用户改动，本轮不提交该文件。

## Requirements

* 清除原本数据库中的测试数据，并清理 `data/raw/` 中旧 Raw Archive，避免旧 pytest 临时路径污染验收。
* 数据库 schema 保持在 Alembic `head`。
* 从公开官方来源下载真实技术文档作为一次性本地输入资料。
* 测试资料优先选择近半年仍在维护或近一年讨论度高的 AI/LLM 开发主题。
* 使用 MCP tool `ingest_source` 摄入测试资料。
* 使用 MCP tool `search_knowledge` 检索每份资料的主题关键词，并用 `canonical_key` 限定目标资料。
* 使用 MCP tool `read_source` 读取搜索结果的原文证据。
* 使用 MCP tool `get_context_pack` 生成 Context Pack，并确认 evidence 可追溯到 `source_id`、`version_id`、`chunk_id` 与 locator。

## Acceptance Criteria

* [x] PostgreSQL 测试数据被清空，`data/raw/` 旧内容被清理。
* [x] `uv run alembic upgrade head` 成功。
* [x] 至少 3 份真实官方技术文档下载成功并作为本地 `.md` 输入。
* [x] `health_check` 通过 MCP 返回 `status=ok`。
* [x] 每份资料通过 `ingest_source` 返回 `completed` 或可解释的非失败状态。
* [x] 每份资料通过 `search_knowledge` 返回至少 1 条命中，并且命中限定到预期 `canonical_key`。
* [x] 每份资料第一条命中可通过 `read_source` 读回非空原文。
* [x] 至少 1 个跨资料查询通过 `get_context_pack` 返回非空 evidence 与 `Conflicts / Caveats`。
* [x] 验收结果记录到本任务目录。

## Definition of Done

* 清库、下载、MCP 验收过程有可追溯记录。
* 不提交真实测试资料或 Raw Archive 内容。
* 不提交用户本地 `.codex/config.toml` 改动。
* 本轮任务文档提交到 git。

## Out of Scope

* 不修改 PKCS 业务代码。
* 不扩展摄入格式，不实现 PDF/HTML 解析。
* 不把下载的公开文档作为长期项目 fixture。
* 不实现自动删除失效 Raw Archive 记录的修复逻辑。

## Technical Notes

* MCP server 入口：`src/pkcs/mcp/server.py:mcp`。
* 当前 FastMCP tools：`health_check`、`ingest_source`、`search_knowledge`、`read_source`、`get_context_pack`。
* 官方资料候选：
  * OpenAI API docs Markdown endpoint under `https://developers.openai.com/api/docs/...`
  * Anthropic docs Markdown endpoint under `https://platform.claude.com/docs/en/...`
* 本轮下载资料只作为摄入输入；摄入后 Raw Archive 位于 `data/raw/`。
* 验收报告：`real-doc-mcp-acceptance-report.md`。
