# brainstorm: Personal Knowledge Context Server Project Plan

## Goal

把 `personal_knowledge_context_server_design.md` 中的愿景文档收敛成可执行项目规划：从第一步如何开始，到每个阶段如何开发、如何验收、如何确认完成，都形成双方同步的 PRD 与路线图。澄清阶段结束后，应能基于本 PRD 拆分阶段任务并进入 Trellis Phase 2 实施准备。

## What I Already Know

* 用户希望以 brainstorm 方式推进，不直接进入实现。
* 目标项目暂定名为 Personal Knowledge Context Server，简称 PKCS，中文名为个人知识上下文服务。
* 核心定位是“面向外部 Agent 的个人知识库后端服务”，不是聊天 UI，也不是替主 Agent 决策的自治 Agent。
* 核心输出是可追溯、可压缩、可注入主 Agent 上下文的 Context Pack。
* 外部使用者包括 Claude Code、Codex、OpenClaw、IDE Agent、本地 Agent、自动化脚本和未来自定义工作流。
* 总路线被设计为五个阶段：M1 接入骨架与数据底座，M2 摄入与基础检索 MVP，M3 检索编排与 Context Pack，M4 特色知识源增强，M5 知识沉淀、安全、评测与运维。
* 原设计已经给出 MVP 建议范围：MCP / HTTP 接入、Raw Archive、PostgreSQL metadata、基础搜索、read_source、get_context_pack v0、AI 对话 ingest、Markdown / 网页 ingest、GitHub repo ingest v0。
* 当前仓库尚无实现代码，只有 `AGENTS.md`、`.trellis/` 和 `personal_knowledge_context_server_design.md`。

## Assumptions (Temporary)

* 第一轮讨论目标是项目规划与 PRD 澄清，不要求本轮写业务代码。
* 本项目应优先支持本地个人使用，再逐步扩展到服务器部署和多 Agent 接入。
* 第一阶段应保持轻量，先验证 Agent 工具接口、Raw Archive、元数据、基础检索和证据回读闭环。
* `AGENTS.md` 中注入的规划上下文仅用于本次 PRD 澄清期间的防丢失，用户会在澄清结束后手动删除。

## Open Questions

* No open MVP questions. M3-M5 PRDs remain future planning work after MVP confirmation.

## Requirements (Evolving)

* 项目规划必须覆盖从启动、开发、验收到完成确认的完整路线。
* 每个阶段必须有明确目标、产物、验收标准和完成定义。
* 每确认一个阶段 PRD，都要立即写入任务 PRD。
* 必须将澄清期必要上下文临时注入 `AGENTS.md`，降低会话信息丢失风险。
* 规划应优先控制范围，避免一开始引入复杂 Graph、完整 LLM Wiki、多 Agent 自治或复杂 UI。
* MVP 首批资料源只包含 AI 对话与 Markdown/Web 文档。
* 代码库不纳入 MVP ingest；后续单独讨论代码仓库读取、索引和引用方式。
* 代码库资料不能默认套用普通文档 chunk 处理，未来应按代码资料特性重新设计。
* MVP 检索底座采用 PostgreSQL metadata + PostgreSQL full-text search，暂不引入 pgvector 或 OpenSearch。
* Context Pack v0 采用 JSON + Markdown hybrid：外层 JSON 承载结构化字段，内部 `context_pack_markdown` 承载可直接注入主 Agent 的上下文正文。
* 第一个实施 PRD 合并 M1+M2，目标是一次完成可调用、可摄入、可检索、可引用、可返回 Context Pack v0 的 MVP 闭环。
* MVP 默认使用 Docker Compose 管理 PostgreSQL，保证本地启动、验收、备份恢复路径一致。
* MVP 技术栈采用 Python。
* MVP 暂不引入 LangChain、LlamaIndex、Haystack 等 RAG/Agent 框架；未来在文档解析、文档切块、检索增强或评测阶段可考虑 LlamaIndex 等框架作为辅助 adapter。
* MVP internal/local HTTP 层使用 FastAPI。
* MVP MCP 层使用官方 MCP Python SDK 的 `FastMCP`。
* MVP 数据库访问与 migration 使用 SQLAlchemy + Alembic。
* MVP Python 包管理与项目脚手架使用 uv。
* MVP 测试使用 pytest + pytest-asyncio，集成测试连接 Docker Compose PostgreSQL。
* MVP Raw Archive 默认存储在项目内 `data/raw/`，真实资料必须通过 `.gitignore` 排除。
* MVP 不实现专门备份/恢复命令；只要求 Docker volume 与 `data/raw/` 路径清楚，可手动备份。
* MVP ingest 输入只支持本地文件路径，暂不支持 raw content 直传或 URL 抓取。
* MVP AI 对话 ingest 同时支持 Markdown/transcript 文本与 JSONL 文件，并归一化到统一 conversation/turn 结构。
* MVP Markdown/Web 文档只支持本地 `.md` / `.txt` 文件；HTML/PDF/docx 解析后置。
* MVP chunk 策略采用结构优先 + 上限切分：Markdown 按 heading/section，AI 对话按 turn/window，超长再按长度切分并保留少量 overlap。
* MVP locator 采用两层设计：主 locator 为统一行号范围，metadata 保留 heading_path、turn/window、roles 等 source_type-specific 语义信息。
* MVP canonical source identity 使用显式 `canonical_key`，可选自动推断；未传时使用 `source_type + normalized_absolute_file_path`。
* MVP source_type 枚举使用 `ai_conversation` 与 `markdown_doc`。
* MVP ingest 支持单文件导入和非递归目录导入；目录导入只处理当前目录下匹配扩展名的文件。
* MVP 目录批量 ingest 遇到单个文件失败时继续处理其他文件，并在 ingest report 记录 succeeded、skipped、failed。
* MVP `search_knowledge` 排序采用 PostgreSQL FTS rank + title boost，不加入 recency boost。
* MVP `get_context_pack` v0 基于 search top_k 结果组包，并做去重与每 source evidence 数量限制。
* MVP Context Pack v0 默认返回最多 10 条 evidence，每个 source 最多 3 条。
* MVP `get_context_pack` 暴露 `budget_tokens` 参数，但只做软限制；不引入精确 tokenizer。
* MVP Context Pack 保留 `Conflicts / Caveats` 段落，但只写检索限制和未检测说明，不做真正冲突检测。
* MVP Agent 接入验收优先使用 Codex；如 Codex MCP 配置受限，则使用任意 MCP client smoke test 作为 fallback。
* MVP 提供最小 CLI：`ingest`、`search`、`read`、`context-pack`，用于本地调试和验收；CLI 复用 application service。
* MVP CLI 使用 Typer。
* MVP 配置管理使用 Pydantic Settings，并提供 `.env.example`。
* MVP 日志使用 Python logging + 结构化 JSON 日志。
* MVP 不单独建 audit log 表；使用 `ingest_jobs` + structured logs 追踪写入与运行事件。
* MVP 权限模型为本地默认允许写入；服务默认绑定 localhost；远程暴露、认证和细粒度权限后置。
* MVP 必须创建必要 schema indexes 与 PostgreSQL FTS GIN index；ingest 后数据应立即可搜索；不提供独立 reindex/rebuild 命令。
* MVP PostgreSQL FTS `search_vector` 使用数据库层自动生成，应用层不直接写入 search_vector。
* MVP PostgreSQL FTS 使用 `simple` 配置，不引入中文分词插件或多语言词典配置。
* MVP `search_knowledge` 支持 `source_type`、`top_k` 和 `canonical_key` 过滤；title/date filters 后置。
* MVP `search_knowledge` 输出稳定证据结构：`result_id/chunk_id`、`source_id`、`version_id`、`canonical_key`、`title`、`source_type`、`snippet`、`score`、`citation`、`metadata`。
* MVP `read_source` 返回 citation 行号范围内容，并支持可选 `context_lines` 前后文。
* MVP `read_source` 支持 `chunk_id` 快捷读取，也支持 `source_id + version_id + locator` 完整 citation 读取。
* MVP `ingest_source` 返回完整 ingest report，包含 job/source/version/hash/chunk/report 明细。
* MVP evaluation corpus 放在 `tests/fixtures/`，只使用合成或非私密样例。
* MVP 检索评测问题使用 `tests/fixtures/eval_queries.jsonl`，每行一个 query expectation。
* MVP PRD 已于 2026-06-04 经用户确认完成，可进入 Trellis Phase 2 准备。

## Acceptance Criteria (Evolving)

* [x] 项目级目标、边界、阶段路线被整理成可执行 PRD。
* [ ] M1 到 M5 每个阶段都有目标、范围、产物、验收标准和完成定义。
* [x] MVP 范围明确列出必须做与明确不做。
* [x] 技术路线关键决策记录为 ADR-lite。
* [x] 后续实施计划被拆成小 PR / 小任务顺序。
* [x] `AGENTS.md` 包含本次澄清阶段的临时上下文块。

## Definition of Done

* 用户确认项目级路线与 MVP 边界。
* 用户确认至少第一个实施 PRD，可进入 Trellis Phase 2。
* 任务 PRD 与 `AGENTS.md` 临时块都反映最新共识。
* 明确如何开始、如何推进、如何验收、如何确认完成。

## Confirmed MVP Implementation PRD

* PRD: `.trellis/tasks/06-03-pkcs-mvp-m1-m2/prd.md`
* Status: confirmed by user on 2026-06-04.
* Scope: combined M1 + M2 MVP.
* Next workflow step: Trellis Phase 2 preparation for `.trellis/tasks/06-03-pkcs-mvp-m1-m2`.
* Future planning: M3-M5 remain separate PRDs after MVP planning is closed.

## Out of Scope (Explicit)

* 本轮不实现业务代码，除非用户明确要求进入实现。
* 本轮不搭建完整 LLM Wiki / GraphRAG / 多 Agent 自治系统。
* 本轮不追求完整 UI 产品。
* 本轮不自动导入真实私密资料。
* MVP 不包含 GitHub repo ingest、代码 chunk、symbol search、代码语义检索或代码仓库读取能力。

## Technical Notes

* Source design document: `personal_knowledge_context_server_design.md`
* Task directory: `.trellis/tasks/06-03-pkcs-project-plan`
* Temporary planning context target: `AGENTS.md`
* Current repo implementation state: no application source code found via `rg --files`; planning starts from design document.
* MCP official docs describe servers as exposing tools, resources, and prompts. PKCS should begin with model-callable tools and later consider resources for browseable source/context access: https://modelcontextprotocol.io/docs/learn/server-concepts
* MCP Streamable HTTP supports independent server processes and multiple client connections, but requires Origin validation, localhost binding for local servers, and authentication for connections: https://modelcontextprotocol.io/specification/2025-06-18/basic/transports
* MCP tool outputs can include structured content and optional output schemas. PKCS tools should use stable JSON schemas and may also return Markdown text for model readability: https://modelcontextprotocol.io/specification/2025-06-18/server/tools
* PostgreSQL full-text search is a viable lightweight first search layer: https://www.postgresql.org/docs/current/textsearch.html
* pgvector supports vector similarity search inside PostgreSQL, which keeps vectors with metadata and can be added after lexical search: https://github.com/pgvector/pgvector
* OpenSearch provides BM25 keyword search and can later support heavier search workloads, but it increases operational complexity: https://docs.opensearch.org/latest/search-plugins/keyword-search/

## Research Notes

### What Similar Tools and Protocols Suggest

* MCP is the right external Agent integration direction because it standardizes model-callable tools and read-only resources.
* PKCS should expose a small set of stable tools first, not leak internal retrieval implementation details to clients.
* Tool results should be structured and schema-validatable, while including readable Markdown where useful for model consumption.
* Local HTTP/MCP servers need explicit security choices from the start: bind locally by default, validate origins, and do not expose write tools without authorization.
* Retrieval systems usually need lexical search before semantic search because exact names, file paths, symbols, aliases, and citations matter heavily in personal knowledge.

### Constraints From This Project

* There is no application code yet, so implementation should optimize for a clean first architecture rather than compatibility with existing code.
* The source universe is heterogeneous: AI conversations, Markdown/web pages, GitHub repos, work notes, email, game/anime/entity wiki materials, and official API docs.
* Evidence traceability is core, so every result must preserve `source_id`, `version_id`, and `locator`.
* The user wants end-to-end shared planning before implementation; therefore each phase should be accepted as a PRD before coding begins.

### Feasible Technical Approaches

**Approach A: MCP-first with internal HTTP service** (Recommended)

* How it works: implement domain logic as a service layer; expose MCP tools for agents; optionally expose local HTTP endpoints for testing, health checks, and future non-MCP clients.
* Pros: matches the target users, preserves stable tool contracts, still gives easy local testability.
* Cons: slightly more scaffolding than MCP-only.
* Status: selected for MVP.

**Approach B: HTTP API first, MCP adapter later**

* How it works: build REST/JSON endpoints first, then wrap them in MCP tools.
* Pros: easiest to test with generic clients and scripts.
* Cons: delays real Agent integration and may bias API shape away from model-callable tools.

**Approach C: MCP-only MVP**

* How it works: expose only MCP tools, with no separate API surface beyond internal modules.
* Pros: smallest external surface.
* Cons: harder to debug, test, automate, and reuse outside MCP clients.

### Feasible Search Backend Approaches

**Approach A: PostgreSQL metadata + PostgreSQL FTS first** (Recommended for MVP)

* How it works: store source/version/chunk/citation tables in PostgreSQL and index searchable chunk text with built-in full-text search.
* Pros: low moving parts, good enough for exact terms, preserves metadata locality, easy to back up.
* Cons: semantic search quality is limited until vectors/reranking are added.
* Status: selected for MVP.

**Approach B: PostgreSQL + pgvector hybrid**

* How it works: add vector embeddings to PostgreSQL while keeping metadata and FTS in the same database.
* Pros: adds semantic recall without a separate search cluster.
* Cons: introduces embedding model choice, vector index tuning, and more ingest cost.

**Approach C: PostgreSQL + OpenSearch**

* How it works: PostgreSQL remains system of record; OpenSearch handles lexical and later hybrid retrieval.
* Pros: strong search engine capabilities and more scalable search architecture.
* Cons: operationally heavier; likely premature before the first personal MVP.

### LLM/RAG Framework Considerations

Framework candidates considered:

* LangChain / LangGraph: strong for agent/tool/model orchestration and observability. Less aligned with PKCS MVP because PKCS is not the main Agent; it is a knowledge context service called by an external Agent.
* LlamaIndex: strongest fit for data/RAG/retrieval learning. It supports high-level APIs for quick ingestion/query and lower-level APIs for custom data connectors, indices, retrievers, query engines, and reranking modules.
* Haystack: strong for explicit, typed, composable RAG pipelines. Its DAG/pipeline model is good for production-style indexing/query separation and component testing, but may add more ceremony than needed for the first personal MVP.
* DSPy and similar prompt/programming frameworks: more relevant to prompt/evaluation optimization later than to first-version source archive, citations, and FTS retrieval.

Framework use should be constrained:

* PKCS must own Raw Archive, `sources`, `source_versions`, `chunks`, `citations`, `ingest_jobs`, and Context Pack schema.
* A framework may be introduced as an adapter layer for parsing, transformations, retrievers, rerankers, query routing, or evaluation.
* A framework must not become the source of truth for source identity, versioning, citation locators, or read_source behavior.
* MVP should avoid internal agent orchestration; the main Agent remains outside PKCS.

Recommended direction if a framework is introduced:

* Use LlamaIndex first, but only in a bounded adapter role.
* Keep PostgreSQL FTS as the selected MVP search backend.
* Do not use LlamaIndex's default vector-first quickstart as the core architecture.
* Add a spike/PR to evaluate LlamaIndex integration against PKCS data model before committing broadly.

## Initial Project Structure Proposal

### Project-Level Phases

* Phase 0: Planning and executable PRD set
* Phase 1: M1 接入骨架与数据底座
* Phase 2: M2 摄入与基础检索 MVP
* Phase 3: M3 检索编排与 Context Pack
* Phase 4: M4 特色知识源增强
* Phase 5: M5 知识沉淀、安全、评测与运维

### MVP Success Statement

MVP 完成时，至少一个真实主 Agent 能调用 PKCS 工具，导入小型个人资料集，搜索相关资料，读取原文证据，并拿到带引用的 Context Pack v0 来完成一次真实规划、写作或编码任务。

## Expansion Sweep

### Future Evolution

* PKCS 未来会从单人本地工具演进到多 Agent、多资料源、可评测、可备份恢复的长期知识基础设施。
* 当前值得保留的扩展点是稳定工具接口、SearchProvider 抽象、SourceType parser/ingester 抽象、ContextPack schema。

### Related Scenarios

* `search_knowledge`、`read_source`、`get_context_pack` 必须形成闭环；否则 Agent 只能拿到搜索片段，不能验证证据。
* `ingest_source` 是写入工具，必须和只读检索工具分离，并从 MVP 开始记录权限和 audit 思路。

### Failure and Edge Cases

* 重复导入、版本覆盖、索引损坏、source locator 不可回读，是 MVP 必须防住的失败路径。
* 远程 HTTP/MCP 暴露、未授权写入、AI 推理污染长期记忆，是后续必须控制的安全路径；MVP 可先默认本地只读优先。

## Decision (ADR-lite)

### ADR-001: MVP Interface Shape

**Context**: PKCS 的目标使用者是 Claude Code、Codex、OpenClaw 等外部 Agent，因此第一版需要尽早验证真实 Agent 工具调用。同时，开发和验收阶段也需要稳定的健康检查、测试和脚本入口。

**Decision**: MVP 采用 MCP-first with internal/local HTTP service。Agent-facing 能力优先通过 MCP tools 暴露；内部/local HTTP 用于 `health_check`、开发测试、本地脚本和未来非 MCP 自动化入口。

**Consequences**: 该方案比 MCP-only 多一点脚手架，但能同时保证真实 Agent 接入、可测试性和未来扩展。HTTP 默认只绑定本地；远程暴露时必须补充认证、Origin validation 和写入权限控制。

### ADR-002: MVP Source Type Scope

**Context**: PKCS 未来会处理代码仓库，但代码资料与普通文档不同。代码库如果直接按文档 chunk 处理，容易丢失 path、symbol、line range、module structure 等关键语义，也可能让后续代码检索路线被早期错误模型绑定。

**Decision**: MVP 首批资料源只支持 AI 对话与 Markdown/Web 文档。GitHub repo ingest v0、代码仓库读取、代码索引和代码引用格式全部后置，等进入代码专项阶段再单独设计。

**Consequences**: 第一版更容易完成 ingest/search/read_source/context pack 闭环，但暂时不能证明“读取代码仓库”的能力。未来代码能力必须独立建模，不默认继承普通文档 chunk 策略。

### ADR-003: MVP Search Backend

**Context**: 第一版最重要的是建立可摄入、可检索、可引用、可读回原文的闭环。向量检索能提升语义召回，但会提前引入 embedding 模型选择、向量重建、成本、召回可解释性和索引维护复杂度。

**Decision**: MVP 检索底座采用 PostgreSQL metadata + PostgreSQL full-text search。PostgreSQL 存储 `sources`、`source_versions`、`chunks`、`citations`、`ingest_jobs` 等主数据，并使用内置全文检索完成第一版 search。

**Consequences**: MVP 搜索更可控、可解释、易部署、易备份。语义召回、pgvector、OpenSearch、reranker 后置；SearchProvider 抽象仍应保留，避免业务逻辑绑定具体检索实现。

### ADR-004: Context Pack v0 Format

**Context**: Context Pack 是 PKCS 的核心产物。它既要能被外部 Agent 直接阅读和注入上下文，也要能被测试、校验、追踪来源，并被后续工具链处理。

**Decision**: Context Pack v0 采用 JSON + Markdown hybrid。工具返回外层 JSON，包含 `query`、`retrieval_plan`、`sources`、`followup_read_suggestions`、`context_pack_markdown` 等字段；Markdown 正文用于组织证据、提示、冲突和后续阅读建议。

**Consequences**: 该格式比 Markdown-only 更容易测试和追踪，比 JSON-only 更适合主 Agent 直接使用。实现时必须避免 Markdown 中出现无法追溯的关键结论，所有 evidence 都应映射回 JSON 中的 source refs。

### ADR-005: First Implementation PRD Scope

**Context**: M1 单独完成时只能证明服务骨架存在，无法证明 PKCS 的核心价值。用户希望每个确定的 PRD 都有明确规划，并最终形成从开始到验收的共享路线。

**Decision**: 第一个实施 PRD 合并 M1 + M2，任务为 `.trellis/tasks/06-03-pkcs-mvp-m1-m2`。该 PRD 覆盖 MCP-first 接入、internal/local HTTP、Raw Archive、PostgreSQL metadata、AI 对话 ingest、Markdown/Web ingest、PostgreSQL FTS search、read_source、Context Pack v0。

**Consequences**: 第一个 PRD 范围较大，但能形成真实可验收闭环。为控制风险，实施时必须拆成小 PR：scaffold/schema、ingest、search/read_source、context_pack、agent integration/eval。

### ADR-006: MVP PostgreSQL Runtime

**Context**: PKCS MVP 依赖 PostgreSQL 存储 source/version/chunk/citation 元数据并执行全文检索。为了让 AI agent、用户和未来环境都能一致复现，数据库运行方式需要明确。

**Decision**: MVP 默认使用 Docker Compose 管理 PostgreSQL。项目应提供 `docker-compose.yml`、环境变量样例、持久化 volume、初始化/migration 说明。

**Consequences**: 该方案比直接使用本机数据库多一个 Docker 依赖，但本地启动、验收、备份、恢复和跨机器复现更稳定。

### ADR-007: MVP Implementation Language

**Context**: PKCS MVP 包含文档解析、ingest pipeline、PostgreSQL FTS、检索编排、Context Pack 构造、测试语料和评测脚本。未来还可能加入 embeddings、reranker、LLM Wiki 与更多数据处理任务。

**Decision**: MVP 使用 Python 作为主要实现语言。

**Consequences**: Python 更适合解析、数据处理、检索实验和后续 ML/LLM 集成。MCP 与 HTTP 层也应优先保持 Python 实现，避免第一版引入跨语言边界。

### ADR-008: MVP LLM/RAG Framework Dependency

**Context**: LangChain、LlamaIndex、Haystack 等框架能减少 RAG 组件开发时间，也适合作为个人学习工程化 RAG 的入口。但 PKCS 的核心价值是 Raw Archive、source/version/chunk/citation、read_source 和 Context Pack 的可追溯闭环，这些核心事实模型不能被框架默认流程接管。

**Decision**: MVP 暂不引入 LangChain、LlamaIndex、Haystack 等 RAG/Agent 框架。先用尽量原生的 Python 与明确自有数据模型完成 MVP。未来如果做文档解析、文档切块、检索增强、reranking、query routing 或评测，可优先考虑 LlamaIndex 作为辅助 adapter 或 spike。

**Consequences**: MVP 实现更可控，减少框架抽象带来的绑定和不透明行为；代价是第一版需要自己实现基础 ingest、chunk、search 和 context pack。后续引入框架时必须保证框架结果能稳定映射回 PKCS 的 `source_id`、`version_id`、`locator`。

### ADR-009: MVP HTTP/API Framework

**Context**: PKCS 的主入口是 MCP tools，但 MVP 仍需要 internal/local HTTP 层支持 health check、开发测试、本地脚本和未来非 MCP 自动化。HTTP 层应有清晰 schema、类型校验和测试体验。

**Decision**: MVP internal/local HTTP 层使用 FastAPI。

**Consequences**: FastAPI 提供 Pydantic schema、OpenAPI、依赖注入和成熟测试模式，适合工程化 MVP。MCP 仍是主要 Agent-facing 接口，FastAPI 不应成为外部产品 API 的过度扩张入口。

### ADR-010: MVP MCP Python SDK

**Context**: PKCS MVP 的主要 Agent-facing 接口是 MCP tools。Python 实现需要遵循 MCP 规范，并支持 tools、structured output、开发调试、未来 Streamable HTTP/ASGI 集成等能力。

**Decision**: MVP 使用官方 MCP Python SDK，并使用其中的 `FastMCP` 作为 MCP server interface。

**Consequences**: 该方案直接跟随官方 MCP Python SDK，减少第三方封装风险。FastAPI 和 FastMCP 应共享同一套 application service，避免 HTTP endpoint 与 MCP tool 逻辑重复。

### ADR-011: MVP Database Access and Migrations

**Context**: PKCS MVP 需要 PostgreSQL schema、migration、repository layer、全文检索 SQL、自定义索引和版本化数据模型。数据库访问方案需要兼顾工程化、可维护性和 PostgreSQL 特性支持。

**Decision**: MVP 使用 SQLAlchemy + Alembic。

**Consequences**: SQLAlchemy + Alembic 是成熟 Python 后端组合，适合建模、migration 和自定义 PostgreSQL FTS 查询。实现时应避免 ORM 过度抽象；FTS ranking、locator 查询等数据库特性可以使用明确 SQL 表达。

### ADR-012: MVP Python Package Management

**Context**: PKCS MVP 需要 Python 依赖管理、lockfile、虚拟环境、开发脚本、测试命令和未来 CLI/服务入口。项目应采用现代且易复现的包管理方式。

**Decision**: MVP 使用 uv 进行 Python 包管理和项目脚手架组织。

**Consequences**: uv 提供快速依赖解析、lockfile、虚拟环境和 `pyproject.toml` 脚本组织能力，适合新项目。文档中应明确 `uv sync`、`uv run`、测试、migration 和服务启动命令。

### ADR-013: MVP Testing Strategy

**Context**: PKCS MVP 的核心路径依赖 PostgreSQL migration、PostgreSQL full-text search、source/version/chunk/citation 表、重复导入检测和 read_source 证据回读。只用 mock 无法验证这些行为。

**Decision**: MVP 使用 pytest + pytest-asyncio；集成测试连接 Docker Compose PostgreSQL。

**Consequences**: 测试环境贴近真实本地运行环境，能验证 FTS 和 migration。代价是运行集成测试前需要启动 Docker Compose PostgreSQL；文档应明确测试前置条件和命令。

### ADR-014: MVP Raw Archive Location

**Context**: PKCS 必须保存原始资料，且 read_source 需要能从 citation 读回原文。MVP 阶段路径应直观、容易验收，同时避免真实个人资料被提交到版本库。

**Decision**: MVP Raw Archive 默认存储在项目内 `data/raw/`，并按 source_type 分层。`data/raw/` 和其他真实数据目录必须加入 `.gitignore`。

**Consequences**: 该方案便于本地开发和人工验收。长期部署时可再把 Raw Archive 路径配置到外部磁盘、NAS 或服务器目录。

### ADR-015: MVP Backup and Restore Scope

**Context**: PKCS 长期需要可备份、可恢复、可迁移。但第一版最重要的是完成 Agent access、ingest、search、read_source、Context Pack 闭环。

**Decision**: MVP 不实现专门 backup/export/restore 命令。第一版只要求 Docker volume、PostgreSQL 连接信息、Raw Archive 路径和 `data/raw/` 位置清楚，允许用户手动备份。

**Consequences**: MVP 范围更集中。自动 backup/restore、一键迁移、新机器恢复流程后置到 M5 运维阶段或单独 PRD。

### ADR-016: MVP Ingest Input Shape

**Context**: `ingest_source` 可以设计为本地文件路径、raw content、URL 抓取或多种输入混合。raw content 和 URL 抓取虽然灵活，但会带来大文本传输、来源标识、网页抓取、认证、清洗和失败重试等额外复杂度。

**Decision**: MVP ingest 输入只支持本地文件路径。

**Consequences**: MVP ingest 更可控，Raw Archive 与 content hash 更容易稳定实现。raw content 直传、URL 抓取、网页清洗和远程 source sync 后置。

### ADR-017: MVP AI Conversation File Formats

**Context**: AI 对话资料可能来自手工整理的 Markdown/transcript，也可能来自 Codex/Claude/OpenAI 等工具历史导出的 JSONL。前者可读性好，后者更结构化，二者都对个人知识库有价值。

**Decision**: MVP AI conversation ingest 同时支持 Markdown/transcript 文本与 JSONL 文件。两种输入都归一化到统一 conversation/turn metadata 结构，再进入 chunk、citation 和 search 流程。

**Consequences**: parser 范围略增，但能覆盖手工整理和批量导入两类核心场景。必须为两种格式各提供样例与测试。

### ADR-018: MVP Markdown/Web Document File Formats

**Context**: MVP 支持 Markdown/Web 文档，但第一版只接受本地文件路径。直接支持 HTML、PDF、docx 会引入正文抽取、清洗、编码、格式转换和引用定位复杂度。

**Decision**: MVP Markdown/Web document ingest 只支持本地 `.md` 与 `.txt` 文件。网页资料应先由用户或外部工具保存/转换为 Markdown 或文本后导入。

**Consequences**: MVP parser 简化，引用 locator 更容易稳定。HTML、PDF、docx、网页抓取和自动清洗后置。

### ADR-019: MVP Chunking Strategy

**Context**: 固定长度切分容易破坏 Markdown heading、section 语义和 AI 对话 turn 边界；完全按结构切分又可能产生过长 chunk，影响 FTS 排名、Context Pack budget 和 evidence 可读性。

**Decision**: MVP chunk 策略采用结构优先 + 上限切分。Markdown/文本先按 heading 或 section 切分；AI 对话先按 turn 或相邻 turns window 切分；超长 chunk 再按字符/token 上限切分，并保留少量 overlap。

**Consequences**: 该方案兼顾语义完整性和检索可控性。具体阈值可作为实现参数并通过测试语料调整；chunk metadata 必须保留 heading_path 或 conversation turn/window 信息。

### ADR-020: MVP Locator Format

**Context**: `read_source` 需要稳定读回原文证据。统一行号 locator 实现简单，但缺少 Markdown heading 和 AI 对话 turn 语义；完全 source_type-specific locator 语义强，但会让 read_source 定位逻辑过早复杂化。

**Decision**: MVP locator 采用两层设计。主 locator 使用统一行号范围，例如 `line 12-30`，并保存 `line_start` / `line_end`；chunk/citation metadata 额外保存 source_type-specific 语义信息，例如 `heading_path`、`turn_start`、`turn_end`、`roles`。

**Consequences**: `read_source` 可以统一按行号回读原文，Context Pack 又能展示 heading/turn/role 等语义上下文。schema 稍复杂，但能避免未来返工。

### ADR-021: MVP Canonical Source Identity

**Context**: PKCS 需要区分“同一份资料的新版本”和“另一份新资料”。content hash 只能判断内容是否相同，不能作为长期 source 身份；单纯依赖文件路径会在文件移动或改名时产生误判。

**Decision**: MVP 使用 `canonical_key` 作为 source 的长期身份标识。`ingest_source` 可接收显式 `canonical_key`；如果未提供，则自动推断为 `source_type + ":" + normalized_absolute_file_path`。content hash 用于判断是否创建新 version，而不是用于 source identity。

**Consequences**: 该方案支持简单路径导入，也支持长期稳定身份管理。文件移动后如果用户提供相同 canonical_key，可继续归入同一个 source。实现时需要路径规范化，并定义重复导入与新版本规则。

### ADR-022: MVP Source Type Names

**Context**: `source_type` 会用于 parser 分发、Raw Archive 分层、搜索过滤、Context Pack 展示和验收语料分类。命名需要清晰、稳定、不过度泛化。

**Decision**: MVP source_type 枚举使用 `ai_conversation` 与 `markdown_doc`。

**Consequences**: 命名简洁明确，适合第一版。后续新增 source_type 时应避免把不同资料类型都塞进泛化的 `document`。

### ADR-023: MVP Ingest File vs Directory Input

**Context**: MVP 只支持本地文件路径输入，但验收需要导入多条 AI 对话和多篇 Markdown/文本文档。只支持单文件会增加手动操作，递归目录会带来过滤、错误报告和目录结构语义复杂度。

**Decision**: MVP `ingest_source` 支持单文件导入和非递归目录导入。目录导入只处理当前目录下与 source_type 匹配的扩展名文件，不递归进入子目录。

**Consequences**: 该方案支持批量样例导入，同时控制范围。递归导入、ignore patterns、目录结构映射和大规模 sync 后置。

### ADR-024: MVP Batch Ingest Error Handling

**Context**: 非递归目录导入可能遇到坏文件、格式不匹配文件或单个 parser 错误。如果失败即中断，一个坏文件会阻塞整个样例语料导入。

**Decision**: MVP 目录批量 ingest 遇到单个文件失败时继续处理其他文件。`ingest_source` 返回 ingest report，至少包含 `succeeded`、`skipped`、`failed` 列表和每个失败项的错误摘要。

**Consequences**: 批量导入更实用，失败可排查。实现时要确保单文件失败不会污染已成功导入的文件；每个文件应有独立 ingest job 或 report item。

### ADR-025: MVP Search Ranking

**Context**: MVP 使用 PostgreSQL full-text search。单纯 FTS rank 足够轻量，但标题命中通常比正文命中更能说明资料相关性。recency boost 可能让较新的但不够相关的资料压过旧的关键证据。

**Decision**: MVP `search_knowledge` 排序采用 PostgreSQL FTS rank + title boost，不加入 recency boost。

**Consequences**: 搜索结果保持可解释，并增强标题命中的重要性。时间过滤可以作为 filter 保留，但默认排序不因时间自动加权。

### ADR-026: MVP Context Pack Selection Strategy

**Context**: 如果 `get_context_pack` 直接使用 search top_k 结果，单一 source 的相邻 chunk 可能占满 Context Pack，降低资料多样性和可读性。MVP source_type 只有两个，不需要复杂多样性算法，但需要基本去重。

**Decision**: MVP `get_context_pack` v0 基于 `search_knowledge` top_k 结果组包，并执行去重与每 source evidence 数量限制。

**Consequences**: Context Pack 更均衡，不容易被单一资料刷屏。实现不做复杂 rerank 或跨 source_type 配额；只做轻量 selection。

### ADR-027: MVP Context Pack Evidence Limits

**Context**: Context Pack 需要在信息量和上下文长度之间平衡。过少 evidence 可能不足以支持主 Agent 判断；过多 evidence 会拖慢阅读并增加上下文成本。

**Decision**: MVP Context Pack v0 默认最多返回 10 条 evidence，每个 source 最多 3 条。

**Consequences**: 第一版上下文信息量较充足，同时避免单一 source 刷屏。未来可根据 `budget_tokens` 或评测结果动态调整。

### ADR-028: MVP Context Pack Budget Tokens

**Context**: Context Pack 需要控制长度，未来主 Agent 调用时也需要传递上下文预算。精确 token 计算需要 tokenizer 和更多模型相关边界处理，MVP 可先保留接口语义。

**Decision**: MVP `get_context_pack` 暴露 `budget_tokens` 参数，但只作为软限制。实现用粗略字符/token 估算控制 `context_pack_markdown` 长度，不引入精确 tokenizer。

**Consequences**: 接口为未来稳定保留预算能力，MVP 实现简单。文档必须明确该限制不是精确 token guarantee。

### ADR-029: MVP Context Pack Caveats Section

**Context**: 原始设计中 Context Pack 需要标记冲突和不确定点。MVP 不应实现复杂冲突检测，但如果完全省略该段落，后续格式会发生变化，也容易让主 Agent 误以为结果已经完整验证。

**Decision**: MVP Context Pack 保留 `Conflicts / Caveats` 段落。第一版只写检索限制、未做冲突检测说明、来源范围和可能不确定性，不做真正冲突检测。

**Consequences**: Context Pack 格式更稳定，也能提醒主 Agent 谨慎使用 evidence。真正冲突检测后置到 M3/M5。

### ADR-030: MVP Agent Integration Acceptance

**Context**: PKCS 的主要价值是被外部 Agent 调用。用户当前工作流重点包括 Codex，但特定客户端 MCP 配置可能受环境限制，不能让验收完全依赖单一客户端。

**Decision**: MVP Agent 接入验收优先使用 Codex。若 Codex MCP 接入配置受限，则使用任意 MCP client smoke test 作为 fallback，证明 MCP tools 可调用。

**Consequences**: 验收贴合实际使用场景，同时保持可执行性。Claude Code、OpenClaw 等多客户端验收后置。

### ADR-031: MVP CLI Scope

**Context**: MCP 和 FastAPI 是主要接口，但本地开发、样例导入、搜索调试和验收会频繁需要命令行入口。完全不做 CLI 会让调试依赖 HTTP/MCP 客户端。

**Decision**: MVP 提供最小 CLI，包含 `ingest`、`search`、`read`、`context-pack`。CLI 只用于本地调试和验收，并复用与 MCP/FastAPI 相同的 application service。

**Consequences**: CLI 增加少量接口层工作，但能显著提升开发与验收效率。backup、restore、reindex、status 等完整管理命令不进入 MVP。

### ADR-032: MVP CLI Framework

**Context**: MVP CLI 需要组织 `ingest`、`search`、`read`、`context-pack` 等命令。项目已经选择 Python、FastAPI 和 Pydantic 风格 schema，CLI 框架应与类型标注和现代 Python 工程化一致。

**Decision**: MVP CLI 使用 Typer。

**Consequences**: Typer 提供类型标注友好的命令定义和较好的开发体验。CLI 只做参数解析和展示，不承载业务逻辑。

### ADR-033: MVP Configuration Management

**Context**: PKCS MVP 需要管理 database URL、Raw Archive 路径、HTTP host/port、默认 top_k、Context Pack defaults 等配置。配置项需要类型校验和本地 `.env` 支持。

**Decision**: MVP 使用 Pydantic Settings 管理配置，并提供 `.env.example`。

**Consequences**: 配置集中、类型清楚、适合 FastAPI/Pydantic 生态。实现时不要把真实私密路径或 credentials 提交到仓库。

### ADR-034: MVP Logging Strategy

**Context**: PKCS MVP 涉及 ingest、search、read_source、context_pack 和数据库错误等关键路径。普通日志足够简单，但结构化日志更利于后续排查 ingest job、source/version 行为和 agent tool 调用。

**Decision**: MVP 使用 Python logging + 结构化 JSON 日志。

**Consequences**: 日志更易查询和分析，适合未来运维与 audit 扩展。MVP 不引入完整 observability 框架；日志必须避免输出完整私密内容或 secrets。

### ADR-035: MVP Audit Log Scope

**Context**: 长期来看，PKCS 需要 audit log 来记录写入、权限、外部 Agent 调用和敏感资料访问。但 MVP 已有 `ingest_jobs` 与 structured logs，单独 audit table 会增加 schema、写入和测试范围。

**Decision**: MVP 不单独建 `audit_logs` 表。写入行为通过 `ingest_jobs` 记录，运行事件通过 structured logs 追踪。

**Consequences**: MVP 范围更小，排查能力仍然够用。完整 audit log 后置到 M5 安全/运维阶段。

### ADR-036: MVP Permission Model

**Context**: PKCS 涉及个人资料写入和读取。长期需要认证、权限、写入审计和敏感资料隔离。但 MVP 是本地个人开发与验收环境，过早实现认证会扩大范围。

**Decision**: MVP 本地默认允许写入工具；服务默认绑定 localhost。远程暴露不作为 MVP 支持场景，认证、API key、细粒度权限和远程写入控制后置。

**Consequences**: MVP 开发和验收更顺畅，同时通过 localhost 默认绑定降低暴露风险。文档必须明确不要将 MVP 服务直接暴露到公网或不可信网络。

### ADR-037: MVP Index and Reindex Scope

**Context**: PostgreSQL 中存在两类索引：schema 层普通 index，例如 canonical_key、content_hash、source/version/chunk 外键相关索引；以及用于 `search_knowledge` 的 PostgreSQL full-text search index，例如 `search_vector` 上的 GIN index。MVP 必须有这些索引才能稳定查询和搜索。单独 reindex/rebuild 命令则用于后续索引规则变化、损坏修复或检索后端切换。

**Decision**: MVP 必须在 migration 中创建必要 schema indexes 和 PostgreSQL FTS GIN index。ingest 写入 chunk 后数据应立即可搜索。MVP 不提供独立 `reindex` / `rebuild-index` 命令。

**Consequences**: 第一版搜索能力完整且范围受控。后续如果修改 chunk 策略、search_vector 规则、检索权重或切换到 pgvector/OpenSearch，再单独设计 reindex/rebuild 流程。

### ADR-038: MVP FTS Search Vector Generation

**Context**: PostgreSQL FTS 需要 `search_vector` 支持检索和 GIN index。该字段可以由数据库 generated column / expression 自动生成，也可以由 trigger 或应用层写入。MVP 的 title/content 加权规则较简单。

**Decision**: MVP `search_vector` 使用数据库层自动生成。应用层只写 title/content/metadata，不直接写入 `search_vector`。

**Consequences**: ingest 代码更简单，更新 title/content 时不容易忘记同步 search_vector。后续如果需要 source_type-specific search document、alias/entity 拼接或复杂字段加权，再重新评估 trigger 或应用层构造。

### ADR-039: MVP PostgreSQL FTS Dictionary

**Context**: PKCS 资料会混合中文、英文、专有名词、工具名和项目术语。PostgreSQL `english` 配置对英文 stemming 有帮助，但中英文混合和专有名词可能引入不必要行为；中文分词插件会增加部署复杂度。

**Decision**: MVP PostgreSQL FTS 使用 `simple` 配置。

**Consequences**: 第一版检索配置简单、部署稳定，适合中英文混合关键词和专有名词。中文分词、语言感知检索和更强召回后置。

### ADR-040: MVP Search Filters

**Context**: `search_knowledge` 需要足够的过滤能力支持调试和验收，但过滤条件过多会扩大接口和测试范围。`canonical_key` 能将搜索限定到某一份长期 source，适合验证版本、chunk、citation 和 Context Pack 行为。

**Decision**: MVP `search_knowledge` 支持 `source_type`、`top_k` 和 `canonical_key` 过滤。title/date filters 不进入 MVP。

**Consequences**: 搜索接口保持简洁，同时能按 source 精确调试。标题相关性通过 title boost 体现，而不是 title filter；时间过滤后置。

### ADR-041: MVP Search Result Shape

**Context**: `search_knowledge` 的结果会被 MCP tools、FastAPI、CLI、Context Pack builder 和测试共同使用。输出必须稳定、结构化、可追溯，不应只是自然语言片段。

**Decision**: MVP `search_knowledge` 输出稳定证据结构，包含 `result_id` / `chunk_id`、`source_id`、`version_id`、`canonical_key`、`title`、`source_type`、`snippet`、`score`、`citation` 和 `metadata`。`citation` 至少包含 `locator`、`line_start`、`line_end`。MVP 不输出 LLM 生成的 `why_relevant`。

**Consequences**: 搜索结果可被 read_source 和 Context Pack 稳定消费，也便于测试。相关性解释后续可通过模板或 rerank/LLM 阶段增强。

### ADR-042: MVP Read Source Context

**Context**: `read_source` 需要让 Agent 验证 citation 对应原文。只返回行号范围最精确，但可能缺少上下文；默认返回整份 source 又会过长。

**Decision**: MVP `read_source` 返回 citation 行号范围内的内容，并支持可选 `context_lines` 参数，用于返回前后若干行上下文。

**Consequences**: `read_source` 既保持可控长度，又能按需提供上下文。默认不返回整份 source；如需整份 source，后续可设计单独接口或显式参数。

### ADR-043: MVP Read Source Addressing

**Context**: `search_knowledge` 结果包含 `chunk_id`，Agent 和 CLI 常需要直接读回该 chunk 的原文；长期引用则需要 `source_id`、`version_id` 和 `locator`，避免只依赖内部 chunk id。

**Decision**: MVP `read_source` 同时支持 `chunk_id` 快捷读取和 `source_id + version_id + locator` 完整 citation 读取。

**Consequences**: 搜索到读取的链路更顺畅，同时保留长期可追溯引用能力。接口实现需要校验两种 addressing mode，避免混传歧义。

### ADR-044: MVP Ingest Report Shape

**Context**: `ingest_source` 既支持单文件，也支持非递归目录导入。MVP 需要清楚表达是否创建了新 source、新 version、多少 chunks，以及目录导入中哪些文件成功、跳过或失败。

**Decision**: MVP `ingest_source` 返回完整 ingest report，包含 `ingest_job_id`、`status`、`source_id`、`version_id`、`canonical_key`、`content_hash`、`created_new_source`、`created_new_version`、`chunks_created`、`succeeded`、`skipped`、`failed`。

**Consequences**: 返回结构更利于 CLI、MCP、HTTP 和测试统一验收。单文件导入也使用同一 report shape，避免接口分叉。

### ADR-045: MVP Evaluation Corpus Location and Privacy

**Context**: MVP 需要固定样例语料和检索问题验证 ingest/search/read_source/context_pack。真实个人资料不应进入版本库，且会降低测试可复现性。

**Decision**: MVP evaluation corpus 放在 `tests/fixtures/`，只使用合成或非私密样例。

**Consequences**: 样例可提交、可复现、可用于 CI 和他人验收。真实个人资料评测后续可放在 gitignored 私有目录中单独设计。

### ADR-046: MVP Evaluation Query Format

**Context**: MVP 需要至少 20 个检索测试问题，并验证 expected sources 是否进入 top 5/top 10。评测问题应易追加、易逐条运行、适合未来扩展字段。

**Decision**: MVP 检索评测问题使用 `tests/fixtures/eval_queries.jsonl`，每行一个 query expectation。字段至少包含 `query`、`expected_canonical_keys`、`expected_source_types` 和可选 `notes`。

**Consequences**: JSONL 便于追加、流式读取和逐条测试。后续可扩展 `must_not_sources`、`expected_chunks`、`difficulty` 等字段。
