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
# Temporary PKCS Planning Context

This block is temporary planning memory for the PRD clarification phase. The user said they will manually delete it after the PRD clarification stage ends.

## Current Planning Task

* Task: `.trellis/tasks/06-03-pkcs-project-plan`
* PRD: `.trellis/tasks/06-03-pkcs-project-plan/prd.md`
* Source design document: `personal_knowledge_context_server_design.md`
* User intent: read the design document, organize the full project roadmap, clarify PRDs phase by phase, and make sure both user and agent share explicit definitions for how the project starts, proceeds, is accepted, and is considered complete.

## PKCS Project Summary

Personal Knowledge Context Server (PKCS) is a personal knowledge backend service for external agents such as Claude Code, Codex, OpenClaw, IDE agents, local agents, scripts, and future custom workflows.

The service is not a chat UI and does not replace the main agent. It provides searchable, traceable, compressed context materials. Its core output is a Context Pack that the main agent can inject into its own working context.

## Working Principles During Clarification

* Use `$brainstorm` behavior: task-first, action-before-asking, one high-value question at a time.
* Update the PRD immediately after each confirmed decision.
* Keep MVP scope small and avoid speculative features.
* Prefer stable external tool interfaces before optimizing internal retrieval implementation.
* Preserve raw source evidence and citation traceability as a non-negotiable project principle.

## Current Roadmap Draft

* M1: 接入骨架与数据底座 - Agent can call the service, raw data is archived, metadata is stored, and original evidence can be read back.
* M2: 摄入与基础检索 MVP - selected source types can be ingested, chunked, indexed, searched, and cited.
* M3: 检索编排与 Context Pack - query routing, multi-retriever fusion, reranking, and context pack generation.
* M4: 特色知识源增强 - code, AI conversations, email, entities, official docs, and work knowledge get specialized retrieval.
* M5: 知识沉淀、安全、评测与运维 - LLM Wiki, decisions, belief history, permissions, anti-pollution controls, evals, backup, and recovery.

## Open Decisions

* MVP interface shape: MCP-only, HTTP-only, or MCP + HTTP.
* MVP source types: AI conversations + Markdown only, or also GitHub repo ingest v0.
* MVP search backend: lightweight local search first, PostgreSQL FTS/pgvector, or PostgreSQL + OpenSearch.
* Context Pack v0 format: JSON, Markdown, or JSON + Markdown hybrid.

<!-- PKCS-PLANNING:TEMP-END -->
