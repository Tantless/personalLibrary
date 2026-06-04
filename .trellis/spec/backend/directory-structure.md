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
└── storage/raw_archive.py  # Raw Archive filesystem writes
```

### 3. Contracts

- Interface layers (`cli.py`, `mcp/server.py`, future HTTP routes) must call application services.
- Application services own transaction orchestration, input validation, and cross-repository workflows.
- Parsers return plain data models and must not write to the database or filesystem.
- Repositories write ORM objects and call `flush()`, but callers own commits.
- Storage helpers write bytes and return paths; they must not know database schema beyond path arguments passed in.

### 4. Validation & Error Matrix

| Change | Required check |
|--------|----------------|
| New CLI/MCP command | Add or update a test that proves it calls the shared service path |
| New parser | Add parser or ingest tests with synthetic fixtures |
| New repository method | Update `database-guidelines.md` signatures and repository/ingest tests |
| New cross-layer report field | Assert the field in service and interface tests |

### 5. Good/Base/Bad Cases

Good:

```python
report = IngestService.from_settings(settings).ingest_source(
    path=path,
    source_type=source_type,
    canonical_key=canonical_key,
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
- Interface smoke tests: CLI and MCP tests for commands/tools that call the service.
- Data-layer changes: `tests/test_database_schema.py` and `tests/test_repositories.py`.

### 7. Wrong vs Correct

#### Wrong

Duplicating ingest logic in `cli.py` and `mcp/server.py`.

#### Correct

Keep both interface layers thin and call `IngestService`.
