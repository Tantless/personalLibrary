# PKCS Artifact Ingest Trace Debug 验收报告

日期：2026-06-12
任务：`.trellis/tasks/06-12-pkcs-artifact-ingest-trace-debug`
状态：通过

## 验收结论

已新增开发者调试入口 `trace-ingest`，可以对单个 Markdown 文件输出从原始输入到 parser 中间态、asset resolution、真实 ingest report、数据库 rows 和 metadata linking 的全链路 JSON。

## 产物

* `src/pkcs/ingest/trace.py`：`ArtifactIngestTraceService`
* `src/pkcs/cli.py`：`uv run pkcs trace-ingest ...`
* `tests/test_ingest_trace.py`：service 和 CLI trace 覆盖
* `README.md`：命令用法说明

## 实际验证

使用用户当前打开的 Linear Regression Markdown 实际生成 trace：

```text
uv run pkcs trace-ingest data/private/acceptance-inputs/2026-06-12-artifact-docs/ML-For-Beginners/2-Regression/3-Linear/README.md --knowledge-type document --canonical-key document:trace-linear-flow-20260612 --output data/private/acceptance-inputs/2026-06-12-artifact-docs/linear-trace-debug.json
```

输出文件：

```text
data/private/acceptance-inputs/2026-06-12-artifact-docs/linear-trace-debug.json
```

摘要：

```text
stage_order = input -> parser -> asset_resolution -> ingest_report -> database
parser chunks = 32
parser table_artifacts = 2
parser image_artifacts = 1
parser table_derived_chunks = 4
parser image_derived_chunks = 1
database chunks = 32
database citations = 32
database table_artifacts = 2
database image_artifacts = 1
linked_artifacts_with_artifact_id = 4
artifact_chunks_with_artifact_id = 5
artifact_chunks_with_parent_narrative_chunk_id = 5
```

## 验收命令

```text
docker compose ps postgres
uv run alembic upgrade head
uv run pytest tests/test_ingest_trace.py
uv run pytest tests/test_ingest.py tests/test_search.py tests/test_context_pack.py tests/test_ingest_trace.py
uv run pytest
python .trellis/scripts/task.py validate .trellis/tasks/06-12-pkcs-artifact-ingest-trace-debug
git diff --check
```

## 验收结果

```text
postgres: healthy
alembic: upgraded to head successfully
trace tests: 2 passed
related tests: 22 passed
full pytest: 43 passed, 1 warning
trellis validate: passed
git diff --check: passed
```

测试警告：

```text
StarletteDeprecationWarning from fastapi.testclient/httpx compatibility
```

该警告来自第三方测试客户端兼容层，不影响本任务结果。

## 明确边界

trace 明确输出当前实现差异：

* 已实现隐式 rendered-entry block stream，但没有显式 public `MarkdownBlock` AST。
* 已实现 table/image artifact object 和 derived chunks。
* 已实现落库后 metadata id link 补全。
* 尚未实现大表 row-group chunking。
* 尚未实现 OCR、vision summary、PDF/HTML/docx artifact extraction。

