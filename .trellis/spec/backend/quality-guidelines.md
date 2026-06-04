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
- For PR4 search: tests must cover result shape, `source_type` filter, `canonical_key` filter, `top_k`, title boost, no-results behavior, CLI, and MCP.
- For PR5 reader: tests must cover `chunk_id`, source/version/locator addressing, `context_lines`, invalid locator/missing refs, CLI, and MCP.

### 7. Wrong vs Correct

#### Wrong

Adding search ranking or Context Pack behavior during the ingest PR.

#### Correct

Store searchable chunks and citations now; implement ranking and Context Pack in their own PRs.

For PR4, do not add `read_source` or Context Pack behavior; only return refs that those later PRs can consume.

For PR5, do not add Context Pack behavior; return source fragments that PR6 can consume.
