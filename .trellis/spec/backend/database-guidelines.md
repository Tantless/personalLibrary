# Database Guidelines

> Executable database contracts for the PKCS backend.

---

## Scenario: PKCS MVP Database Schema

### 1. Scope / Trigger

- Trigger: Any change to SQLAlchemy models, Alembic migrations, repository write behavior, Raw Archive database references, or PostgreSQL full-text search fields.
- Runtime: PostgreSQL from Docker Compose is the default MVP database.
- Stack: SQLAlchemy ORM models in `src/pkcs/db/models.py`, Alembic migrations in `migrations/versions/`, sessions from `src/pkcs/db/session.py`, and repository wrappers in `src/pkcs/db/repositories.py`.

### 2. Signatures

Commands:

```bash
docker compose up -d postgres
uv run alembic upgrade head
uv run pytest tests/test_database_schema.py tests/test_repositories.py
```

Configuration:

```env
PKCS_DATABASE_URL=postgresql+psycopg://pkcs:pkcs@localhost:54329/pkcs
```

Repository constructors:

```python
SourceRepository(session: Session)
ChunkRepository(session: Session)
CitationRepository(session: Session)
IngestJobRepository(session: Session)
```

Required write methods:

```python
SourceRepository.get(source_id)
SourceRepository.get_by_canonical_key(canonical_key)
SourceRepository.get_version_by_hash(source_id, content_hash)
SourceRepository.get_version(source_id, version_id)
SourceRepository.create_source(canonical_key, title, source_type, origin_uri=None)
SourceRepository.create_version(source, content_hash, file_path, raw_archive_path, version_id=None, status="imported", metadata_json=None)
ChunkRepository.create_chunk(source_id, version_id, chunk_index, title, source_type, locator, line_start, line_end, content, ...)
ChunkRepository.get(chunk_id)
ChunkRepository.get_by_locator(source_id, version_id, locator)
CitationRepository.create_citation(source_id, version_id, chunk_id, locator, line_start, line_end, quote=None, metadata_json=None)
IngestJobRepository.create_job(source_type, input_path, status="started", summary_json=None)
IngestJobRepository.finish_job(job, status, summary_json, error_message=None)
```

Search signatures:

```python
SearchProvider.search(query, top_k, source_type=None, canonical_key=None)
PostgresFTSSearchProvider.from_database_url(database_url)
SearchService.search_knowledge(query, source_type=None, canonical_key=None, top_k=None)
```

Reader signatures:

```python
parse_line_locator(locator) -> tuple[int, int]
format_line_locator(line_start, line_end) -> str
ReadSourceService.read_source(chunk_id=None, source_id=None, version_id=None, locator=None, context_lines=0)
```

### 3. Contracts

Core tables:

- `sources`: one stable source identity per `canonical_key`; `source_type` is indexed; `current_version_id` points at the latest imported version.
- `source_versions`: immutable source versions; `(source_id, content_hash)` and `(source_id, version_number)` are unique; `raw_archive_path` must point to the archived raw file.
- `chunks`: searchable evidence units; `(version_id, chunk_index)` is unique; locator fields use `locator`, `line_start`, and `line_end`.
- `citations`: source/version/chunk-linked evidence references for future `read_source` and Context Pack output.
- `ingest_jobs`: MVP audit surface for ingest status and per-run summaries.

Read source:

- The only MVP locator format is `line N-M`.
- `read_source(chunk_id=...)` resolves source/version/locator through `chunks`.
- `read_source(source_id=..., version_id=..., locator=...)` parses the locator and reads the matching line range even if no exact chunk row exists.
- Source text must be read from `source_versions.raw_archive_path`, not from the current original file path.
- `context_lines` may expand the returned line range but must not make whole-source reads the default.

Full-text search:

- `chunks.search_vector` is a PostgreSQL generated column.
- Application code must not write `search_vector`.
- PostgreSQL FTS search must read `chunks.search_vector` and use `websearch_to_tsquery('simple', query)`.
- Search ranking is `ts_rank_cd(chunks.search_vector, query)` plus an explicit title match boost.
- Optional `source_type` and `canonical_key` filters must be SQL parameters and cast nullable params to text.
- The expression uses PostgreSQL `simple` configuration and title boost:

```sql
setweight(to_tsvector('simple', coalesce(title, '')), 'A') ||
setweight(to_tsvector('simple', coalesce(content, '')), 'B')
```

Indexes:

- `ix_chunks_search_vector` must be a GIN index.
- Keep indexes for `source_type`, `source_id`, `version_id`, `content_hash`, and ingest `status` when changing schema.

Transaction boundary:

- Repositories call `session.flush()` to materialize IDs and constraints.
- Callers own `commit()` and `rollback()`.
- Do not hide transaction commits inside repositories.
- Ingest may pass a pre-generated `version_id` to `create_version()` so Raw Archive paths can include `source_id/version_id` before the database row is inserted.

### 4. Validation & Error Matrix

| Case | Expected behavior | Required assertion |
|------|-------------------|--------------------|
| PostgreSQL unavailable | Integration tests skip with a clear pytest skip reason | `tests/conftest.py` connectivity gate |
| Duplicate `sources.canonical_key` | Database rejects the duplicate | Unique constraint remains present |
| Duplicate `(source_id, content_hash)` | Database rejects duplicate source version content | `uq_source_versions_source_hash` remains present |
| Duplicate `(version_id, chunk_index)` | Database rejects duplicate chunk order | `uq_chunks_version_chunk_index` remains present |
| Insert chunk without `search_vector` | Database generates `search_vector` | `test_chunks_search_vector_is_database_generated` |
| Repository create methods called | IDs are available after method returns | Repository tests assert persisted rows |
| Duplicate ingest for same canonical source and content hash | Application skips new version creation | Ingest tests assert the existing version id is returned |
| Changed content for same canonical source | Application creates a new source version and preserves old version | Ingest tests assert two versions for one source |
| Optional search filters are omitted | Query still executes without PostgreSQL ambiguous parameter errors | Search tests call without filters |
| Title and body both match | Title match sorts ahead when scores are otherwise close | `test_search_top_k_and_title_boost` |
| Read by `chunk_id` | Returns source/version refs and fragment content for that chunk locator | Reader tests map search result chunk id back to source |
| Read by source/version/locator | Returns the requested line range plus optional context | Reader tests use `line 4-4` with `context_lines=1` |
| Invalid locator | Raises reader input error | Reader tests assert invalid locator failure |

### 5. Good/Base/Bad Cases

Good:

```python
source = SourceRepository(session).create_source(
    canonical_key="markdown_doc:C:/notes/example.md",
    title="example.md",
    source_type="markdown_doc",
)
version = SourceRepository(session).create_version(
    source=source,
    content_hash="sha256hex",
    file_path="C:/notes/example.md",
    raw_archive_path="data/raw/markdown_doc/source/version/example.md",
)
session.commit()
```

Base:

- Run `uv run alembic upgrade head` before database integration tests.
- Use repositories for application writes; use direct SQL only in schema-focused tests.

Bad:

```python
chunk.search_vector = "manually generated value"
session.commit()
```

### 6. Tests Required

- `tests/test_database_schema.py`: table presence, required indexes, generated `search_vector`.
- `tests/test_repositories.py`: repository write/read behavior and caller-owned commit.
- `tests/test_raw_archive.py`: raw archive path layout that `source_versions.raw_archive_path` stores.
- `tests/test_ingest.py`: duplicate hash skip, new hash versioning, chunks/citations, and ingest job summaries.
- `tests/test_search.py`: PostgreSQL FTS query, title boost, filters, top_k, no-results, and interface smoke tests.
- `tests/test_reader.py`: `chunk_id`, source/version/locator, `context_lines`, invalid locator, CLI, and MCP.
- Full PR-sized database changes must run `uv run pytest` with Docker PostgreSQL healthy.

### 7. Wrong vs Correct

#### Wrong

```python
def create_chunk(...):
    chunk = Chunk(..., search_vector=make_vector(content))
    session.add(chunk)
    session.commit()
```

#### Correct

```python
def create_chunk(...):
    chunk = Chunk(...)
    session.add(chunk)
    session.flush()
    return chunk
```

The database owns FTS generation and the caller owns transaction completion.

Search must read the generated column:

```sql
where c.search_vector @@ websearch_to_tsquery('simple', :query)
```

Do not recalculate or overwrite `chunks.search_vector` in Python.

Reader must use Raw Archive:

```python
path = Path(source_version.raw_archive_path)
lines = path.read_text(encoding="utf-8-sig").splitlines()
```

Do not read from `source_versions.file_path` for evidence recovery because the original file may have moved or changed after ingest.

---

## Common Mistakes

- Treating `content_hash` as source identity. It is version identity; `canonical_key` is the stable source identity.
- Adding a model field without adding an Alembic migration and a schema assertion.
- Committing inside repository methods, which makes multi-table ingest rollback unsafe.
- Writing optional PostgreSQL filter clauses as `:source_type is null`; cast nullable params with `cast(:source_type as text)` so PostgreSQL can infer the type.
- Reading current source files instead of Raw Archive in `read_source`; this breaks version traceability.
