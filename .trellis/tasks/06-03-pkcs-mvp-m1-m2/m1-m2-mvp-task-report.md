# PKCS M1+M2 MVP 阶段任务报告

生成日期：2026-06-09
任务目录：`.trellis/tasks/06-03-pkcs-mvp-m1-m2`
当前最新提交：`31e889b docs: document source key prefix mappings`

## 1. 阶段结论

本阶段 M1+M2 MVP 已经在本地完成实现、测试和提交。这里的 MVP（Minimum Viable Product，最小可用产品）不是完整长期产品，而是第一版可运行闭环：外部 Agent（智能体，也就是 Codex、Claude Code 这类会调用工具的 AI 编程助手）可以通过 MCP（Model Context Protocol，模型上下文协议）工具访问 PKCS（Personal Knowledge Context Server，个人知识上下文服务器），导入资料，搜索资料，读回原始证据，并生成 Context Pack（上下文包，即可被主 Agent 注入上下文的结构化资料包）。

当前阶段完成到 PR7。PR（Pull Request，拉取请求；在本项目中也指一次小步可提交工程阶段）从 PR1 到 PR7 均已完成并提交。之后又完成了数据库建模清理子任务：拆分 source format、normalized format、knowledge type，移除用户原始完整路径作为长期身份，改用 Raw Archive 和内部 canonical key 作为证据回读基础。

本阶段可以通过自动化测试、命令行流程、MCP 工具调用 fallback（后备验收路径）和固定评测语料来验收。真实 Codex CLI MCP 验收文档已补充在 `.trellis/tasks/06-03-pkcs-mvp-m1-m2/codex-cli-mcp-acceptance.md`，当前状态是“文档就绪，待人工执行”。最近一次完整验证结果为：

```powershell
docker compose ps postgres
uv run alembic upgrade head
uv run pytest
git diff --check
```

最近一次结果：

* PostgreSQL（开源关系型数据库）容器为 healthy（健康状态）。
* Alembic（数据库迁移工具）迁移到 head（最新迁移版本）成功。
* pytest（Python 测试框架）通过：32 passed，1 warning。
* `git diff --check` 无空白错误，仅有 Windows 换行提示。

## 2. 专业名词表

| 术语 | 中文解释 |
| --- | --- |
| PKCS | Personal Knowledge Context Server，个人知识上下文服务器，本项目要构建的本地知识后端服务。 |
| M1 | Milestone 1，第一阶段里程碑，本项目中指接入骨架与数据底座。 |
| M2 | Milestone 2，第二阶段里程碑，本项目中指摄入与基础检索 MVP。 |
| MVP | Minimum Viable Product，最小可用产品，用最小范围证明核心价值的第一版可运行系统。 |
| PRD | Product Requirements Document，产品需求文档，记录范围、验收标准和技术约束。 |
| PR | Pull Request，拉取请求；在当前本地开发中也用来表示一次小步可验证、可提交的工程阶段。 |
| Agent | 智能体，能根据上下文调用工具、执行任务的 AI 助手，例如 Codex、Claude Code。 |
| MCP | Model Context Protocol，模型上下文协议，用标准方式让 Agent 调用外部工具或读取外部上下文。 |
| FastMCP | MCP Python SDK 中的快速服务接口，用来在 Python 中定义 MCP tools（工具）。 |
| MCP tool | MCP 工具，暴露给 Agent 调用的函数，例如 `search_knowledge`。 |
| MCP client | MCP 客户端，调用 MCP 服务的一方，例如 Codex 或测试中的 generic client。 |
| generic MCP client fallback | 通用 MCP 客户端后备验收路径，当真实 Codex MCP 配置不可用时，用 SDK 直接调用工具证明链路可用。 |
| HTTP | Hypertext Transfer Protocol，超文本传输协议，本项目用于本地健康检查接口。 |
| FastAPI | Python Web 框架，本项目用于本地 HTTP 服务。 |
| CLI | Command Line Interface，命令行接口，用于本地调试和验收。 |
| Typer | Python 命令行框架，本项目用于实现 `pkcs ingest/search/read/context-pack` 命令。 |
| uv | Python 包管理和命令运行工具，本项目用于安装依赖、运行测试和命令。 |
| PostgreSQL | 开源关系型数据库，本项目用于保存元数据、分块、引用和全文检索索引。 |
| Docker Compose | 容器编排工具，本项目用于启动本地 PostgreSQL 数据库。 |
| SQLAlchemy | Python 数据库 ORM（对象关系映射）工具，用 Python 类操作数据库表。 |
| ORM | Object Relational Mapping，对象关系映射，把数据库表映射成代码中的对象。 |
| Alembic | SQLAlchemy 生态中的数据库迁移工具，用来创建和升级数据库表结构。 |
| migration | 数据库迁移脚本，描述数据库结构如何从一个版本变到另一个版本。 |
| Raw Archive | 原始资料归档，保存摄入时的原始文件字节，保证以后能按引用读回证据。 |
| source | 资料源，一份长期存在的资料身份，例如一篇 Markdown 文档或一段 AI 对话。 |
| source_version | 资料版本，同一个 source 内容变化后生成的新版本。 |
| chunk | 内容分块，把较长资料按结构切成可检索片段。 |
| citation | 引用记录，保存 chunk 对应的 source、version、locator 和原文片段信息。 |
| locator | 定位符，本项目主要使用 `line N-M` 行号范围定位原文。 |
| metadata | 元数据，辅助描述资料的结构信息，例如标题路径、角色、turn 范围。 |
| source_type | 资料类型，本 MVP 支持 `ai_conversation` 和 `markdown_doc`。 |
| ai_conversation | AI 对话资料类型，支持 Markdown/transcript 文本和 JSONL。 |
| markdown_doc | Markdown/text 文档资料类型，支持 `.md` 和 `.txt`。 |
| canonical_key | 规范化资料键，用于标识同一份长期 source。未传时由 source_type 加绝对路径生成。 |
| content_hash | 内容哈希，用 SHA-256 算法计算文件内容指纹，用于判断重复或新版本。 |
| SHA-256 | 安全哈希算法，用来把内容计算成固定长度指纹。 |
| ingest | 摄入，把本地文件解析、归档、写入数据库并生成 chunk/citation 的过程。 |
| parser | 解析器，把 Markdown、文本或 JSONL 变成统一内部结构的代码。 |
| structure-first chunking | 结构优先切块，优先按标题、章节、对话 turn 切分，再按长度上限细切。 |
| overlap | 重叠内容，切块之间保留少量相邻行，减少上下文断裂。 |
| FTS | Full Text Search，全文检索，用数据库文本索引进行关键词搜索。 |
| search_vector | PostgreSQL 的全文检索向量字段，把 chunk 的标题和正文转成可搜索索引。 |
| GIN index | PostgreSQL 的倒排索引类型，适合加速全文检索。 |
| `simple` dictionary | PostgreSQL FTS 的简单词典配置，不做复杂语言分词。 |
| websearch_to_tsquery | PostgreSQL 函数，把用户搜索字符串转成全文检索查询。 |
| title boost | 标题加权，标题命中的结果会比纯正文命中获得额外分数。 |
| top_k | 返回前 K 个搜索结果的数量参数。 |
| SearchProvider | 搜索提供者抽象，让业务层不直接绑定 PostgreSQL FTS，未来可替换实现。 |
| read_source | 读回原文证据的能力，根据 chunk_id 或 source/version/locator 读取 Raw Archive。 |
| Context Pack | 上下文包，把搜索命中的证据、来源、后续阅读建议和 Markdown 文本组合成 Agent 可用资料。 |
| JSON | JavaScript Object Notation，结构化数据格式，本项目工具返回的主要机器可读格式。 |
| Markdown | 轻量标记文本格式，本项目用来让 Agent 和人类更容易阅读 Context Pack。 |
| evidence | 证据，Context Pack 中选出的可追溯原文片段。 |
| Caveats | 限制说明，Context Pack 中说明 MVP 未做语义检索、未做真实冲突检测等限制。 |
| budget_tokens | 软长度预算参数，用于提示 Context Pack Markdown 尽量不要过长，不是精确 token 计算。 |
| token | 模型处理文本的近似单位；本 MVP 不做精确 tokenizer（分词器）计算。 |
| reranker | 重排序器，先搜索再用模型或算法重新排序结果；本 MVP 未实现。 |
| embedding | 向量表示，把文本转成数字向量用于语义检索；本 MVP 未实现。 |
| pgvector | PostgreSQL 的向量检索扩展；本 MVP 未引入。 |
| OpenSearch | 搜索引擎服务；本 MVP 未引入。 |
| LangChain / LlamaIndex / Haystack | RAG 或 Agent 工程框架；本 MVP 暂不作为核心依赖。 |
| RAG | Retrieval-Augmented Generation，检索增强生成，即先检索资料再辅助大模型回答。 |
| Pydantic Settings | Pydantic 的配置管理能力，用环境变量和 `.env` 文件生成配置对象。 |
| `.env.example` | 环境变量样例文件，说明需要哪些配置但不包含真实密钥。 |
| localhost | 本机地址，本 MVP 服务默认仅绑定本机，避免远程暴露。 |
| structured JSON logs | 结构化 JSON 日志，按字段记录事件，便于机器分析；本项目避免记录完整私密内容。 |
| audit_logs | 审计日志表，本 MVP 不单独实现，使用 `ingest_jobs` 和结构化日志做基础追踪。 |
| ingest_jobs | 摄入任务表，记录每次摄入的状态、摘要和错误。 |
| eval corpus | 评测语料，用固定合成资料评估检索是否命中目标。 |
| eval_queries.jsonl | 每行一个 JSON 的评测查询文件，记录 query 和预期命中资料。 |
| JSONL | JSON Lines，每行一个 JSON 对象的文本格式。 |
| top 10 hit rate | 目标资料进入前 10 个搜索结果的比例。 |
| top 5 hit rate | 目标资料进入前 5 个搜索结果的比例。 |
| integration test | 集成测试，连接真实 Docker PostgreSQL 等外部依赖验证跨层行为。 |
| smoke test | 冒烟测试，用最短路径确认核心链路可用。 |
| unit test | 单元测试，验证较小代码单元的行为。 |
| pytest-asyncio | pytest 的异步测试插件，用于测试 async MCP 工具调用。 |
| git diff --check | Git 检查命令，用于发现多余空白等提交前问题。 |
| working tree | Git 工作区，当前文件相对最近提交是否有未提交改动。 |

## 3. 当前完成到了哪一阶段

当前 M1+M2 MVP 已经完成到 PR7，也就是这个 MVP 任务的最后一个小步。

| 阶段 | 状态 | 已完成内容 |
| --- | --- | --- |
| PR1 | 已完成并提交 | 项目脚手架、FastAPI 健康检查、FastMCP 服务骨架、Typer CLI 骨架、Docker Compose PostgreSQL。 |
| PR2 | 已完成并提交 | Alembic 数据库迁移、PostgreSQL 表结构、FTS GIN index、Raw Archive、Repository（数据库访问层）。 |
| PR3 | 已完成并提交 | Markdown/text 和 AI conversation 摄入、解析、切块、重复检测、新版本保存、CLI/MCP 摄入工具。 |
| PR4 | 已完成并提交 | PostgreSQL FTS 搜索、SearchProvider 抽象、搜索过滤、标题加权、CLI/MCP 搜索工具。 |
| PR5 | 已完成并提交 | read_source 原文读回、chunk_id 和 source/version/locator 两种寻址、上下文行读取。 |
| PR6 | 已完成并提交 | Context Pack v0，JSON + Markdown 输出，证据上限、每 source 上限、Caveats、soft budget_tokens。 |
| PR7 | 已完成并提交 | 合成评测语料、20 条 eval 查询、检索阈值测试、CLI 端到端 smoke、MCP fallback smoke、文档。 |

因此，按当前 PRD（产品需求文档）定义，M1+M2 MVP 在本地已经完成。下一阶段不属于 M1+M2，而应进入 M3（检索编排与 Context Pack 增强）或先进行真实 Codex MCP 客户端手动验收。

## 4. 当前已经完成了什么

### 4.1 接入能力

已经完成三种入口：

* HTTP（本地网页/接口协议）健康检查：`GET /health`。
* CLI（命令行接口）：`pkcs health`、`pkcs ingest`、`pkcs search`、`pkcs read`、`pkcs context-pack`。
* MCP tools（模型上下文协议工具）：`health_check`、`ingest_source`、`search_knowledge`、`read_source`、`get_context_pack`。

这意味着系统已经不是孤立代码，而是可以被本地命令、HTTP 测试和 Agent 工具协议调用。

### 4.2 数据底座

已经完成 PostgreSQL（关系型数据库）数据结构：

* `sources`：保存长期资料身份。
* `source_versions`：保存资料版本和 Raw Archive 路径。
* `chunks`：保存可检索分块。
* `citations`：保存引用和定位信息。
* `ingest_jobs`：保存摄入任务状态。

已经完成 Raw Archive（原始资料归档）：摄入时保存原始文件副本，后续 `read_source` 不依赖原文件是否被移动或修改。

### 4.3 摄入能力

已经支持：

* `markdown_doc`（Markdown/text 文档）：`.md`、`.txt`。
* `ai_conversation`（AI 对话资料）：`.md`、`.txt`、`.jsonl`。
* 单文件摄入。
* 非递归目录摄入。
* 目录中单文件失败不阻塞其他文件。
* 显式 `canonical_key`（规范化资料键）。
* 未传 `canonical_key` 时用 `source_type + normalized absolute path`（资料类型加规范化绝对路径）推断。
* 相同 `canonical_key` 且相同 `content_hash`（内容哈希）时跳过重复。
* 相同 `canonical_key` 但内容变化时创建新版本。

### 4.4 搜索能力

已经支持 PostgreSQL FTS（全文检索）：

* 使用 PostgreSQL `simple` dictionary（简单词典配置）。
* 使用数据库自动生成的 `search_vector`（全文检索向量）。
* 使用 GIN index（倒排索引）加速搜索。
* 使用 `websearch_to_tsquery`（把搜索词转为 PostgreSQL 查询语法的函数）。
* 使用 FTS rank（全文检索相关性分数）加 title boost（标题加权）。
* 支持 `source_type`（资料类型）、`canonical_key`（资料身份）和 `top_k`（返回数量）过滤。

搜索结果包含稳定证据结构：

* `chunk_id`：分块 ID。
* `source_id`：资料 ID。
* `version_id`：版本 ID。
* `canonical_key`：规范化资料键。
* `title`：标题。
* `source_type`：资料类型。
* `snippet`：命中摘要。
* `score`：检索分数。
* `citation`：引用定位。
* `metadata`：元数据。

### 4.5 原文读回能力

已经完成 `read_source`：

* 可以按 `chunk_id` 快捷读取。
* 可以按 `source_id + version_id + locator` 完整引用读取。
* locator（定位符）使用 `line N-M` 行号范围。
* 支持 `context_lines`（前后文行数）。
* 默认不返回整份原文，只返回引用片段，降低上下文膨胀风险。

### 4.6 Context Pack v0

已经完成 `get_context_pack`：

* 内部调用 `search_knowledge` 搜索。
* 对搜索结果做 chunk deduplication（分块去重）。
* 限制全局最多 10 条 evidence（证据）。
* 限制每个 source（资料源）最多 3 条 evidence。
* 每条 evidence 都通过 `read_source` 读回 Raw Archive 原文。
* 输出 JSON（结构化数据）和 Markdown（可读上下文文本）混合结果。
* Markdown 中包含 `Conflicts / Caveats`（冲突和限制说明）。
* `budget_tokens` 是软限制，不是精确 token 预算。

### 4.7 评测与验收语料

已经完成固定合成语料：

* `tests/fixtures/markdown/`：至少 10 篇 Markdown/text 文档。
* `tests/fixtures/conversations/`：至少 10 段 AI conversation 样例。
* `tests/fixtures/eval_queries.jsonl`：20 条检索评测 query expectation（查询预期）。

验收阈值：

* top 10 hit rate（目标资料进入前 10 的比例）不低于 80%。
* top 5 hit rate（目标资料进入前 5 的比例）不低于 60%。

最近一次完整测试已通过。

## 5. 如何验收当前阶段成果

### 5.1 自动化完整验收

在项目根目录运行：

```powershell
docker compose ps postgres
uv run alembic upgrade head
uv run pytest
git diff --check
```

预期结果：

* PostgreSQL 容器状态为 healthy。
* Alembic 迁移命令成功。
* pytest 显示全部测试通过。
* `git diff --check` 不出现 whitespace error（空白错误）。

### 5.2 只验收 PR7 评测闭环

```powershell
uv run pytest tests/test_acceptance.py
```

该测试会验证：

* fixture corpus（评测语料）数量和格式。
* `eval_queries.jsonl` 查询预期格式。
* 真实 Docker PostgreSQL 上的 FTS 检索阈值。
* CLI ingest/search/read/context-pack 端到端流程。
* MCP generic client fallback 端到端流程。

### 5.3 手动 CLI 验收

可以用命令行手动导入样例、搜索、读回、生成 Context Pack：

```powershell
uv run pkcs ingest tests/fixtures/markdown/product-notes.md --source-type markdown_doc --canonical-key markdown_doc:product-notes
uv run pkcs search "stable citations" --top-k 5
uv run pkcs context-pack "stable citations" --top-k 10 --budget-tokens 800
```

如果需要读回搜索结果，需要先从 `search` 输出中复制 `chunk_id`：

```powershell
uv run pkcs read --chunk-id <chunk_id> --context-lines 2
```

### 5.4 手动 HTTP 健康检查

启动本地 HTTP 服务：

```powershell
uv run uvicorn pkcs.http.app:app --host 127.0.0.1 --port 8765
```

访问：

```text
http://127.0.0.1:8765/health
```

预期返回 `status: ok`。

### 5.5 MCP 验收

当前自动化测试已经用 FastMCP（MCP Python SDK 的服务接口）直接调用了：

```text
health_check -> ingest_source -> search_knowledge -> read_source -> get_context_pack
```

这条链路证明 MCP tools 本身可用。真实 Codex MCP 客户端配置如果可用，可以在后续单独做人工验收；如果不可用，当前 generic MCP client fallback 已满足本 PRD 的 fallback 验收标准。

## 6. 具体技术实现细节

### 6.1 总体架构

当前实现采用分层架构：

```text
CLI / HTTP / MCP
      |
Application Services
      |
Repositories / Raw Archive / SearchProvider
      |
PostgreSQL + data/raw
```

中文解释：

* CLI / HTTP / MCP 是接口层，负责接收外部调用。
* Application Services 是应用服务层，负责业务流程编排，例如摄入、搜索、读回、生成上下文包。
* Repositories 是数据库访问层，封装 PostgreSQL 表读写。
* Raw Archive 是文件归档层，保存原始资料。
* SearchProvider 是搜索提供者抽象，目前实现是 PostgreSQL FTS。

### 6.2 配置实现

配置集中在 `src/pkcs/config.py`：

* 使用 Pydantic Settings（配置对象生成工具）。
* 支持环境变量前缀 `PKCS_`。
* 默认数据库地址为本地 Docker PostgreSQL：`localhost:54329`。
* 默认 Raw Archive 路径为 `data/raw`。
* 默认 `top_k` 为 10。
* 默认 Context Pack evidence 上限为 10，每 source 上限为 3。

### 6.3 数据库实现

数据库模型集中在 `src/pkcs/db/models.py`：

* `Source` 对应 `sources` 表。
* `SourceVersion` 对应 `source_versions` 表。
* `Chunk` 对应 `chunks` 表。
* `Citation` 对应 `citations` 表。
* `IngestJob` 对应 `ingest_jobs` 表。

迁移文件为 `migrations/versions/20260604_0001_initial_schema.py`。

关键设计：

* `chunks.search_vector` 是数据库层 Computed column（计算列），应用层不写入。
* `search_vector` 使用标题和正文组合生成。
* 数据库迁移创建 GIN index 加速全文检索。
* `sources.canonical_key` 唯一，保证长期资料身份稳定。
* `source_versions` 用 `source_id + content_hash` 避免重复版本。

### 6.4 摄入实现

摄入服务在 `src/pkcs/ingest/service.py`。

摄入流程：

1. 校验 source_type（资料类型）。
2. 校验路径必须是本地文件或非递归目录。
3. 读取文件 bytes（字节内容）。
4. 计算 SHA-256 content_hash（内容指纹）。
5. 解析文件，生成 ParsedSource（解析后的资料）和 ParsedChunk（解析后的分块）。
6. 写入 Raw Archive。
7. 写入 `sources`、`source_versions`、`chunks`、`citations`。
8. 更新 `ingest_jobs` 状态。
9. 返回 ingest report（摄入报告）。

解析器在 `src/pkcs/ingest/parsers.py`：

* Markdown/text 按 heading（标题）和 section（章节）结构切分。
* AI conversation 按 transcript（对话文本）或 JSONL turn（对话轮次）解析。
* 分块保留 heading_path（标题路径）、roles（角色）、turn_start/turn_end（对话轮次范围）等 metadata。

### 6.5 搜索实现

搜索服务在：

* `src/pkcs/search/service.py`
* `src/pkcs/search/providers.py`
* `src/pkcs/search/models.py`

当前 SearchProvider（搜索提供者）实现是 PostgreSQL FTS：

* 输入 query（查询文本）。
* 使用 `websearch_to_tsquery('simple', :query)` 转成 PostgreSQL FTS 查询。
* 在 `chunks.search_vector` 上搜索。
* 支持 `source_type`、`canonical_key`、`top_k`。
* 排序为 `ts_rank_cd`（PostgreSQL 相关性分数）加 title boost（标题命中加权）。
* 返回 SearchResponse（搜索响应）和 SearchResult（搜索结果）。

这个阶段没有实现 embedding（向量检索）、reranker（重排序器）、pgvector（向量扩展）或 OpenSearch（独立搜索引擎）。

### 6.6 read_source 实现

读回服务在 `src/pkcs/reader/service.py`。

支持两种寻址方式：

* `chunk_id`：直接用搜索结果里的分块 ID 读回。
* `source_id + version_id + locator`：用完整引用读回。

locator 解析在 `src/pkcs/reader/locators.py`，格式为：

```text
line 4-7
```

读回内容来自 `source_versions.raw_archive_path` 指向的 Raw Archive 文件，不读当前原始路径。这样可以保证即使原始文件被移动或修改，旧 evidence 仍然能读回。

### 6.7 Context Pack 实现

Context Pack 服务在：

* `src/pkcs/context_pack/service.py`
* `src/pkcs/context_pack/models.py`

流程：

1. 接收 query（查询）。
2. 调用 SearchService（搜索服务）取得 top_k 搜索结果。
3. 对 chunk 做 deduplication（去重）。
4. 按每 source 最多 3 条 evidence 做限制。
5. 最多选择 10 条 evidence。
6. 对每条 evidence 调用 ReadSourceService 读回原文。
7. 生成 structured JSON（结构化 JSON）。
8. 同时生成 context_pack_markdown（可直接注入 Agent 的 Markdown 文本）。

Markdown 固定包含：

* Retrieval Plan（检索计划）。
* Sources（资料源列表）。
* Evidence（证据）。
* Followup Read Suggestions（后续读回建议）。
* Conflicts / Caveats（冲突和限制说明）。

### 6.8 MCP 实现

MCP 服务在 `src/pkcs/mcp/server.py`。

当前暴露工具：

* `health_check`：健康检查。
* `ingest_source`：摄入资料。
* `search_knowledge`：搜索资料。
* `read_source`：读回证据。
* `get_context_pack`：生成 Context Pack。

每个 MCP tool 都调用对应 application service（应用服务），没有复制业务逻辑。

### 6.9 CLI 实现

CLI 在 `src/pkcs/cli.py`。

当前命令：

* `pkcs health`
* `pkcs ingest`
* `pkcs search`
* `pkcs read`
* `pkcs context-pack`

CLI 也复用 application service，因此 CLI 验收和 MCP 验收覆盖的是同一套核心业务逻辑。

### 6.10 测试实现

测试文件：

* `tests/test_health.py`：健康检查。
* `tests/test_database_schema.py`：数据库结构和 FTS 计算列。
* `tests/test_repositories.py`：Repository 数据访问。
* `tests/test_raw_archive.py`：原始归档写入。
* `tests/test_ingest.py`：摄入、解析、重复检测、新版本、CLI/MCP 摄入。
* `tests/test_search.py`：搜索结果形状、过滤、标题加权、CLI/MCP 搜索。
* `tests/test_reader.py`：read_source 两种寻址、上下文、错误路径、CLI/MCP 读回。
* `tests/test_context_pack.py`：Context Pack JSON/Markdown、证据限制、Caveats、CLI/MCP。
* `tests/test_acceptance.py`：最终验收语料、检索阈值、CLI 端到端、MCP fallback 端到端。

测试依赖 Docker Compose PostgreSQL，确保不是只测假数据或内存逻辑。

## 7. 已知限制和未做内容

本阶段明确未做：

* 代码仓库 ingest（代码库摄入）。
* 代码 chunking（代码切块）。
* Email ingest（邮件摄入）。
* URL crawling（网页抓取）。
* HTML/PDF/docx 解析。
* embedding（向量检索）。
* pgvector（PostgreSQL 向量扩展）。
* OpenSearch（独立搜索引擎）。
* reranker（搜索结果重排序）。
* LangChain / LlamaIndex / Haystack 作为核心依赖。
* 远程部署、认证、权限系统。
* 备份/恢复/reindex 命令。
* UI（用户界面）。
* 真正的冲突检测。

这些不是遗漏，而是 M1+M2 MVP 的刻意边界。尤其代码库后续需要单独讨论，不应默认按普通文档 chunking 处理。

## 8. 当前阶段完成定义

本阶段可以认为完成，原因是：

* PRD 中定义的 M1+M2 核心闭环已经实现。
* 所有 PR1-PR7 小步均已提交。
* 自动化测试覆盖核心功能和验收语料。
* CLI、HTTP、MCP 三类入口均可用。
* 搜索结果和 Context Pack evidence 均可追溯到 Raw Archive 原文。
* 固定 eval corpus 达到 top 10 和 top 5 检索阈值。
* 文档已经说明如何启动、如何导入、如何搜索、如何读回、如何生成 Context Pack、如何验收。

## 9. 建议的下一步

下一步有两条合理路线：

1. 执行真实 Codex CLI MCP 客户端人工验收：按 `.trellis/tasks/06-03-pkcs-mvp-m1-m2/codex-cli-mcp-acceptance.md` 配置 `pkcs` MCP server，并让 Codex CLI 调用五个 MCP tools 完成一次端到端验收。
2. 开始 M3 规划：讨论 query routing（查询路由）、multi-retriever fusion（多检索器融合）、reranking（重排序）、更强 Context Pack selection（上下文包选择策略）。

如果目标是先确认 M1+M2 成果，建议先走第 1 条。如果目标是继续工程推进，建议进入 M3 PRD 讨论。
