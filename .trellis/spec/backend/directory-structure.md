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
├── eval/
│   ├── models.py           # Eval query and report contracts
│   └── m3_baseline.py      # M3 search + Context Pack baseline orchestration
├── http/app.py             # FastAPI wiring
├── ingest/
│   ├── models.py           # Ingest report/parser data contracts
│   ├── parsers.py          # File parsing and chunk construction
│   ├── image_enrichment.py # Optional image-enrichment sidecar schema/validation
│   └── service.py          # Ingest application workflow
├── mcp/server.py           # FastMCP tool wiring
├── reader/
│   ├── locators.py         # Locator parsing and formatting
│   ├── models.py           # Source fragment response contracts
│   └── service.py          # Raw Archive backed source fragment reading
├── search/
│   ├── models.py           # Search response/result contracts
│   ├── planned.py          # Planned multi-pass search and fusion orchestration
│   ├── planning.py         # RetrievalPlan contracts and deterministic query planning
│   ├── providers.py        # SearchProvider abstraction and PostgreSQL FTS provider
│   └── service.py          # Search application workflow
└── storage/raw_archive.py  # Raw Archive filesystem writes
```

### 3. Contracts

- Interface layers (`cli.py`, `mcp/server.py`, future HTTP routes) must call application services.
- Application services own transaction orchestration, input validation, and cross-repository workflows.
- Parsers return plain data models and must not write to the database or filesystem.
- Markdown artifact-aware parsers return `ParsedChunk`, `ParsedTableArtifact`, `ParsedImageArtifact`, and an optional transient `ParsedMarkdownBlockGraph`; they do not create ORM rows or copy image assets.
- Image enrichment sidecar loading belongs in `src/pkcs/ingest/image_enrichment.py` and `IngestService`; parsers may consume already-validated enrichment entries but must not read `image-enrichment.json` from disk.
- `ParsedMarkdownBlockGraph` is an ingest/chunk-planning debug contract only. It may be exposed by `trace-ingest`, but it must not create a `source_blocks` table, repository, search API, or read API without a separate PRD.
- Search providers own retrieval implementation details; interface layers and future Context Pack code call `SearchService`.
- PostgreSQL FTS search includes `sources.title` alongside chunk title/content so source-alias queries can recover chunks whose local chunk headings omit the source title.
- Reader services own source/version/chunk lookup and Raw Archive line slicing; interface layers call `ReadSourceService`.
- Context Pack services own retrieval orchestration, lightweight artifact hydration, and Markdown rendering; they call `SearchService` and `ReadSourceService`, and use artifact repositories only to hydrate already-selected evidence.
- Eval modules own local query-set parsing and quality report calculation. They call `SearchService` and `ContextPackService` instead of duplicating retrieval or evidence assembly logic.
- Eval fixtures committed under `tests/fixtures/` must be synthetic or public-reference metadata only. Private corpus source files and local baseline run outputs stay under gitignored `data/private/`.
- Retrieval planning belongs in `src/pkcs/search/planning.py`. It converts a user query into a `RetrievalPlan` with named passes, intent, fusion method, and debug metadata; it must not execute search SQL or read/write database rows.
- Deterministic query planning may use reusable entity extraction, glossary terms, and source aliases, but must not map whole eval questions directly to source-specific queries.
- Planned retrieval belongs in `src/pkcs/search/planned.py`. It runs each `RetrievalPass` through the shared `SearchProvider`, fuses chunk results with `reciprocal_rank_v1`, deduplicates by `chunk_id`, and adds `planned_retrieval` metadata with fused rank, fused score, and pass hits.
- Source alias discovery belongs behind `SourceAliasProvider`; the PostgreSQL implementation reads `sources.canonical_key` and `sources.title` only and must not write database rows.
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
| New retrieval planning pass or plan field | Assert pass names, query strings, intent fallback, and serialized shape in `tests/test_search_planning.py` |
| New planned search fusion behavior | Assert source-title matching, pass runs, fused result metadata, and pass-error continuation in `tests/test_planned_search.py` |
| New reader result field | Assert the field in service and interface tests |
| New Context Pack field | Assert the field in service and interface tests |
| New eval row/report field | Assert loader validation and report shape in `tests/test_m3_eval.py` |

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

planned = PlannedSearchService.from_settings(settings).search_knowledge(
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

queries = load_m3_eval_queries(Path("tests/fixtures/m3_eval_queries.jsonl"))
report = M3BaselineEvaluator.from_settings().evaluate(queries)

plan = QueryPlanner(source_aliases=source_aliases).plan(query)
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
- Retrieval planning behavior: `tests/test_search_planning.py`.
- Planned search and fusion behavior: `tests/test_planned_search.py`.
- Reader behavior: `tests/test_reader.py`.
- Context Pack behavior: `tests/test_context_pack.py`.
- Eval schema and report behavior: `tests/test_m3_eval.py`.
- Interface smoke tests: CLI and MCP tests for commands/tools that call the service.
- Data-layer changes: `tests/test_database_schema.py` and `tests/test_repositories.py`.

### 7. Wrong vs Correct

#### Wrong

Duplicating ingest logic in `cli.py` and `mcp/server.py`.

#### Correct

Keep interface layers thin and call `IngestService`, `SearchService`, `ReadSourceService`, or `ContextPackService`.
