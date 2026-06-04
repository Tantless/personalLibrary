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
# Temporary PKCS MVP Context

This temporary block preserves only the confirmed MVP planning state. The detailed decisions live in:

* Parent planning PRD: `.trellis/tasks/06-03-pkcs-project-plan/prd.md`
* Confirmed MVP PRD: `.trellis/tasks/06-03-pkcs-mvp-m1-m2/prd.md`
* Source design doc: `personal_knowledge_context_server_design.md`

## Current State

* MVP PRD confirmed by user on 2026-06-04.
* No open MVP decisions remain.
* PR1, PR2, PR3, PR4, PR5, PR6, and PR7 have been implemented and verified locally.
* PR7 covers synthetic fixture corpus, eval queries, retrieval thresholds, docs, and MCP smoke acceptance.
* After the PR7 commit, the M1+M2 MVP implementation PRD should be considered complete locally.
* Post-MVP database usability update: PostgreSQL table and column Chinese comments are added through Alembic revision `20260604_0002`.
* M3-M5 planning remains future work.

## Workflow Rule

After each complete PR-sized step is implemented and verified, inspect the working tree. If the changed content is coherent and committable, commit it immediately with a focused commit message before starting the next PR-sized step.

## MVP Scope

PKCS MVP combines M1 + M2: agent access, Raw Archive, PostgreSQL metadata, AI conversation and Markdown/text ingest, PostgreSQL FTS search, `read_source`, and Context Pack v0.

Core stack:

* Python + uv
* FastAPI for local HTTP
* Official MCP Python SDK with `FastMCP`
* Typer CLI
* Docker Compose PostgreSQL
* SQLAlchemy + Alembic
* Pydantic Settings
* pytest + pytest-asyncio

Core constraints:

* Source types: `ai_conversation`, `markdown_doc`
* Input: local file paths only; single file or non-recursive directory
* AI conversation formats: Markdown/transcript and JSONL
* Document formats: local `.md` and `.txt` only
* Raw Archive: project-local `data/raw/`, gitignored
* Search: PostgreSQL FTS with `simple`, database-generated `search_vector`, FTS GIN index, FTS rank + title boost
* Filters: `source_type`, `canonical_key`, `top_k`
* Context Pack: JSON + Markdown, max 10 evidence, max 3 per source, soft `budget_tokens`, includes `Conflicts / Caveats`
* Evidence must always map to `source_id`, `version_id`, and locator; `read_source` supports `chunk_id` and full source/version/locator addressing
* Search: `SearchProvider` abstraction, PostgreSQL FTS provider, `search_knowledge`, title boost, `source_type`/`canonical_key`/`top_k` filters, stable evidence result shape
* Read source: `ReadSourceService`, Raw Archive backed reads, `line N-M` locators, `chunk_id` and source/version/locator addressing, optional `context_lines`
* Context Pack: `ContextPackService`, search + read_source orchestration, chunk deduplication, evidence caps, per-source cap, JSON + Markdown response, soft `budget_tokens`, Caveats

Out of MVP scope:

* Code repo ingest or code chunking
* Email ingest
* LangChain/LlamaIndex/Haystack as core dependencies
* pgvector, OpenSearch, reranker, GraphRAG
* HTML/PDF/docx parsing, URL crawling, raw content upload
* Remote exposure, auth, audit log table
* Backup/restore/reindex commands
* UI, full LLM Wiki, autonomous multi-agent workflow

## Execution Plan

* PR1: scaffold, uv config, Docker Compose PostgreSQL, FastAPI health, FastMCP skeleton, Typer CLI skeleton - completed
* PR2: Alembic schema, required indexes, FTS GIN index, Raw Archive writer, source/version/chunk/citation repositories - completed
* PR3: AI conversation and Markdown/text ingest, structure-first chunking, duplicate/new-version behavior, ingest report - completed
* PR4: PostgreSQL FTS SearchProvider, title boost, filters, search result shape - completed
* PR5: `read_source` by `chunk_id` and source/version/locator, with optional `context_lines` - completed
* PR6: Context Pack v0 JSON + Markdown, evidence caps, Caveats, soft `budget_tokens` - completed
* PR7: synthetic fixtures, `eval_queries.jsonl`, retrieval thresholds, docs, Codex-first MCP smoke test with generic MCP fallback - completed

## Acceptance Summary

MVP is complete only when:

* Unit tests and Docker-backed integration tests pass.
* At least 10 synthetic/non-private AI conversation samples and 10 Markdown/text samples ingest successfully.
* At least 20 eval queries reach top 10 >= 80% and top 5 >= 60%.
* CLI, FastAPI health, MCP health, and Codex-first MCP smoke test pass.
* Every search result and Context Pack evidence maps back to `read_source`.
* Docs cover setup, config, ingest, search, `read_source`, Context Pack, testing, and limitations.

## PR7 Acceptance Shape

* Fixture corpus lives under `tests/fixtures/markdown/` and `tests/fixtures/conversations/`.
* `tests/fixtures/eval_queries.jsonl` contains at least 20 query expectations with `query`, `expected_fixture`, `expected_canonical_keys`, `expected_source_types`, and `notes`.
* PR7 tests use runtime-unique canonical keys to avoid persistent Docker database collisions.
* Generic MCP fallback proves `health_check -> ingest_source -> search_knowledge -> read_source -> get_context_pack`.

<!-- PKCS-PLANNING:TEMP-END -->
