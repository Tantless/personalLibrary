# M3 baseline corpus v1 reingestion result

## Result

* manifest rows: 100
* DB sources: 100
* DB source versions: 100
* DB chunks: 4248
* DB image artifacts: 412
* DB table artifacts: 75
* validation pass: 100
* validation fail: 0
* search smoke pass: 100
* title mismatches: 0
* reject-pattern rows: 0
* local artifact-ready rows: 28

## Notes

* The full run reset PKCS business tables and cleared `data/raw` / `data/private` before ingesting v1.
* Ingestion used `.venv/Scripts/pkcs.exe` CLI, which calls the same PKCS application service as the MCP ingest path.
* `M3-ANIME-021` required the explicit `markdown_utf8_sanitized` fallback and was patched in a second no-reset run.
* Reader Markdown snapshots were used where public HTML was more stable through reader conversion than direct Docling HTML conversion.

## Reports

* Per-row validation: `validation.jsonl`
* Machine summary: `summary.json`
