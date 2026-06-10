# PKCS MCP Acceptance: Codex CLI

Date: 2026-06-09
Task: `.trellis/tasks/06-03-pkcs-mvp-m1-m2`
Acceptance agent: Codex CLI
Status: Ready to execute manually. Generic FastMCP fallback is already covered by automated tests.

## Purpose

This document defines the real-agent MCP acceptance path for PKCS M1+M2 MVP using Codex CLI as the acceptance agent.

Passing this acceptance means Codex CLI can discover the PKCS MCP server, call every MVP MCP tool, ingest a local fixture, search the ingested knowledge, read back Raw Archive evidence, and generate a Context Pack with traceable evidence.

## Current Implementation Baseline

PKCS already exposes these FastMCP tools from `src/pkcs/mcp/server.py`:

* `health_check`
* `ingest_source`
* `search_knowledge`
* `read_source`
* `get_context_pack`

The current automated fallback acceptance is `tests/test_acceptance.py::test_codex_first_mcp_acceptance_generic_client_fallback`. It calls the same tool flow directly through FastMCP:

```text
health_check -> ingest_source -> search_knowledge -> read_source -> get_context_pack
```

The missing manual check is proving that Codex CLI can use the PKCS MCP server through Codex's MCP configuration.

## Verified Local Facts

These facts were checked locally on 2026-06-09 before writing this document:

* `codex --help` exposes the `mcp` command group.
* `codex mcp add --help` supports stdio MCP servers through `codex mcp add <name> -- <command>...`.
* `codex mcp add --help` also supports streamable HTTP servers with `--url`.
* `codex mcp list` currently reports no configured MCP servers.
* `uv run mcp run --help` supports importing a server object with `server.py:object`.
* `uv run python -c "from pkcs.mcp.server import mcp; print([tool.name for tool in mcp._tool_manager.list_tools()])"` lists all five PKCS MCP tools.
* `PKCS_DATABASE_URL` default is `postgresql+psycopg://pkcs:pkcs@localhost:54329/pkcs`.
* `PKCS_RAW_ARCHIVE_PATH` default is `data/raw`.

## Prerequisites

Run these from `Z:\personalLibrary`:

```powershell
git status --short --branch
uv sync
docker compose up -d postgres
docker compose ps postgres
uv run alembic upgrade head
uv run pytest tests/test_acceptance.py
codex doctor --summary
```

Required preflight result:

* Git has no unrelated dirty files that could confuse the run.
* PostgreSQL is healthy.
* Alembic is at head.
* `tests/test_acceptance.py` passes.
* Codex doctor has no blocking auth or runtime issue.

## Configure PKCS As A Codex MCP Server

Recommended durable configuration is a Codex `config.toml` entry, because PKCS should start from the project root. Use either user-level `C:\Users\tantl\.codex\config.toml` or the trusted project config at `Z:\personalLibrary\.codex\config.toml`.

Do not add secrets to project config. The default local database URL below is acceptable for local MVP validation, but review it before committing any config change.

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

CLI setup alternative, usable when Codex is launched from the project root:

```powershell
codex mcp add pkcs `
  --env PKCS_DATABASE_URL=postgresql+psycopg://pkcs:pkcs@localhost:54329/pkcs `
  --env PKCS_RAW_ARCHIVE_PATH=data/raw `
  -- uv run mcp run src/pkcs/mcp/server.py:mcp
```

If the CLI setup is used, inspect the resulting config and add `cwd = "Z:\\personalLibrary"` manually if Codex may be launched from another directory.

## Interactive Acceptance

Start Codex CLI in the project:

```powershell
codex -C Z:\personalLibrary
```

Inside Codex, run:

```text
/mcp
```

Expected result:

* `pkcs` is listed as an enabled MCP server.
* The server exposes the five expected PKCS tools.

Then ask Codex:

```text
Use the pkcs MCP server to run MVP acceptance.

1. Call health_check and report the status.
2. Ingest tests/fixtures/markdown/mcp-tools.md as knowledge_type=document with canonical_key=document:codex-cli-mcp-acceptance-20260609-manual.
3. Search for "toolanchor health_check ingest_source search_knowledge" with top_k=5.
4. Read the first returned chunk with context_lines=1.
5. Build a Context Pack for the same query with top_k=5 and budget_tokens=600.
6. Report the canonical_key, chunk_id, source_id, version_id, locator, and whether the Context Pack includes Conflicts / Caveats.

Do not use shell commands for ingest/search/read/context-pack unless the MCP tool call fails. If a tool fails, report the exact tool and error.
```

Passing result:

* `health_check` returns `status: ok`.
* `ingest_source` returns `status: completed` or `status: skipped` only if the exact canonical key was already ingested.
* `search_knowledge` returns at least one result for the acceptance query.
* The first result includes `chunk_id`, `source_id`, `version_id`, `canonical_key`, `knowledge_type`, and `citation.locator`.
* `read_source` returns content from Raw Archive and includes the expected MCP tool text.
* `get_context_pack` returns non-empty `evidence` and `context_pack_markdown`.
* The Markdown contains `Conflicts / Caveats`.

If the run used a repeated canonical key and produced `status: skipped`, rerun with a fresh key such as:

```text
document:codex-cli-mcp-acceptance-20260609-<HHMMSS>
```

## Noninteractive Acceptance

Use this when a repeatable transcript is preferred:

```powershell
$RunId = "codex-cli-mcp-" + (Get-Date -Format "yyyyMMddHHmmss")
$Prompt = @"
Use the pkcs MCP server to run MVP acceptance.

Call these MCP tools in order: health_check, ingest_source, search_knowledge, read_source, get_context_pack.

Use:
- path: tests/fixtures/markdown/mcp-tools.md
- knowledge_type: document
- canonical_key: document:$RunId
- query: toolanchor health_check ingest_source search_knowledge
- top_k: 5
- context_lines: 1
- budget_tokens: 600

Return a concise Markdown report with:
- health status
- ingest status
- canonical_key
- first search result chunk_id/source_id/version_id/locator
- read_source evidence excerpt summary
- Context Pack evidence count
- whether Conflicts / Caveats appears

Do not use shell commands for ingest/search/read/context-pack unless an MCP tool fails.
"@

codex exec -C Z:\personalLibrary --sandbox workspace-write --ask-for-approval on-request --json $Prompt
```

Passing result is the same as the interactive path. Preserve the JSONL output if the run is used as an audit artifact.

## Failure Triage

If `pkcs` does not appear in `/mcp`:

* Run `codex mcp list`.
* Confirm the config table is `[mcp_servers.pkcs]`.
* Confirm `cwd = "Z:\\personalLibrary"`.
* Confirm the command works from the repo root:

```powershell
uv run mcp run src/pkcs/mcp/server.py:mcp
```

If `health_check` fails:

* Run `codex doctor --summary`.
* Confirm `uv sync` has completed.
* Confirm Codex can launch stdio MCP commands from the configured `cwd`.

If ingest or search fails:

* Run `docker compose ps postgres`.
* Run `uv run alembic upgrade head`.
* Run `uv run pkcs ingest tests/fixtures/markdown/mcp-tools.md --knowledge-type document --canonical-key document:manual-cli-check`.
* Run `uv run pkcs search "toolanchor health_check ingest_source search_knowledge" --top-k 5`.

If `read_source` fails after search succeeds:

* Confirm `data/raw/` exists.
* Confirm the search result has a `chunk_id`.
* Run `uv run pkcs read --chunk-id <chunk_id> --context-lines 1`.

## Acceptance Decision

Mark real Codex CLI MCP acceptance as passed only when:

* Codex CLI lists `pkcs` as an enabled MCP server.
* Codex CLI uses the PKCS MCP tools instead of only using shell commands.
* All five MCP tools complete in one acceptance thread.
* The final report includes traceable evidence references and a Context Pack.

Until this manual run is completed, the project status is:

```text
M1+M2 MVP implementation: complete
Generic MCP fallback acceptance: complete
Real Codex CLI MCP acceptance: documented and ready, pending manual execution
```
