# PKCS MVP: M1+M2 Agent Access and Basic Retrieval

## Goal

交付 PKCS 第一个可运行 MVP：外部 Agent 能通过 MCP tools 调用个人知识上下文服务；系统能摄入 AI 对话和 Markdown/Web 文档，保存原始资料与元数据，执行 PostgreSQL full-text search，读回原文证据，并返回 JSON + Markdown hybrid 的 Context Pack v0。

## PRD Status

Confirmed by user on 2026-06-04. Implementation has progressed through PR1-PR7 locally; final acceptance is defined in the procedure below.

## MVP Success Statement

MVP 完成时，Codex 优先或任意 MCP client fallback 能调用 PKCS，导入 `tests/fixtures/` 中的非私密样例资料，搜索目标资料，读回引用原文，并拿到带 evidence、source refs、Caveats 的 Context Pack v0。

## Requirements

* 提供 MCP-first 接入，包含 MVP tools：`health_check`、`ingest_source`、`search_knowledge`、`read_source`、`get_context_pack`。
* MCP 层使用官方 MCP Python SDK 的 `FastMCP`。
* 提供 internal/local HTTP service，用于 health check、开发测试、本地脚本和未来非 MCP 自动化入口。
* internal/local HTTP service 使用 FastAPI。
* 提供最小 CLI：`ingest`、`search`、`read`、`context-pack`，用于本地调试和验收。
* CLI 使用 Typer。
* CLI、FastAPI、FastMCP 必须复用同一套 application service，不重复业务逻辑。
* 配置管理使用 Pydantic Settings，并提供 `.env.example`。
* 日志使用 Python logging + 结构化 JSON 日志；避免输出完整私密内容或 secrets。
* MVP 不单独建 `audit_logs` 表；写入通过 `ingest_jobs` 记录，运行事件通过 structured logs 追踪。
* MVP 本地默认允许写入工具；服务默认绑定 localhost；不支持/不配置远程暴露、认证或细粒度权限。
* migration 必须创建必要 schema indexes 和 PostgreSQL FTS GIN index；ingest 后数据立即可搜索。
* PostgreSQL FTS `search_vector` 使用数据库层自动生成，应用层不直接写入。
* PostgreSQL FTS 使用 `simple` 配置，不引入中文分词插件或多语言词典配置。
* MVP 不提供独立 `reindex` / `rebuild-index` 命令。
* MVP 主要实现语言为 Python；第一版不引入跨语言服务边界。
* Python 包管理与项目脚手架使用 uv。
* 数据库访问和 migration 使用 SQLAlchemy + Alembic。
* 测试使用 pytest + pytest-asyncio；集成测试连接 Docker Compose PostgreSQL。
* MVP 暂不引入 LangChain、LlamaIndex、Haystack 等 RAG/Agent 框架；未来在解析、切块、检索增强或评测阶段再考虑辅助 adapter。
* 默认本地运行，HTTP 绑定 localhost；写入工具与只读工具在权限模型上分离。
* 默认使用 Docker Compose 管理 PostgreSQL，提供持久化 volume、环境变量样例和启动说明。
* 建立 Raw Archive，默认路径为项目内 `data/raw/`，按 source_type 分层；原始资料追加保存，不因新版本覆盖旧版本。
* `data/raw/` 和真实数据目录必须加入 `.gitignore`，避免个人资料进入版本库。
* MVP 不实现专门 backup/export/restore 命令；只要求 Docker volume 和 `data/raw/` 路径清楚，可手动备份。
* MVP ingest 输入只支持本地文件路径；支持单文件导入和非递归目录导入；暂不支持 raw content 直传或 URL 抓取。
* 目录批量 ingest 遇到单个文件失败时继续处理其他文件，并在 ingest report 中记录 `succeeded`、`skipped`、`failed`。
* `ingest_source` 返回完整 ingest report，包含 `ingest_job_id`、`status`、`source_id`、`version_id`、`canonical_key`、`content_hash`、`created_new_source`、`created_new_version`、`chunks_created`、`succeeded`、`skipped`、`failed`。
* MVP evaluation corpus 存放在 `tests/fixtures/`，只使用合成或非私密样例。
* MVP 检索评测问题使用 `tests/fixtures/eval_queries.jsonl`，每行一个 query expectation。
* 建立 PostgreSQL 主数据结构，至少包含 `sources`、`source_versions`、`chunks`、`citations`、`ingest_jobs`。
* MVP source_type 枚举包含 `ai_conversation` 与 `markdown_doc`。
* 支持 AI 对话 ingest，输入格式包含 Markdown/transcript 文本与 JSONL 文件，并归一化到统一 conversation/turn 结构。
* AI 对话 ingest 至少保存 conversation title、participants/roles、turns text、summary/open questions/decisions 的预留字段。
* 支持 Markdown/Web 文档 ingest，输入格式只包含本地 `.md` / `.txt` 文件；至少保存 title、origin_uri、heading_path、section locator、content。
* chunk 策略采用结构优先 + 上限切分：Markdown/文本按 heading 或 section，AI 对话按 turn 或相邻 turns window，超长再切分并保留少量 overlap。
* locator 采用两层设计：主 locator 为统一行号范围；metadata 保留 heading_path、turn/window、roles 等 source_type-specific 语义信息。
* canonical source identity 使用 `canonical_key`；未传时自动推断为 `source_type + ":" + normalized_absolute_file_path`。
* 支持重复导入检测：相同内容 hash 不产生脏重复；同一 canonical source 的新 hash 产生新 version。
* 支持 PostgreSQL full-text search，支持 query、source_type filter、canonical_key filter、top_k；排序采用 FTS rank + title boost。
* `search_knowledge` 输出稳定证据结构，包含 `result_id/chunk_id`、`source_id`、`version_id`、`canonical_key`、`title`、`source_type`、`snippet`、`score`、`citation`、`metadata`。
* 支持 `read_source` 根据 `chunk_id` 快捷读取，或根据 `source_id`、`version_id`、`locator` 完整 citation 读取原文片段，并支持可选 `context_lines` 返回前后文。
* 支持 `get_context_pack` v0：内部调用基础搜索，执行去重与每 source evidence 数量限制，默认最多 10 条 evidence 且每个 source 最多 3 条，暴露 `budget_tokens` 软限制参数，返回结构化 JSON 与 `context_pack_markdown`。
* Context Pack Markdown 保留 `Conflicts / Caveats` 段落；MVP 只写检索限制和未做冲突检测说明。
* 所有搜索结果和 Context Pack evidence 必须带 `source_id`、`version_id`、`locator`，不得输出无法追溯的关键证据。
* 保留 `SearchProvider` 抽象，避免业务逻辑直接绑定 PostgreSQL FTS 实现。

## Acceptance Criteria

* [ ] 可以启动 PKCS 本地服务，并通过 HTTP `health_check` 和 MCP `health_check` 验证服务可用。
* [ ] 可以通过 CLI 执行 ingest/search/read/context-pack 基础流程。
* [ ] 可以通过 Docker Compose 启动 PostgreSQL，服务重启后数据库数据不丢。
* [ ] migration 创建 canonical_key/content_hash/source-version 相关 schema indexes 与 FTS GIN index。
* [ ] `search_vector` 由数据库层自动生成，ingest 代码不直接写入该字段。
* [ ] FTS 查询与 search_vector 使用 `simple` 配置。
* [ ] 可以运行 pytest 单元测试和连接 Docker Compose PostgreSQL 的集成测试。
* [ ] 可以导入至少 10 条 AI 对话样例和 10 篇 Markdown/Web 文档样例。
* [ ] `source_type` filter 支持 `ai_conversation` 与 `markdown_doc`。
* [ ] `search_knowledge` 支持 `canonical_key` filter，用于限定某一长期 source 内搜索。
* [ ] AI 对话样例覆盖 Markdown/transcript 与 JSONL 两种格式。
* [ ] Markdown/Web 文档样例只要求覆盖 `.md` / `.txt` 文件。
* [ ] `ingest_source` 接收本地文件路径并拒绝/不暴露 raw content 与 URL 抓取输入。
* [ ] `ingest_source` 可以导入单个文件，也可以导入目录下当前层级的匹配文件；不递归进入子目录。
* [ ] 目录导入中单个文件失败不会阻止其他文件处理，report 包含 succeeded/skipped/failed。
* [ ] 单文件和目录导入都返回同一 ingest report shape。
* [ ] 导入后 Raw Archive 中存在原始资料文件，数据库中存在 source、version、chunk、citation 记录。
* [ ] chunk metadata 保留 Markdown heading_path 或 AI conversation turn/window 信息。
* [ ] citation 同时包含 `line_start` / `line_end` 和 source_type-specific metadata。
* [ ] `ingest_source` 支持显式 `canonical_key`，未传时按 source_type + normalized absolute path 推断。
* [ ] `data/raw/` 中真实资料不会被 git 跟踪。
* [ ] 重复导入相同内容不会产生脏重复。
* [ ] 同一资料的新版本不会覆盖旧版本。
* [ ] `search_knowledge` 能在 3 秒内返回 top_k 搜索结果，并包含 source refs 与 snippets。
* [ ] `search_knowledge` 结果结构包含 result/chunk/source/version refs、canonical_key、title、source_type、score、citation 和 metadata。
* [ ] 标题命中的搜索结果相对纯正文命中有 boost，默认不使用 recency boost。
* [ ] `read_source` 能在 1 秒内按 citation 读回正确原文片段。
* [ ] `read_source` 支持 `context_lines`，并默认不返回整份 source。
* [ ] `read_source` 支持 `chunk_id` addressing 和 `source_id/version_id/locator` addressing。
* [ ] `get_context_pack` 返回外层 JSON，且包含 `query`、`retrieval_plan`、`sources`、`followup_read_suggestions`、`context_pack_markdown`。
* [ ] `context_pack_markdown` 包含 `Conflicts / Caveats` 段落，并明确 MVP 未做真正冲突检测。
* [ ] Context Pack 不会被单一 source 的相邻 chunks 占满。
* [ ] Context Pack 默认最多包含 10 条 evidence，且每个 source 最多 3 条。
* [ ] `budget_tokens` 可以影响 `context_pack_markdown` 长度，但文档明确它是软限制而非精确 token guarantee。
* [ ] Context Pack 中每个 evidence 都能映射到可读回的 source/version/locator。
* [ ] 构造至少 20 个 MVP 检索问题，目标资料进入 top 10 的比例不低于 80%，进入 top 5 的比例不低于 60%。
* [ ] 检索问题存放在 `tests/fixtures/eval_queries.jsonl`，每行包含 query expectation。
* [ ] `tests/fixtures/` 中不包含真实个人私密资料。
* [ ] Codex 优先调用 MCP tools 完成一次“检索过去资料并生成上下文”的任务；若 Codex MCP 配置受限，则用任意 MCP client smoke test fallback。

## Definition of Done

* MVP 功能通过单元测试、集成测试和最小 Agent 接入验收。
* uv、Docker Compose、数据库 migration、Raw Archive 路径、`.gitignore`、配置样例和启动说明齐全。
* `.env.example` 包含 MVP 必要配置项且不包含真实 secret。
* 所有写入行为有 ingest job 状态记录和基础日志。
* 关键路径日志覆盖 ingest、search、read_source、context_pack 和错误摘要。
* 失败路径至少覆盖：重复导入、source not found、locator invalid、search no results、数据库不可用。
* 不引入 pgvector、OpenSearch、代码仓库 ingest、邮件 ingest、完整 LLM Wiki 或复杂 UI。
* 不实现专门 backup/export/restore 命令。

## Start Conditions

Before implementation begins:

* Run Trellis Phase 2 for this task: research the empty/new codebase shape, initialize task context, then start the task.
* Read backend guideline files required by `.trellis/spec/backend/index.md` before writing code.
* Confirm local prerequisites: Python + uv, Docker, Docker Compose, and available local PostgreSQL port from compose config.
* Do not ingest real private data during MVP implementation; use `tests/fixtures/` synthetic/non-private data only.

## Technical Approach

实现按层拆分：

* Interface layer: official MCP Python SDK `FastMCP` tools + FastAPI local HTTP endpoints + Typer minimal CLI.
* Application layer: ingest service, search service, source reader, context pack builder.
* Data layer: SQLAlchemy/Alembic PostgreSQL repositories, Raw Archive writer, SearchProvider abstraction.
* Parsers: AI conversation parser and Markdown/Web parser with structure-first chunking.
* Evaluation: fixed synthetic/non-private sample corpus in `tests/fixtures/` plus `tests/fixtures/eval_queries.jsonl`.
* Testing: pytest + pytest-asyncio, with integration tests against Docker Compose PostgreSQL.
* Runtime language: Python.
* Package management: uv.
* Configuration: Pydantic Settings with `.env.example`.
* Logging: Python logging with structured JSON logs.
* Framework dependency: no LangChain/LlamaIndex/Haystack in MVP core path.

## Decision (ADR-lite)

**Context**: 第一个 MVP 必须证明 PKCS 的核心价值，而不是只证明服务能启动。因此 M1 接入骨架与 M2 摄入/基础检索合并实施。

**Decision**: 第一个实施 PRD 覆盖 MCP-first access、local HTTP、Raw Archive、PostgreSQL metadata、AI conversation ingest、Markdown/Web ingest、PostgreSQL FTS、search/read_source、Context Pack v0。

**Consequences**: 范围比单独 M1 更大，但能形成真正闭环。通过小 PR 拆分控制风险。

## Implementation Plan (Small PRs)

* PR1: Project scaffold, config, Docker Compose PostgreSQL, local HTTP health check, MCP server skeleton, CLI skeleton, tests for startup and health.
* PR2: PostgreSQL schema/migrations, `data/raw/` Raw Archive writer, `.gitignore`, source/version/chunk/citation repositories.
* PR3: AI conversation Markdown/transcript + JSONL parser, Markdown/Web ingest pipeline, hash/version behavior, ingest job logging.
* PR4: PostgreSQL FTS SearchProvider, `search_knowledge`, source_type filter, title boost, top_k behavior.
* PR5: `read_source` citation lookup and locator-based source fragment reading.
* PR6: `get_context_pack` v0 with dedup/source limits and JSON + Markdown hybrid output.
* PR7: MVP evaluation corpus, query tests, Codex-first MCP integration smoke test with generic MCP client fallback, docs.

## Verification Plan

Each implementation PR must have a direct verification gate:

* PR1 verifies service startup, HTTP health, MCP health, CLI command discovery, config loading, and Docker Compose PostgreSQL startup.
* PR2 verifies migrations, required schema indexes, FTS GIN index, Raw Archive path behavior, `.gitignore`, and repository CRUD for source/version/chunk/citation.
* PR3 verifies local file ingest, non-recursive directory ingest, Markdown/transcript + JSONL AI conversation parsing, `.md`/`.txt` document parsing, hash duplicate handling, new version creation, and ingest report shape.
* PR4 verifies PostgreSQL FTS `simple` search, database-generated `search_vector`, title boost, source_type/canonical_key filters, top_k, stable search result shape, and latency target.
* PR5 verifies `read_source` by `chunk_id`, by full source/version/locator, `context_lines`, invalid locator behavior, and 1 second latency target.
* PR6 verifies Context Pack JSON schema, Markdown body, evidence caps, per-source limit, soft `budget_tokens`, Caveats section, and source refs mapping back to `read_source`.
* PR7 verifies fixture corpus, `eval_queries.jsonl`, retrieval thresholds, docs, and Codex-first MCP smoke test with generic MCP fallback.

## Implementation Progress

### PR1: Scaffold and Health Skeleton

Status: completed locally on 2026-06-04.

Delivered:

* `pyproject.toml` with uv project metadata, runtime dependencies, dev dependencies, and `pkcs` CLI entry point.
* `.env.example` with local configuration defaults.
* `docker-compose.yml` with PostgreSQL 17 Alpine, persistent volume, port `54329`, and healthcheck.
* `.gitignore` excluding virtualenv/cache files and real data paths such as `data/raw/`.
* FastAPI app with `GET /health`.
* Official MCP Python SDK `FastMCP` server skeleton with `health_check`.
* Typer CLI with `health` and placeholder MVP commands.
* Basic health/startup tests.

Verified:

* `uv sync` succeeded.
* `docker compose up -d postgres` succeeded.
* `docker compose ps postgres` reported `healthy`.
* `uv run pytest` passed: 3 tests.
* `uv run pkcs health` returned status `ok`.
* `uv run pkcs --help` listed expected MVP commands.
* `GET http://127.0.0.1:8765/health` returned status `ok`.

Notes:

* FastAPI TestClient emits a Starlette deprecation warning about `httpx`; it does not fail tests.
* `ingest`, `search`, `read`, and `context-pack` CLI commands are placeholders by design until later PRs.

### PR2: Schema, Raw Archive, and Repositories

Status: completed locally on 2026-06-04.

Delivered:

* Alembic configuration and initial migration.
* PostgreSQL tables: `sources`, `source_versions`, `chunks`, `citations`, `ingest_jobs`.
* Required schema indexes and PostgreSQL FTS GIN index.
* Database-generated `chunks.search_vector` using PostgreSQL `simple` FTS configuration.
* SQLAlchemy models and sync session helper.
* Repository layer for source/version/chunk/citation/ingest job CRUD.
* `RawArchiveWriter` writing under source_type/source_id/version_id.
* Docker-backed integration tests for schema, generated FTS vector, repository round-trip, and Raw Archive path behavior.

Verified:

* `uv run alembic upgrade head` succeeded.
* `uv run pytest` passed: 7 tests.

Notes:

* PR2 does not implement ingest parsing or search service behavior; it only creates the data layer needed by PR3 and PR4.
* FastAPI TestClient still emits a Starlette deprecation warning about `httpx`; it does not fail tests.

### PR3: Ingest Pipeline

Status: completed locally on 2026-06-04.

Delivered:

* `IngestService` application workflow shared by CLI and MCP.
* `ingest_source` FastMCP tool.
* Functional `pkcs ingest` CLI command returning the stable ingest report shape.
* Markdown/text parser for `markdown_doc` with heading_path metadata and line locators.
* AI conversation parser for Markdown/transcript and JSONL inputs, normalized into turn/window chunks with role metadata.
* Structure-first chunking with max character cap and small line overlap.
* SHA-256 content hash handling.
* Canonical source identity behavior using explicit `canonical_key` or `source_type:absolute_path` fallback.
* Duplicate content skip for the same canonical source and hash.
* New source version creation for changed content under the same canonical source.
* Raw Archive writes under `source_type/source_id/version_id`.
* Chunk and citation creation for ingested evidence.
* Ingest job summary updates for completed, skipped, failed, and completed_with_errors outcomes.
* Non-recursive directory ingest with per-file failure continuation.
* Synthetic/non-private fixtures for Markdown and AI conversation formats.
* Backend code-spec updates for directory structure, database, error handling, logging, and quality rules.

Verified:

* `uv run pytest tests/test_ingest.py` passed: 6 tests.
* `uv run pytest` passed: 13 tests.

Notes:

* PR3 does not implement search ranking, `read_source`, or Context Pack behavior; those remain PR4-PR6.
* FastAPI TestClient still emits a Starlette deprecation warning about `httpx`; it does not fail tests.

### PR4: PostgreSQL FTS Search

Status: completed locally on 2026-06-04.

Delivered:

* `SearchProvider` abstraction.
* PostgreSQL FTS provider using `websearch_to_tsquery('simple', query)` against the database-generated `chunks.search_vector`.
* `SearchService.search_knowledge()` application workflow.
* Ranking by PostgreSQL FTS rank plus explicit title match boost.
* `source_type`, `canonical_key`, and `top_k` filters.
* Stable search response shape with result/chunk/source/version refs, canonical key, title, source type, snippet, score, citation, and metadata.
* Functional `pkcs search` CLI command.
* FastMCP `search_knowledge` tool.
* Docker-backed search tests for result shape, filters, top_k, title boost, no-results behavior, CLI, and MCP.
* Backend code-spec updates for search module layout, FTS query contracts, search error behavior, logging, and quality requirements.

Verified:

* `uv run pytest tests/test_search.py` passed: 5 tests.
* `uv run pytest` passed: 18 tests.

Notes:

* PR4 does not implement `read_source` or Context Pack behavior; those remain PR5 and PR6.
* FastAPI TestClient still emits a Starlette deprecation warning about `httpx`; it does not fail tests.

### PR5: Read Source

Status: completed locally on 2026-06-04.

Delivered:

* `ReadSourceService.read_source()` application workflow.
* `line N-M` locator parser and formatter.
* Raw Archive backed source fragment reading from `source_versions.raw_archive_path`.
* `chunk_id` shortcut addressing.
* Full `source_id` + `version_id` + `locator` addressing.
* Optional `context_lines` support without returning whole sources by default.
* Functional `pkcs read` CLI command.
* FastMCP `read_source` tool.
* Stable read response shape with source refs, locator, citation lines, returned context line range, content, and metadata.
* Reader error handling for missing chunk, invalid locator, missing source/version, missing Raw Archive file, negative context lines, and incomplete addressing.
* Docker-backed reader tests for chunk lookup, full citation lookup, context lines, invalid refs, CLI, and MCP.
* Backend code-spec updates for reader module layout, Raw Archive read contracts, read errors, logging, and quality requirements.

Verified:

* `uv run pytest tests/test_reader.py` passed: 5 tests.
* `uv run pytest` passed: 23 tests.

Notes:

* PR5 does not implement Context Pack behavior; that remains PR6.
* FastAPI TestClient still emits a Starlette deprecation warning about `httpx`; it does not fail tests.

### PR6: Context Pack v0

Status: completed locally on 2026-06-04.

Delivered:

* `ContextPackService.get_context_pack()` application workflow.
* Context Pack v0 outer JSON with `query`, `retrieval_plan`, `sources`, `evidence`, `followup_read_suggestions`, and `context_pack_markdown`.
* Evidence selection using search top_k, chunk deduplication, global evidence cap, and per-source evidence cap.
* Evidence content read through `ReadSourceService` so every evidence item maps back to `read_source`.
* Structured evidence refs with chunk/source/version/canonical key/locator/line range.
* Follow-up read suggestions with `chunk_id` and `context_lines`.
* Markdown rendering with retrieval plan, sources, evidence, follow-up reads, and `Conflicts / Caveats`.
* Caveats explicitly state that MVP does not perform real conflict detection.
* `budget_tokens` soft Markdown length hint; no exact tokenizer guarantee.
* Functional `pkcs context-pack` CLI command.
* FastMCP `get_context_pack` tool.
* Docker-backed Context Pack tests for JSON shape, evidence caps, per-source limit, budget behavior, caveats, read_source mapping, CLI, and MCP.
* Backend code-spec updates for Context Pack module layout, evidence traceability, errors, logging, and quality requirements.

Verified:

* `uv run pytest tests/test_context_pack.py` passed: 5 tests.
* `uv run pytest` passed: 28 tests.

Notes:

* PR6 does not implement PR7 eval corpus, retrieval thresholds, or external MCP client acceptance.
* FastAPI TestClient still emits a Starlette deprecation warning about `httpx`; it does not fail tests.

### PR7: Evaluation Corpus and Final Acceptance Smoke

Status: completed locally on 2026-06-04.

Delivered:

* Synthetic/non-private fixture corpus under `tests/fixtures/`.
* At least 10 Markdown/text document samples in `tests/fixtures/markdown/`.
* At least 10 AI conversation samples in `tests/fixtures/conversations/`, covering Markdown/transcript and JSONL.
* `tests/fixtures/eval_queries.jsonl` with 20 query expectation lines.
* Eval query fields: `query`, `expected_fixture`, `expected_canonical_keys`, `expected_source_types`, and `notes`.
* Docker-backed retrieval threshold test requiring top 10 >= 80% and top 5 >= 60%.
* Final CLI smoke test covering ingest, search, read, and context-pack.
* Codex-first MCP acceptance fallback test using `FastMCP.call_tool` to cover `health_check`, `ingest_source`, `search_knowledge`, `read_source`, and `get_context_pack`.
* README documentation for evaluation and final acceptance commands.
* Backend quality spec update for PR7 evaluation contracts.

Verified:

* `uv run pytest tests/test_acceptance.py` passed: 4 tests.
* `docker compose ps postgres` reported PostgreSQL healthy.
* `uv run alembic upgrade head` succeeded.
* `uv run pytest` passed: 32 tests.
* `git diff --check` reported no whitespace errors; only Windows LF/CRLF conversion warnings.

Notes:

* The MCP smoke test is the generic client fallback path. A real Codex MCP client smoke can be run later if local Codex MCP configuration is available.
* Eval tests use runtime-unique canonical key templates so persistent Docker test data does not affect acceptance results.

## Final Acceptance Procedure

MVP is accepted only when all of the following pass:

* `uv sync` completes and documented service commands run.
* Docker Compose PostgreSQL starts with persistent volume.
* Alembic migrations create tables, schema indexes, and FTS GIN index.
* pytest unit tests and Docker-backed integration tests pass.
* Synthetic fixture ingest imports at least 10 AI conversation samples and 10 Markdown/text samples.
* Evaluation over at least 20 queries reaches top 10 >= 80% and top 5 >= 60%.
* CLI ingest/search/read/context-pack flow works end to end.
* HTTP health and MCP health pass.
* Codex can call MCP tools for one real smoke task, or a generic MCP client fallback proves the same tool flow.
* Documentation explains setup, config, ingest, search, read_source, context_pack, testing, and MVP limitations.

Concrete commands:

```powershell
docker compose ps postgres
uv run alembic upgrade head
uv run pytest
git diff --check
```

## Out of Scope

* GitHub repo ingest, code chunking, symbol search, code semantic search.
* Email ingest and thread search.
* pgvector, OpenSearch, reranker, GraphRAG.
* LangChain, LlamaIndex, Haystack, or other RAG/Agent frameworks as MVP core dependencies.
* raw content ingest and URL crawling/fetching.
* HTML, PDF, docx, or other rich document parsing.
* Full LLM Wiki, memory proposal workflow, belief history.
* Remote multi-user deployment and complex permission system.
* API key/token auth, remote write controls, or public network exposure.
* Dedicated backup/export/restore commands.
* Dedicated `audit_logs` table.
* Full management CLI beyond ingest/search/read/context-pack.
* `reindex` / `rebuild-index` commands.
* Chat UI or autonomous multi-Agent workflow.

## Technical Notes

* Parent planning task: `.trellis/tasks/06-03-pkcs-project-plan`
* Confirmed interface: MCP-first + internal/local HTTP.
* Confirmed MCP SDK: official MCP Python SDK with `FastMCP`.
* Confirmed HTTP framework: FastAPI.
* Confirmed database tools: SQLAlchemy + Alembic.
* Confirmed package management: uv.
* Confirmed testing strategy: pytest + pytest-asyncio against Docker Compose PostgreSQL for integration tests.
* Confirmed Raw Archive location: project-local `data/raw/`, gitignored.
* Confirmed backup scope: no dedicated backup/export/restore commands in MVP; manual backup only.
* Confirmed ingest input: local file paths only.
* Confirmed ingest path mode: single file plus non-recursive directory import.
* Confirmed batch ingest error handling: continue on per-file failure and report succeeded/skipped/failed.
* Confirmed ingest report shape: full report with job/source/version/hash/chunk/succeeded/skipped/failed fields.
* Confirmed evaluation corpus: `tests/fixtures/`, synthetic or non-private only.
* Confirmed eval query format: `tests/fixtures/eval_queries.jsonl`.
* Confirmed AI conversation formats: Markdown/transcript and JSONL.
* Confirmed Markdown/Web document formats: local `.md` / `.txt` only.
* Confirmed chunking strategy: structure-first with length cap and small overlap.
* Confirmed locator format: unified line range plus source_type-specific metadata.
* Confirmed canonical source identity: explicit `canonical_key`, with source_type + normalized absolute path fallback.
* Confirmed source_type names: `ai_conversation`, `markdown_doc`.
* Confirmed implementation language: Python.
* Confirmed framework stance: no RAG/Agent framework dependency in MVP; consider LlamaIndex later as adapter for parsing/chunking/retrieval/eval.
* Confirmed source scope: AI conversations + Markdown/Web documents only.
* Confirmed search backend: PostgreSQL metadata + PostgreSQL full-text search.
* Confirmed search ranking: FTS rank + title boost, no recency boost by default.
* Confirmed search filters: `source_type`, `canonical_key`, and `top_k`; no title/date filters in MVP.
* Confirmed search result shape: stable evidence structure; no LLM-generated why_relevant in MVP.
* Confirmed read_source context: citation lines plus optional context_lines; no full-source default.
* Confirmed read_source addressing: chunk_id shortcut plus full source_id/version_id/locator citation.
* Confirmed PostgreSQL runtime: Docker Compose by default.
* Confirmed Context Pack format: JSON + Markdown hybrid.
* Confirmed Context Pack selection: search top_k plus dedup and per-source evidence limit.
* Confirmed Context Pack evidence limits: default 10 evidence, max 3 per source.
* Confirmed budget_tokens: exposed as soft limit only; no exact tokenizer in MVP.
* Confirmed Context Pack caveats: include caveats section, no real conflict detection in MVP.
* Confirmed Agent integration acceptance: Codex first, generic MCP client fallback.
* Confirmed CLI scope: minimal ingest/search/read/context-pack, reusing application service.
* Confirmed CLI framework: Typer.
* Confirmed configuration management: Pydantic Settings with `.env.example`.
* Confirmed logging strategy: Python logging + structured JSON logs.
* Confirmed audit scope: no dedicated audit_logs table; use ingest_jobs + structured logs.
* Confirmed permission model: local-only by default, writes allowed locally, no auth/remote exposure in MVP.
* Confirmed index scope: schema indexes and PostgreSQL FTS GIN index are required; no reindex/rebuild command in MVP.
* Confirmed FTS search_vector generation: database-generated, not application-written.
* Confirmed FTS dictionary: PostgreSQL `simple`.
* Code repositories are explicitly deferred and must not be modeled as ordinary document chunks by default.
