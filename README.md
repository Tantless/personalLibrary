# Personal Knowledge Context Server

PKCS 是一个本地优先的个人知识上下文服务，用来把本地文档和 AI 对话摄入 PostgreSQL，并向外部 agent 提供可追溯的搜索结果、原文证据和 Context Pack。

## 功能概览

* 摄入本地 Markdown/text 文档和 AI conversation 文件。
* 使用 PostgreSQL full-text search 检索知识片段。
* 通过 `read_source` 从 Raw Archive 读取可追溯原文证据。
* 生成 Context Pack v0，包含 JSON 结构化数据和 Markdown 摘要。
* 提供 FastMCP tools，并保留本地 health endpoint 便于部署检查。
* 可选使用 Docling CLI 将 PDF/DOCX/XLSX/HTML 预处理为 Markdown ingest package。

## 环境要求

请先在本机安装：

* Git
* Python 3.11+
* uv: <https://docs.astral.sh/uv/getting-started/installation/>
* Docker 与 Docker Compose: <https://docs.docker.com/get-started/get-docker/>

可选：如果需要摄入 PDF、DOCX、XLSX 或 HTML，请额外安装 Docling CLI，并确保 `docling` 在当前 shell 的 `PATH` 中。

## 快速启动

```bash
git clone https://github.com/Tantless/personalLibrary.git
cd personalLibrary
uv sync
docker compose up -d postgres
uv run alembic upgrade head
uv run pkcs health
```

默认数据库连接为：

```text
postgresql+psycopg://pkcs:pkcs@localhost:54329/pkcs
```

如果 `uv run pkcs health` 返回 `{"status": "ok", ...}`，说明本地环境已启动成功。

## Agent / MCP 用法

PKCS 的推荐使用方式是接入 Codex CLI、Claude Code 等 agent CLI，让 agent 通过 MCP tools 操作知识库。

摄入资料时，不需要用户直接调用底层命令。把 PKCS MCP server 接入 agent CLI 后，让 agent 使用 `pkcs-ingest` skill 处理本地文件；该 skill 会完成预处理，并通过 MCP `ingest_source` 写入知识库。

可暴露给 agent 的 MCP tools：

* `health_check`: 检查 PKCS 服务状态。
* `ingest_source`: 摄入本地文件或已预处理的 Markdown package。
* `search_knowledge`: 检索已摄入知识。
* `read_source`: 按 `chunk_id` 或 citation 读取原文证据。
* `get_context_pack`: 为一个问题生成 Context Pack。

## 支持的输入

直接摄入支持：

* `document`: `.md`, `.txt`
* `ai_conversation`: `.md`, `.txt`, `.jsonl`

目录摄入只处理当前目录层级，不递归进入子目录。

预处理摄入支持单文件：

* Markdown: `.md`, `.markdown`, `.mdx`
* Docling-backed: `.pdf`, `.docx`, `.xlsx`, `.html`, `.htm`

对于 PDF、DOCX、XLSX、HTML 等非 Markdown 输入，由 agent 调用 `pkcs-ingest` skill 完成规范化，再通过 MCP `ingest_source` 摄入生成的 `document.md`。

## 常用 CLI 示例

摄入一份 Markdown 或 text 文档：

```bash
uv run pkcs ingest path/to/document.md --knowledge-type document --canonical-key document:example
```

搜索已摄入资料：

```bash
uv run pkcs search "your search query" --knowledge-type document --canonical-key document:example --top-k 5
```

按搜索结果中的 `chunk_id` 读回原文证据：

```bash
uv run pkcs read --chunk-id "<chunk_id_from_search>" --context-lines 2
```

生成 Context Pack：

```bash
uv run pkcs context-pack "your research question" --knowledge-type document --canonical-key document:example --top-k 8 --budget-tokens 1200
```

如果输入是 PDF、DOCX、XLSX 或 HTML，先生成 ingest package，再摄入生成的 `document.md`：

```bash
uv run pkcs prepare-ingest path/to/source.pdf --slug example
uv run pkcs ingest data/private/ingest-prep/<generated-package>/document.md --knowledge-type document --canonical-key document:example
```

## HTTP 服务

启动本地 HTTP 服务：

```bash
uv run uvicorn pkcs.http.app:app --host 127.0.0.1 --port 8765
```

健康检查 endpoint：

```text
GET http://127.0.0.1:8765/health
```

## MCP Server

`src/pkcs/mcp/server.py` 暴露 FastMCP server object `mcp`。请在你的 MCP client 中指向该 Python module，并确保启动前已完成依赖安装、PostgreSQL 启动和 Alembic migration。

## 配置

配置通过 `PKCS_` 环境变量或 `.env` 覆盖。常用项：

```text
PKCS_DATABASE_URL=postgresql+psycopg://pkcs:pkcs@localhost:54329/pkcs
PKCS_RAW_ARCHIVE_PATH=data/raw
PKCS_DEFAULT_TOP_K=10
PKCS_CONTEXT_PACK_MAX_EVIDENCE=10
PKCS_CONTEXT_PACK_MAX_EVIDENCE_PER_SOURCE=3
```

`data/raw/` 是 PKCS 的 Raw Archive，用于后续证据读回。不要手动编辑其中的文件。

## 测试

```bash
docker compose up -d postgres
uv run alembic upgrade head
uv run pytest
```
