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
SourceRepository.get_by_canonical_key(canonical_key)
SourceRepository.get_version_by_hash(source_id, content_hash)
SourceRepository.create_source(canonical_key, title, source_type, origin_uri=None)
SourceRepository.create_version(source, content_hash, file_path, raw_archive_path, version_id=None, status="imported", metadata_json=None)
ChunkRepository.create_chunk(source_id, version_id, chunk_index, title, source_type, locator, line_start, line_end, content, ...)
CitationRepository.create_citation(source_id, version_id, chunk_id, locator, line_start, line_end, quote=None, metadata_json=None)
IngestJobRepository.create_job(source_type, input_path, status="started", summary_json=None)
IngestJobRepository.finish_job(job, status, summary_json, error_message=None)
```

### 3. Contracts

Core tables:

- `sources`: one stable source identity per `canonical_key`; `source_type` is indexed; `current_version_id` points at the latest imported version.
- `source_versions`: immutable source versions; `(source_id, content_hash)` and `(source_id, version_number)` are unique; `raw_archive_path` must point to the archived raw file.
- `chunks`: searchable evidence units; `(version_id, chunk_index)` is unique; locator fields use `locator`, `line_start`, and `line_end`.
- `citations`: source/version/chunk-linked evidence references for future `read_source` and Context Pack output.
- `ingest_jobs`: MVP audit surface for ingest status and per-run summaries.

Full-text search:

- `chunks.search_vector` is a PostgreSQL generated column.
- Application code must not write `search_vector`.
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

---

## Common Mistakes

- Treating `content_hash` as source identity. It is version identity; `canonical_key` is the stable source identity.
- Adding a model field without adding an Alembic migration and a schema assertion.
- Committing inside repository methods, which makes multi-table ingest rollback unsafe.
