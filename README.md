# Personal Knowledge Context Server

PKCS 是一个本地优先的个人知识上下文服务，用来把本地文档和 AI 对话摄入 PostgreSQL，并向外部 agent 提供可追溯的搜索结果、原文证据和 Context Pack。

## 功能概览

* 摄入本地 Markdown/text 文档和 AI conversation 文件。
* 使用 PostgreSQL full-text search 检索知识片段。
* 通过 `read_source` 从 Raw Archive 读取可追溯原文证据。
* 生成 Context Pack v0，包含 JSON 结构化数据和 Markdown 摘要。
* 提供 Typer CLI、FastAPI health endpoint 和 FastMCP tools。
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

## 常用命令

摄入 Markdown 或 text 文档：

```bash
uv run pkcs ingest tests/fixtures/markdown/product-notes.md --knowledge-type document
```

摄入 AI conversation：

```bash
uv run pkcs ingest tests/fixtures/conversations/codex-session.jsonl --knowledge-type ai_conversation
```

搜索知识库：

```bash
uv run pkcs search "source evidence" --top-k 5
```

读取搜索结果对应的原文证据：

```bash
uv run pkcs read --chunk-id <chunk_id> --context-lines 2
```

生成 Context Pack：

```bash
uv run pkcs context-pack "source evidence" --top-k 10 --budget-tokens 800
```

## 支持的输入

直接摄入支持：

* `document`: `.md`, `.txt`
* `ai_conversation`: `.md`, `.txt`, `.jsonl`

目录摄入只处理当前目录层级，不递归进入子目录。

预处理摄入支持单文件：

* Markdown: `.md`, `.markdown`, `.mdx`
* Docling-backed: `.pdf`, `.docx`, `.xlsx`, `.html`, `.htm`

示例：

```bash
uv run pkcs prepare-ingest path/to/source.pdf --output-root data/private/ingest-prep --slug source
uv run pkcs ingest data/private/ingest-prep/YYYY-MM-DD-source/document.md --knowledge-type document
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

## MCP Tools

`src/pkcs/mcp/server.py` 暴露 FastMCP server object `mcp`，包含以下 tools：

* `health_check`
* `ingest_source`
* `search_knowledge`
* `read_source`
* `get_context_pack`

请在你的 MCP client 中指向该 Python module，并确保启动前已完成 `uv sync`、PostgreSQL 启动和 Alembic migration。

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
