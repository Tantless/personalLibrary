# Quality Guidelines

> Backend quality rules for PKCS MVP implementation.

---

## Scenario: Local Knowledge Backend Changes

### 1. Scope / Trigger

- Trigger: Any backend code change in `src/pkcs/`, migrations, fixtures, or tests.
- Core requirement: Keep PR-sized changes narrow and verifiable; do not add future MVP features early.

### 2. Signatures

Required verification for backend PR-sized work:

```bash
docker compose ps postgres
uv run alembic upgrade head
uv run pytest
git diff --check
```

### 3. Contracts

- Use synthetic or non-private fixtures under `tests/fixtures/`.
- Do not ingest real personal data during tests.
- Keep interface layers thin; CLI/MCP/HTTP should call shared services.
- Do not introduce LangChain, LlamaIndex, Haystack, pgvector, OpenSearch, or rerankers in MVP PRs unless the PRD changes.
- Do not write `chunks.search_vector` from application code.
- Keep local-only behavior: no URL crawling, raw content upload, remote exposure, auth, or UI in MVP PRs.

### 4. Validation & Error Matrix

| Change | Required verification |
|--------|-----------------------|
| Parser behavior | Synthetic fixture tests |
| Database writes | Docker-backed integration test |
| PostgreSQL FTS search | Docker-backed search integration test |
| Raw Archive source reading | Docker-backed reader integration test |
| Context Pack generation | Docker-backed Context Pack integration test |
| Eval corpus or retrieval threshold | Docker-backed acceptance test using synthetic fixtures |
| M3 eval schema or baseline report helper | `tests/test_m3_eval.py` plus non-private fixture rows |
| CLI/MCP command | Interface smoke test |
| Config key | `.env.example` update |
| New code-spec convention | Update relevant `.trellis/spec/backend/*.md` |

### 5. Good/Base/Bad Cases

Good:

```python
body = json.loads(result.stdout)
assert body["status"] == "completed"
```

Bad:

```python
# Do not assert only that the command exits; assert the stable report shape.
assert result.exit_code == 0
```

### 6. Tests Required

- Full suite: `uv run pytest`.
- For database PRs: PostgreSQL must be healthy and Alembic must be at head.
- For PR3 ingest: tests must cover file ingest, directory ingest, duplicate skip, new version creation, parser metadata, CLI, and MCP.
- For PR4 search: tests must cover result shape, `knowledge_type` filter, `canonical_key` filter, `top_k`, title boost, no-results behavior, CLI, and MCP.
- For PR5 reader: tests must cover `chunk_id`, source/version/locator addressing, `context_lines`, invalid locator/missing refs, CLI, and MCP.
- For PR6 Context Pack: tests must cover outer JSON shape, evidence caps, per-source limit, `budget_tokens`, Caveats, `read_source` mapping, CLI, and MCP.
- For PR7 acceptance: tests must ingest at least 10 Markdown/text fixtures and 10 AI conversation fixtures, validate `tests/fixtures/eval_queries.jsonl`, require top 10 >= 80% and top 5 >= 60%, cover CLI ingest/search/read/context-pack, and cover MCP health/ingest/search/read/context-pack via Codex or generic MCP client fallback.

### 7. Wrong vs Correct

#### Wrong

Adding search ranking or Context Pack behavior during the ingest PR.

#### Correct

Store searchable chunks and citations now; implement ranking and Context Pack in their own PRs.

For PR4, do not add `read_source` or Context Pack behavior; only return refs that those later PRs can consume.

For PR5, do not add Context Pack behavior; return source fragments that PR6 can consume.

For PR6, do not add PR7 eval corpus or MCP client acceptance; keep it to Context Pack behavior.

For PR7, keep changes to synthetic fixtures, acceptance tests, docs, and specs unless a defect in earlier MVP behavior is exposed.

For M3 eval baseline work, keep report calculation separate from retrieval changes. Add query/report schema tests first, then compare later QueryRouter or fusion PRs against the baseline instead of changing ranking and metrics in the same PR.

For M3C eval schema work, keep v1 fixture rows backward-compatible and validate v2 diagnostic metadata in `tests/test_m3_eval.py` without adding expanded diagnostic queries or changing retrieval behavior in the same PR.

For M3C comparison report work, use fake service tests for summary math, pass diagnostics, failure classes, noisy result counts, source concentration counts, and JSON writing. Do not change `SearchService`, `PlannedSearchService`, planner rules, or Context Pack selection in the comparison-report PR.

For future multilingual retrieval changes, first create or run an M3 comparison report that includes locked regression rows and diagnostic rows. Translation, embedding, semantic, pgvector, OpenSearch, or reranker work must document quality delta, locked-regression preservation, must-not/noise impact, latency or cost, privacy behavior, reindex path, and rollback before becoming a retained dependency or default path.
