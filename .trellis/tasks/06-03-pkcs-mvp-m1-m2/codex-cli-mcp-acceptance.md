# PKCS MCP 验收：Codex CLI

日期：2026-06-09
任务：`.trellis/tasks/06-03-pkcs-mvp-m1-m2`
验收 Agent：Codex CLI
状态：文档已就绪，等待人工执行；自动化 generic FastMCP fallback 已由测试覆盖。

## 目标

本文档定义 PKCS M1+M2 MVP 面向真实 Agent 的 MCP 验收路径，验收对象固定为 Codex CLI。

通过本验收意味着：Codex CLI 能发现 PKCS MCP server，调用所有 MVP MCP tools，摄入本地 fixture，检索已摄入知识，从 Raw Archive 读回原始证据，并生成带可追溯 evidence 的 Context Pack。

## 当前实现基线

PKCS 已在 `src/pkcs/mcp/server.py` 暴露以下 FastMCP tools：

* `health_check`
* `ingest_source`
* `search_knowledge`
* `read_source`
* `get_context_pack`

当前自动化 fallback 验收是 `tests/test_acceptance.py::test_codex_first_mcp_acceptance_generic_client_fallback`。它直接通过 FastMCP 调用同一条工具链路：

```text
health_check -> ingest_source -> search_knowledge -> read_source -> get_context_pack
```

尚未完成的人工验收是：证明 Codex CLI 能通过 Codex MCP 配置调用 PKCS MCP server。

## 已确认的本地事实

以下事实已在 2026-06-09 写入本文档前本地确认：

* `codex --help` 暴露 `mcp` 命令组。
* `codex mcp add --help` 支持通过 `codex mcp add <name> -- <command>...` 添加 stdio MCP server。
* `codex mcp add --help` 也支持通过 `--url` 添加 streamable HTTP MCP server。
* `codex mcp list` 当前显示未配置 MCP server。
* `uv run mcp run --help` 支持用 `server.py:object` 导入并运行 server 对象。
* `uv run python -c "from pkcs.mcp.server import mcp; print([tool.name for tool in mcp._tool_manager.list_tools()])"` 能列出全部五个 PKCS MCP tools。
* `PKCS_DATABASE_URL` 默认值是 `postgresql+psycopg://pkcs:pkcs@localhost:54329/pkcs`。
* `PKCS_RAW_ARCHIVE_PATH` 默认值是 `data/raw`。

## 前置条件

在 `Z:\personalLibrary` 运行：

```powershell
git status --short --branch
uv sync
docker compose up -d postgres
docker compose ps postgres
uv run alembic upgrade head
uv run pytest tests/test_acceptance.py
codex doctor --summary
```

前置检查应满足：

* Git 没有会干扰验收的无关 dirty files。
* PostgreSQL 状态为 healthy。
* Alembic 已迁移到 head。
* `tests/test_acceptance.py` 通过。
* Codex doctor 没有 auth 或 runtime blocking failure。

## 将 PKCS 配置为 Codex MCP Server

推荐使用 Codex `config.toml` 持久配置，因为 PKCS 需要从项目根目录启动。可以配置在用户级 `C:\Users\tantl\.codex\config.toml`，也可以配置在受信任项目级 `Z:\personalLibrary\.codex\config.toml`。

不要把 secret 写入项目配置。下面的本地数据库 URL 只适合本地 MVP 验收，提交任何配置前都要复核。

```toml
[mcp_servers.pkcs]
command = "uv"
args = ["run", "mcp", "run", "src/pkcs/mcp/server.py:mcp"]
cwd = "Z:\\personalLibrary"
startup_timeout_sec = 20
tool_timeout_sec = 120
enabled = true
required = true
enabled_tools = [
  "health_check",
  "ingest_source",
  "search_knowledge",
  "read_source",
  "get_context_pack",
]
default_tools_approval_mode = "prompt"

[mcp_servers.pkcs.env]
PKCS_DATABASE_URL = "postgresql+psycopg://pkcs:pkcs@localhost:54329/pkcs"
PKCS_RAW_ARCHIVE_PATH = "data/raw"
```

如果 Codex 总是在项目根目录启动，也可以用 CLI 添加：

```powershell
codex mcp add pkcs `
  --env PKCS_DATABASE_URL=postgresql+psycopg://pkcs:pkcs@localhost:54329/pkcs `
  --env PKCS_RAW_ARCHIVE_PATH=data/raw `
  -- uv run mcp run src/pkcs/mcp/server.py:mcp
```

如果使用 CLI 添加方式，添加后检查生成的配置；如果 Codex 可能从其他目录启动，需要手动补上 `cwd = "Z:\\personalLibrary"`。

## 交互式验收

从项目目录启动 Codex CLI：

```powershell
codex -C Z:\personalLibrary
```

在 Codex 内运行：

```text
/mcp
```

预期结果：

* `pkcs` 显示为已启用 MCP server。
* 该 server 暴露五个预期 PKCS tools。

然后要求 Codex 执行：

```text
使用 pkcs MCP server 执行 MVP 验收。

1. 调用 health_check 并报告 status。
2. 将 tests/fixtures/markdown/mcp-tools.md 作为 knowledge_type=document 摄入，canonical_key 使用 document:codex-cli-mcp-acceptance-20260609-manual。
3. 用 "toolanchor health_check ingest_source search_knowledge" 搜索，top_k=5。
4. 对第一条搜索结果调用 read_source，context_lines=1。
5. 对同一查询生成 Context Pack，top_k=5，budget_tokens=600。
6. 报告 canonical_key、chunk_id、source_id、version_id、locator，以及 Context Pack 是否包含 Conflicts / Caveats。

除非 MCP tool 调用失败，不要用 shell command 代替 ingest/search/read/context-pack。如果 tool 失败，报告具体 tool 名和错误。
```

通过标准：

* `health_check` 返回 `status: ok`。
* `ingest_source` 返回 `status: completed`；如果相同 canonical key 已摄入过，允许返回 `status: skipped`。
* `search_knowledge` 对验收查询至少返回一条结果。
* 第一条结果包含 `chunk_id`、`source_id`、`version_id`、`canonical_key`、`knowledge_type` 和 `citation.locator`。
* `read_source` 从 Raw Archive 返回内容，并包含预期 MCP tool 文本。
* `get_context_pack` 返回非空 `evidence` 和 `context_pack_markdown`。
* Markdown 中包含 `Conflicts / Caveats`。

如果因为重复 canonical key 得到 `status: skipped`，用新的 key 重跑，例如：

```text
document:codex-cli-mcp-acceptance-20260609-<HHMMSS>
```

## 非交互式验收

需要可保存 transcript 时使用：

```powershell
$RunId = "codex-cli-mcp-" + (Get-Date -Format "yyyyMMddHHmmss")
$Prompt = @"
使用 pkcs MCP server 执行 MVP 验收。

按顺序调用这些 MCP tools：health_check、ingest_source、search_knowledge、read_source、get_context_pack。

使用：
- path: tests/fixtures/markdown/mcp-tools.md
- knowledge_type: document
- canonical_key: document:$RunId
- query: toolanchor health_check ingest_source search_knowledge
- top_k: 5
- context_lines: 1
- budget_tokens: 600

返回一份简洁 Markdown 报告，包含：
- health status
- ingest status
- canonical_key
- 第一条搜索结果的 chunk_id/source_id/version_id/locator
- read_source 证据摘要
- Context Pack evidence 数量
- 是否出现 Conflicts / Caveats

除非 MCP tool 失败，不要用 shell command 代替 ingest/search/read/context-pack。
"@

codex exec -C Z:\personalLibrary --sandbox workspace-write --ask-for-approval on-request --json $Prompt
```

通过标准与交互式验收一致。如果该次运行用于审计，保留 JSONL 输出。

## 失败排查

如果 `/mcp` 里看不到 `pkcs`：

* 运行 `codex mcp list`。
* 确认配置表名是 `[mcp_servers.pkcs]`。
* 确认 `cwd = "Z:\\personalLibrary"`。
* 在项目根目录确认启动命令可运行：

```powershell
uv run mcp run src/pkcs/mcp/server.py:mcp
```

如果 `health_check` 失败：

* 运行 `codex doctor --summary`。
* 确认 `uv sync` 已完成。
* 确认 Codex 能从配置的 `cwd` 启动 stdio MCP command。

如果 ingest 或 search 失败：

* 运行 `docker compose ps postgres`。
* 运行 `uv run alembic upgrade head`。
* 运行 `uv run pkcs ingest tests/fixtures/markdown/mcp-tools.md --knowledge-type document --canonical-key document:manual-cli-check`。
* 运行 `uv run pkcs search "toolanchor health_check ingest_source search_knowledge" --top-k 5`。

如果 search 成功但 `read_source` 失败：

* 确认 `data/raw/` 存在。
* 确认搜索结果包含 `chunk_id`。
* 运行 `uv run pkcs read --chunk-id <chunk_id> --context-lines 1`。

## 验收结论规则

只有满足以下条件，才能把真实 Codex CLI MCP 验收标记为通过：

* Codex CLI 将 `pkcs` 列为已启用 MCP server。
* Codex CLI 使用 PKCS MCP tools，而不是只用 shell commands。
* 五个 MCP tools 在同一条验收线程中全部完成。
* 最终报告包含可追溯 evidence refs 和 Context Pack。

在人工执行完成前，项目状态为：

```text
M1+M2 MVP 实现：已完成
Generic MCP fallback 验收：已完成
真实 Codex CLI MCP 验收：文档已就绪，等待人工执行
```
