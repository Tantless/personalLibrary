# PKCS Explicit Markdown Block Graph 验收报告

日期：2026-06-12
任务：`.trellis/tasks/06-12-pkcs-explicit-markdown-block-graph`
状态：通过
实现提交：`7e209c1`

## 验收结论

已将 Markdown artifact-aware ingest 主链路从隐式 `_RenderedEntry` 流升级为 transient internal `MarkdownBlock` graph：

```text
raw Markdown
  -> transient block graph
  -> artifact extraction
  -> block-owned narrative chunks
  -> artifact-derived chunks
  -> existing artifact/chunk/citation persistence
```

本任务没有新增 `source_blocks` 表、block repository、block search/read API，也没有改变 Raw Archive 作为证据源的规则。

## 产物

* `src/pkcs/ingest/models.py`：新增 `ParsedMarkdownBlock`、`ParsedMarkdownBlockEdge`、`ParsedArtifactBinding`、`ParsedMarkdownBlockGraph`。
* `src/pkcs/ingest/parsers.py`：Markdown parser 先构建 transient block graph，再派生 table/image artifacts、narrative chunks 和 artifact chunks。
* `src/pkcs/ingest/service.py`：保留已有 persistence flow，并把 `source_block_id` / `bound_block_ids` 写入现有 artifact metadata。
* `src/pkcs/ingest/trace.py`：`trace-ingest` 升级为 `artifact_ingest_trace_v2`，新增 `block_graph` 阶段。
* `tests/test_ingest_trace.py`：覆盖 block graph trace、block refs、overlap context reference。
* `.trellis/spec/backend/*.md`：同步 parser contract 和 artifact metadata contract。
* `README.md`：更新 trace 边界说明。

## 实际验证

使用用户当前验收文档重新生成 trace：

```text
uv run pkcs trace-ingest data/private/acceptance-inputs/2026-06-12-artifact-docs/ML-For-Beginners/2-Regression/3-Linear/README.md --knowledge-type document --canonical-key document:trace-linear-block-graph-20260612 --output data/private/acceptance-inputs/2026-06-12-artifact-docs/linear-trace-debug.json
```

输出摘要：

```text
trace_version = artifact_ingest_trace_v2
stage_order = input -> block_graph -> parser -> asset_resolution -> ingest_report -> database
block_graph.blocks = 298
block_graph.edges = 297
block_graph.artifact_bindings = 3
block_graph.diagnostics = 12
block_types = heading 22, blank 124, paragraph 77, image 1, blockquote 34, list 9, table 2, code_fence 21, html 8
parser.table_artifacts = 2
parser.image_artifacts = 1
parser.table_derived_chunks = 4
parser.image_derived_chunks = 1
```

关键诊断：

```text
line 22: unsupported_linked_markdown_image
line 114: unsupported_linked_markdown_image
line 120: unsupported_html_image
```

这说明本任务已经能在 block graph 层解释当前文档中 linked image / HTML image 仍未对象化的原因；后续图片语法增强任务可基于这些 diagnostics 继续推进。

## 验收命令

```text
docker compose ps postgres
uv run alembic upgrade head
uv run pytest tests/test_ingest_trace.py
uv run pytest tests/test_ingest.py tests/test_context_pack.py tests/test_search.py
uv run pytest tests/test_ingest_trace.py tests/test_ingest.py tests/test_context_pack.py tests/test_search.py
uv run pytest
python .trellis/scripts/task.py validate .trellis/tasks/06-12-pkcs-explicit-markdown-block-graph
git diff --check
```

## 验收结果

```text
postgres: healthy
alembic: upgraded to head successfully
trace tests: 3 passed
related tests: 23 passed
full pytest: 44 passed, 1 warning
trellis validate: passed
git diff --check: passed
```

测试警告：

```text
StarletteDeprecationWarning from fastapi.testclient/httpx compatibility
```

该警告来自第三方测试客户端兼容层，不影响本任务结果。

## 明确边界

* 已实现 transient internal Markdown block graph。
* 已实现 block-owned narrative chunks 与 primary/context artifact link role。
* 已实现 artifact-derived chunks 的 `source_block_id` / `bound_block_ids`。
* 已实现 `trace-ingest` 的 `block_graph` 阶段。
* 未实现 persisted `source_blocks`。
* 未实现 linked image / HTML image 对象化；这些属于 `06-12-pkcs-comprehensive-markdown-image-block-parsing`。
* 未实现 OCR、vision summary、embedding、rerank、PDF/HTML/docx ingest。

