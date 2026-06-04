# Logging Guidelines

> Logging contracts for the local-first PKCS backend.

---

## Scenario: Ingest Event Logging

### 1. Scope / Trigger

- Trigger: Changes to ingest, search, read_source, context_pack, or failure-path logging.
- MVP privacy rule: Logs may include IDs, paths, status, counts, and short error summaries. Logs must not include full source content, chunks, quotes, secrets, or raw private text.

### 2. Signatures

Logger usage:

```python
logger = logging.getLogger(__name__)
logger.info("ingest_file_succeeded", extra={"event": "ingest_file_succeeded", ...})
logger.exception("ingest_file_failed", extra={"event": "ingest_file_failed", ...})
```

Current ingest events:

```text
ingest_file_succeeded
ingest_file_skipped
ingest_file_failed
```

### 3. Contracts

- Include `event` in `extra` for machine-readable logs.
- Include stable references when available: `source_id`, `version_id`, `source_type`, `chunks_created`.
- For failures, include path and source_type, but not content.
- `ingest_jobs.summary_json` is the durable MVP audit surface; logs are operational traces.

### 4. Validation & Error Matrix

| Logged field | Allowed? | Reason |
|--------------|----------|--------|
| `source_id`, `version_id` | Yes | Stable non-content refs |
| `canonical_key` | Use care | May contain local paths; prefer DB report over logs |
| Local path | Yes for local MVP, but no content | Needed to debug ingest |
| Chunk content or quote | No | Private source material |
| Secret/env values | No | Credential leak risk |

### 5. Good/Base/Bad Cases

Good:

```python
logger.info(
    "ingest_file_succeeded",
    extra={"event": "ingest_file_succeeded", "source_id": source_id, "chunks_created": chunks_created},
)
```

Bad:

```python
logger.info("ingested content", extra={"content": parsed_chunk.content})
```

### 6. Tests Required

- Behavior is primarily verified through `ingest_jobs.summary_json` in integration tests.
- If log formatting becomes part of runtime configuration, add a focused logging formatter test.

### 7. Wrong vs Correct

#### Wrong

Using logs as the only ingest audit record.

#### Correct

Persist ingest outcome in `ingest_jobs`, and use logs for event traces.
