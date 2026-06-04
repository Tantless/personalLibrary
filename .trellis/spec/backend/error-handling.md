# Error Handling

> Error contracts for backend application services.

---

## Scenario: Ingest Errors

### 1. Scope / Trigger

- Trigger: Changes to ingest input validation, parser failures, batch behavior, or interface error handling.
- Principle: Single-file failures and directory item failures must be visible in the ingest report; directory item failures must not stop the rest of the batch.

### 2. Signatures

Error classes:

```python
IngestInputError(ValueError)
IngestParseError(ValueError)
SearchInputError(ValueError)
```

Report fields:

```python
IngestReport.status                 # completed, skipped, completed_with_errors, failed
IngestReport.succeeded              # list[IngestItemReport]
IngestReport.skipped                # list[IngestItemReport]
IngestReport.failed                 # list[IngestItemReport]
IngestItemReport.error              # short reason, no source content
```

### 3. Contracts

- `IngestInputError` covers invalid local path usage, unsupported source types, unsupported extensions, URLs, and ambiguous directory canonical keys.
- `IngestParseError` covers invalid UTF-8, invalid JSONL, empty documents, and parser output with no chunks.
- `ingest_source()` creates an `ingest_jobs` row before validating the input path existence so failed local path attempts are recorded.
- Directory ingest catches per-file exceptions, rolls back that file, records a failed item, and continues.
- Interface layers should return the report shape rather than hiding item failures.

Search behavior:

- `SearchInputError` covers empty query, unsupported `source_type`, and invalid `top_k`.
- Search with no matches returns a valid response with `results: []`; it is not an error.
- Interface layers should return the stable search response shape for zero and nonzero results.

### 4. Validation & Error Matrix

| Case | Expected behavior |
|------|-------------------|
| Missing path | Report status `failed`, one failed item |
| URL-like path | Raise `IngestInputError` before filesystem access |
| Unsupported single-file extension | Report status `failed`, one failed item |
| Unsupported file inside directory | Report status `skipped` or `completed_with_errors`, skipped item |
| Invalid UTF-8 file inside directory | Failed item, remaining files still ingest |
| Duplicate content hash | Report status `skipped`, no new chunks |
| Empty search query | `SearchInputError` |
| Unsupported search `source_type` | `SearchInputError` |
| Search no results | Valid response with empty `results` |

### 5. Good/Base/Bad Cases

Good:

```python
try:
    item = service._ingest_file(...)
    session.commit()
except Exception as exc:
    session.rollback()
    failed.append(IngestItemReport(status="failed", error=str(exc)))
```

Bad:

```python
for file_path in files:
    service._ingest_file(file_path)  # one exception aborts the whole directory
```

### 6. Tests Required

- `tests/test_ingest.py::test_ingest_directory_is_non_recursive_and_continues_after_file_failure`
- `tests/test_search.py::test_search_no_results_returns_empty_list`
- Add a test whenever a new error status or input validation branch is introduced.

### 7. Wrong vs Correct

#### Wrong

Logging or returning full source content in an error message.

#### Correct

Return file path, status, and a short reason only.
