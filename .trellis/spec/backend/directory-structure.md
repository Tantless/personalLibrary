# Directory Structure

> Backend module layout for the PKCS MVP.

---

## Scenario: Adding Backend Features

### 1. Scope / Trigger

- Trigger: Any new backend module, interface command, application service, parser, storage helper, or database access code.
- Rule: Put business logic in application modules, then call it from CLI/MCP/HTTP. Do not duplicate behavior in interface layers.

### 2. Signatures

Current layout:

```text
src/pkcs/
├── cli.py                  # Typer command wiring only
├── config.py               # Pydantic Settings
├── context_pack/
│   ├── models.py           # Context Pack response/evidence/source contracts
│   └── service.py          # Search + read_source orchestration and Markdown rendering
├── health.py               # Health application function
├── db/
│   ├── models.py           # SQLAlchemy ORM models
│   ├── repositories.py     # Repository wrappers, no hidden commits
│   └── session.py          # Engine/session factory helpers
├── http/app.py             # FastAPI wiring
├── ingest/
│   ├── models.py           # Ingest report/parser data contracts
│   ├── parsers.py          # File parsing and chunk construction
│   └── service.py          # Ingest application workflow
├── mcp/server.py           # FastMCP tool wiring
├── reader/
│   ├── locators.py         # Locator parsing and formatting
│   ├── models.py           # Source fragment response contracts
│   └── service.py          # Raw Archive backed source fragment reading
├── search/
│   ├── models.py           # Search response/result contracts
│   ├── providers.py        # SearchProvider abstraction and PostgreSQL FTS provider
│   └── service.py          # Search application workflow
└── storage/raw_archive.py  # Raw Archive filesystem writes
```

### 3. Contracts

- Interface layers (`cli.py`, `mcp/server.py`, future HTTP routes) must call application services.
- Application services own transaction orchestration, input validation, and cross-repository workflows.
- Parsers return plain data models and must not write to the database or filesystem.
- Markdown artifact-aware parsers return `ParsedChunk`, `ParsedTableArtifact`, and `ParsedImageArtifact`; they do not create ORM rows or copy image assets.
- Search providers own retrieval implementation details; interface layers and future Context Pack code call `SearchService`.
- Reader services own source/version/chunk lookup and Raw Archive line slicing; interface layers call `ReadSourceService`.
- Context Pack services own retrieval orchestration, lightweight artifact hydration, and Markdown rendering; they call `SearchService` and `ReadSourceService`, and use artifact repositories only to hydrate already-selected evidence.
- Repositories write ORM objects and call `flush()`, but callers own commits.
- Storage helpers write source bytes or copied asset bytes and return paths; they must not know database schema beyond path arguments passed in.

### 4. Validation & Error Matrix

| Change | Required check |
|--------|----------------|
| New CLI/MCP command | Add or update a test that proves it calls the shared service path |
| New parser | Add parser or ingest tests with synthetic fixtures |
| New repository method | Update `database-guidelines.md` signatures and repository/ingest tests |
| New artifact-aware ingest behavior | Assert parser/service metadata links, artifact rows, and Context Pack hydration |
| New cross-layer report field | Assert the field in service and interface tests |
| New search result field | Assert the field in service and interface tests |
| New reader result field | Assert the field in service and interface tests |
| New Context Pack field | Assert the field in service and interface tests |

### 5. Good/Base/Bad Cases

Good:

```python
report = IngestService.from_settings(settings).ingest_source(
    path=path,
    knowledge_type=knowledge_type,
    canonical_key=canonical_key,
)

response = SearchService.from_settings(settings).search_knowledge(
    query=query,
    knowledge_type=knowledge_type,
    canonical_key=canonical_key,
    top_k=top_k,
)

fragment = ReadSourceService.from_settings(settings).read_source(
    chunk_id=chunk_id,
    source_id=source_id,
    version_id=version_id,
    locator=locator,
    context_lines=context_lines,
)

pack = ContextPackService.from_settings(settings).get_context_pack(
    query=query,
    knowledge_type=knowledge_type,
    canonical_key=canonical_key,
    top_k=top_k,
    budget_tokens=budget_tokens,
)
```

Bad:

```python
# Do not parse and insert chunks directly inside CLI or MCP handlers.
@app.command()
def ingest(...):
    session.add(Chunk(...))
```

### 6. Tests Required

- Shared service behavior: `tests/test_ingest.py`.
- Search behavior: `tests/test_search.py`.
- Reader behavior: `tests/test_reader.py`.
- Context Pack behavior: `tests/test_context_pack.py`.
- Interface smoke tests: CLI and MCP tests for commands/tools that call the service.
- Data-layer changes: `tests/test_database_schema.py` and `tests/test_repositories.py`.

### 7. Wrong vs Correct

#### Wrong

Duplicating ingest logic in `cli.py` and `mcp/server.py`.

#### Correct

Keep interface layers thin and call `IngestService`, `SearchService`, `ReadSourceService`, or `ContextPackService`.
