# PKCS M3 baseline corpus ingestion result

## Result

Status: completed on 2026-06-18.

This task ingested the 100-document M3 baseline corpus into the local PKCS database after clearing previous local test data from `data/private/`, `data/raw/`, and the local PostgreSQL schema.

Private artifacts and detailed machine-readable reports are under:

```text
data/private/m3-baseline/reports/
```

These files are intentionally not committed.

## Stage Summary

### Environment reset

* Docker/PostgreSQL was started.
* `data/private/` and `data/raw/` were cleared.
* The local `pkcs` PostgreSQL schema was reset and Alembic migrations were reapplied.
* Final health check used `.venv\Scripts\pkcs.exe health` and returned `ok`.

### Source download and replacement

* 100 source rows were attempted.
* Initial direct download completed 74/100.
* Retry and replacement work brought final local source availability to 100/100.
* Several source rows in `selected-sources.jsonl` were corrected or replaced because the original URL was blocked, moved, or unstable.

### Prepare inputs

Final prepare input mix:

| Input kind | Count |
|---|---:|
| Original downloaded file | 42 |
| HTML converted to Markdown snapshot with pandoc | 43 |
| PDF converted to plain Markdown snapshot with pdftotext | 13 |
| DOCX converted to Markdown snapshot with pandoc | 1 |
| Non-UTF-8 Markdown sanitized to UTF-8 | 1 |

Final prepare extension mix:

| Extension | Count |
|---|---:|
| `.md` | 85 |
| `.pdf` | 10 |
| `.docx` | 5 |

### prepare-ingest

* Total: 100
* `success`: 72
* `soft_fail`: 28
* Failed: 0

The 28 `soft_fail` cases were accepted as degraded ingestion because they were missing local image references from GitHub/HTML-derived Markdown. Text evidence was still preserved.

### ingest

Current Codex environment did not expose a callable external PKCS MCP tool, so ingestion used the project-equivalent CLI path:

```powershell
.venv\Scripts\pkcs.exe ingest <document.md> --knowledge-type document --canonical-key <canonical_key>
```

This uses the same project ingestion service as the MCP `ingest_source` tool, but it is not a literal external MCP call.

* Total: 100
* Completed: 100
* Failed: 0
* Duplicate skipped: 0

### Database counts

```text
sources,versions,chunks,citations,image_artifacts,table_artifacts
100,100,4940,4940,1087,67
```

### Validation

10 cross-domain samples were validated with:

* `search`
* `read`
* `context-pack`

Final sample validation failures: 0.

Validated samples covered:

* OpenAI Agents SDK Markdown
* OpenAI GPT-5 system card
* 3GPP AIML DOCX-derived source
* Unreal Lumen documentation
* SIGGRAPH Lumen PDF-derived source
* Bevy README
* LinkTo-Anime paper
* Crunchyroll interview fallback source
* AJA anime data page
* Danbooru dataset README

## Known Degradation

* 43 HTML documents were converted to Markdown snapshots with `pandoc`; JavaScript layout, interactive UI, and some media were not preserved.
* 13 large/problematic PDFs were converted with `pdftotext`; layout, images, and tables are degraded.
* 28 sources had missing local image warnings; image artifacts from these missing references are not preserved.
* No `image-enrichment.json` was generated in this task.
* Ingestion used CLI-equivalent service path instead of literal external MCP tool invocation due current tool availability.

## Failure Review

The task took too long and initially failed to complete for engineering-process reasons:

1. The source manifest was selected but not fully download-validated before ingestion.
2. Several sources were blocked by Cloudflare/anti-bot protection, moved, or used unstable direct URLs.
3. Modern HTML pages did not work reliably through Docling; converting them to Markdown snapshots was more stable.
4. Docling PDF conversion was slow and memory-sensitive; parallel PDF prepare produced hard failures and process residue.
5. Some Markdown sources had non-UTF-8 encoding or missing local image references.
6. The work was attempted as one 100-document batch instead of small resumable batches.
7. `uv run` left lingering processes after aborted/timeout operations; `.venv\Scripts\pkcs.exe` was more stable for continuation.
8. The execution should have stopped after the first HTML/PDF smoke failure and revised the pipeline before continuing.

## Follow-up Recommendation

For future corpus ingestion:

1. Keep source selection separate from download validation.
2. Require a 10-12 document smoke batch before full corpus execution.
3. Convert public HTML to Markdown snapshots before `prepare-ingest`.
4. Use Docling only for a small PDF/DOCX subset where artifact fidelity matters.
5. Use per-file timeout and append-only reports from the start.
6. Avoid `uv run` for long batch loops on Windows; use `.venv\Scripts\pkcs.exe` directly after `uv sync`.

