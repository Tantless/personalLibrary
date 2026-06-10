<!-- TRELLIS:START -->
# Trellis Instructions

These instructions are for AI assistants working in this project.

Use the `/trellis:start` command when starting a new session to:
- Initialize your developer identity
- Understand current project context
- Read relevant guidelines

Use `@/.trellis/` to learn:
- Development workflow (`workflow.md`)
- Project structure guidelines (`spec/`)
- Developer workspace (`workspace/`)

If you're using Codex, project-scoped helpers may also live in:
- `.agents/skills/` for reusable Trellis skills
- `.codex/agents/` for optional custom subagents

Keep this managed block so 'trellis update' can refresh the instructions.

<!-- TRELLIS:END -->

<!-- PKCS-PLANNING:TEMP-START -->
# 临时 PKCS 上下文

本临时块只保留当前实现边界和硬约束。详细规划、实现进度和验收记录以 Trellis 为准：

* 总体规划 PRD：`.trellis/tasks/06-03-pkcs-project-plan/prd.md`
* M1+M2 MVP PRD：`.trellis/tasks/06-03-pkcs-mvp-m1-m2/prd.md`
* M1+M2 任务报告：`.trellis/tasks/06-03-pkcs-mvp-m1-m2/m1-m2-mvp-task-report.md`
* Codex CLI MCP 验收文档：`.trellis/tasks/06-03-pkcs-mvp-m1-m2/codex-cli-mcp-acceptance.md`
* 源设计文档：`personal_knowledge_context_server_design.md`

## 语言规则

* 项目作者是中文母语者；编写面向用户、面向开发者的文档、说明、日志、任务报告时，自然语言描述优先使用中文。
* 代码标识符、命令、配置键、协议字段、API/tool 名称保留英文原文。

## 当前状态

* M1+M2 MVP 已本地完成：摄入、切块、入库、全文检索、证据读回、Context Pack、CLI/HTTP/MCP 闭环均已实现。
* 数据库建模清理已完成：source format、normalized format、knowledge type 已拆分，持久化枚举字段使用 int code。
* 用户原始导入路径只作为一次性输入；Raw Archive 是证据读回的内部源文件，默认 `canonical_key` 使用知识类型前缀 + 五位数据库计数器。
* 自动化 generic MCP fallback 已通过；真实 Codex CLI MCP 验收已写文档，待人工执行。
* M3-M5 仍是未来规划，不要在当前 MVP 约束外提前实现。

## 工作流规则

After each complete PR-sized step is implemented and verified, inspect the working tree. If the changed content is coherent and committable, commit it immediately with a focused commit message before starting the next PR-sized step.

## 数据库建模规则

* Persisted PostgreSQL table/column comments use concise Chinese `中文名：解释`; FK columns must include `外键，关联 table.column`.
* Do not mix file format and knowledge semantics in one field; separate source format, normalized format, and knowledge type when modeling sources.
* Persisted enum fields use int storage; column comments must list each int mapping, e.g. `1:md，2:pdf`.
* User ingest paths are one-time inputs only; Raw Archive is the internal source file, and default `canonical_key` uses knowledge-type prefix + five-digit DB counter.

## MVP 约束

* 技术栈：Python + uv, FastAPI, official MCP Python SDK `FastMCP`, Typer, Docker Compose PostgreSQL, SQLAlchemy + Alembic, Pydantic Settings, pytest + pytest-asyncio。
* 知识类型仅包含 `document` 与 `ai_conversation`；输入仅支持本地单文件或非递归目录。
* AI 对话格式支持 Markdown/transcript 与 JSONL；文档格式支持本地 `.md` 与 `.txt`。
* Raw Archive 位于项目内 `data/raw/` 且必须 gitignored。
* 搜索使用 PostgreSQL FTS `simple`、数据库生成的 `search_vector`、GIN index、FTS rank + title boost。
* 检索过滤项为 `knowledge_type`、`canonical_key`、`top_k`。
* 所有 search result 与 Context Pack evidence 必须能追溯到 `source_id`、`version_id` 和 locator。
* `read_source` 支持 `chunk_id` 与 `source_id/version_id/locator`，locator 格式为 `line N-M`，可选 `context_lines`。
* Context Pack v0 输出 JSON + Markdown，最多 10 条 evidence、每 source 最多 3 条、`budget_tokens` 是软限制，并包含 `Conflicts / Caveats`。

## MVP 范围外

* 代码仓库 ingest/code chunking、Email ingest、HTML/PDF/docx 解析、URL crawling、raw content upload。
* LangChain/LlamaIndex/Haystack 作为核心依赖，pgvector/OpenSearch/reranker/GraphRAG。
* 远程暴露、认证、审计日志表、备份/恢复/reindex 命令、UI、完整 LLM Wiki、自主 multi-agent workflow。

## 已完成功能点

* 接入层：FastAPI health、Typer CLI、FastMCP tools 已可复用同一 application service。
* 数据层：Alembic schema、Raw Archive、sources/source_versions/chunks/citations/ingest_jobs/source_key_counters 已实现。
* 摄入层：Markdown/text 与 AI conversation 摄入、结构优先切块、重复跳过、新版本写入已实现。
* 检索层：PostgreSQL FTS SearchProvider、过滤、标题加权、稳定 search result shape 已实现。
* 证据层：Raw Archive backed `read_source`、chunk/full citation addressing、`context_lines` 已实现。
* Context Pack：搜索编排、chunk 去重、证据上限、Markdown 渲染、Caveats 已实现。
* 验收层：合成 fixtures、20 条 eval queries、检索阈值测试、CLI smoke、generic MCP fallback smoke 已实现。

<!-- PKCS-PLANNING:TEMP-END -->
