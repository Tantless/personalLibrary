# PKCS Comprehensive Markdown Image Block Parsing 验收报告

日期：2026-06-12
任务：`.trellis/tasks/06-12-pkcs-comprehensive-markdown-image-block-parsing`
状态：自动验证通过，待用户验收
实现提交：`abd9f91`

## 验收结论

已基于现有 transient `ParsedMarkdownBlockGraph` 增强 Markdown image block 识别，没有新增独立解析管线，也没有新增数据库表或迁移。

当前支持的可见图片形态：

* standalone Markdown image：`![alt](path)`
* blockquote Markdown image：`> ![alt](path)`
* linked Markdown image：`[![alt](thumb)](target "title")`
* reference image：`![alt][id]` / `![alt][]` / `![alt]`
* HTML img：`<img alt="x" src="path" width="50%"/>`
* linked HTML img：同一 HTML block 内 `<a href="..."><img ...></a>`

图片 artifact metadata 现在会保留 `image_syntax`、`container`、`outer_link_url`、`outer_link_title`、`html_attrs`、`reference_id`、`caption_block_ids`、`nearby_text_block_ids` 等确定性字段。

## 实现摘要

* `src/pkcs/ingest/parsers.py`
  * 在 block graph 构造阶段识别更多 image candidate。
  * 将 supported linked / HTML / reference image 提升为 `block_type=image`。
  * 为 linked image 绑定后续 caption / nearby block，并写入 `bound_block_ids`。
  * fenced code 内图片继续被忽略。
* `src/pkcs/ingest/trace.py`
  * 更新 `design_delta`，反映 common Markdown image block detection。
* `.trellis/spec/backend/database-guidelines.md`
  * 记录 image artifact metadata contract。
* `tests/test_ingest.py`
  * 新增数据库级 ingest 覆盖：本地 asset copy、remote URL 不 copy、metadata 入库、image summary chunks。
* `tests/test_ingest_trace.py`
  * 新增 parser/trace 覆盖：blockquote、linked、HTML、reference image，以及 fenced code 忽略。

## 实际文档验收

使用用户当前 Linear Regression README 重新生成 trace：

```text
uv run pkcs trace-ingest data/private/acceptance-inputs/2026-06-12-artifact-docs/ML-For-Beginners/2-Regression/3-Linear/README.md --knowledge-type document --canonical-key document:trace-image-block-20260612 --output data/private/acceptance-inputs/2026-06-12-artifact-docs/image-block-trace-check.json
```

输出摘要：

```text
trace_version = artifact_ingest_trace_v2
block_graph.block_types.image = 15
block_graph.artifact_bindings = 17
block_graph.diagnostics = 0
unsupported_linked_markdown_image = 0
unsupported_html_image = 0
parser.image_artifacts = 15
database.image_artifacts = 15
database.image_derived_chunks = 15
```

关键对比：

* 显式 block graph 任务验收时，该 README 只有 `image_artifacts = 1`。
* 本任务实现后，该 README 解析出 `image_artifacts = 15`。
* 原先 line 22 / line 114 / line 174 / line 297 的 linked image 已成为 `linked_markdown_image` artifact。
* 原先 HTML `<img>` 行已成为 `html_img` artifact。
* 原先 unsupported linked / HTML diagnostics 已清零。

## 验收命令

```text
docker compose ps postgres
uv run alembic upgrade head
uv run pytest tests/test_ingest_trace.py::test_markdown_block_graph_detects_common_image_block_syntax tests/test_ingest.py::test_ingest_markdown_common_image_syntax_artifacts -q
uv run pytest tests/test_ingest_trace.py tests/test_ingest.py -q
uv run pytest tests/test_context_pack.py -q
uv run pytest tests/test_ingest_trace.py tests/test_ingest.py tests/test_context_pack.py -q
uv run pytest
git diff --check
```

## 验收结果

```text
postgres: healthy
alembic: upgraded to head successfully
new focused tests: 2 passed
ingest + trace tests: 13 passed
context pack tests: 6 passed
related tests: 19 passed
full pytest: 46 passed, 1 warning
git diff --check: passed
```

测试警告：

```text
StarletteDeprecationWarning from fastapi.testclient/httpx compatibility
```

该警告来自第三方测试客户端兼容层，不影响本任务结果。

## 明确边界

* 未新增 persisted `source_blocks` 表。
* 未新增 block-level query/read API。
* 未下载 remote image URL 到 Raw Archive。
* 未实现 OCR、vision summary、detected entities。
* 未实现 PDF/HTML/docx artifact extraction。
* 未引入 `markdown-it-py` 依赖；当前 fixtures 已可由 graph-first targeted parser 覆盖。
