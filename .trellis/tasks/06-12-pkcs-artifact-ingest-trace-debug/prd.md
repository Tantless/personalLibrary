# PKCS Artifact Ingest Trace Debug

## Goal

提供一个开发者可运行的 Markdown artifact ingest trace，用 JSON 把原始 Markdown 从输入、解析、artifact 对象、derived chunks、Raw Archive/asset 写入、数据库 rows、metadata link 补全的每一步输出出来，帮助对照“理想 block stream 设计”和当前实现状态。

## What I Already Know

* 用户希望看清楚一份 Markdown 文档如何逐步识别文本域、图片域、表格域，并如何生成对象和对象派生 chunks。
* 当前实现已经走通 Markdown-only artifact-aware ingest skeleton，但 parser 内部使用隐式 `_RenderedEntry` 流，不是显式 `MarkdownBlock` AST。
* 当前 table artifact 会派生 `table_summary` 和 `table_rows`；image artifact 会派生 `image_summary`。
* 当前图片不做 OCR/vision，只对象化 Markdown image reference 的 `original_uri`、`asset_path`、`alt_text`、`nearby_text`。
* 生产 ingest 不应默认打印源文内容或调试细节；trace 应作为显式开发者工具。

## Requirements

* 新增一个显式调试入口，能对单个本地 Markdown 文件输出端到端 trace。
* trace 输出必须包含阶段：
  * input 文件元数据。
  * parser 输出的 chunks、table artifacts、image artifacts。
  * 当前实现与理想设计的差异说明。
  * image asset 解析/存在性检查。
  * ingest report。
  * database rows：source/version、table_artifacts、image_artifacts、chunks、citations。
  * metadata linking：`linked_artifacts.artifact_id`、artifact-derived chunk 的 `artifact_id` 和 `parent_narrative_chunk_id`。
* trace 输出默认不打印完整源文，只输出 preview、counts、locator、metadata。
* trace 必须复用现有 parser/service/repository/session，不复制生产 ingest 逻辑。
* trace 可以写入数据库，因为目标是看“到落库”的全链路；命令名和文档必须明确它会执行 ingest。
* CLI 增加开发者命令，保持 interface thin。
* 增加测试验证 trace JSON shape 和关键链路字段。

## Acceptance Criteria

* [ ] 可以运行 `uv run pkcs trace-ingest <markdown-file> --knowledge-type document --canonical-key <key>` 并输出 JSON。
* [ ] JSON 中能看到 input -> parser -> storage checks -> ingest report -> database -> design gaps。
* [ ] trace 中 table/image artifacts 数量与数据库 rows 一致。
* [ ] trace 中 narrative chunk 能看到 `linked_artifacts`，且落库后有 `artifact_id`。
* [ ] trace 中 derived chunks 能看到 `chunk_kind`、`artifact_type`、`artifact_id`、`parent_narrative_chunk_id`。
* [ ] 测试使用 synthetic fixture，不依赖 private data。
* [ ] `uv run pytest` 通过。

## Technical Approach

新增 `src/pkcs/ingest/trace.py`：

* `ArtifactIngestTraceService` 负责：
  * 读取文件 bytes 和基础元数据。
  * 调用 `parse_source_file()` 得到 parser trace。
  * 对 image artifacts 做 asset existence check。
  * 调用 `IngestService.ingest_source()` 执行真实 ingest。
  * 按 returned `source_id/version_id` 查询数据库 rows。
  * 输出稳定 JSON dict。
* `src/pkcs/cli.py` 增加 `trace-ingest` 命令，只做参数接收和 JSON 输出。
* `tests/test_ingest_trace.py` 覆盖 service 和 CLI shape。

## Decision (ADR-lite)

**Context**: 用户需要理解当前 artifact-aware ingest skeleton 与原始设计的差异，普通测试断言无法直观看到每个阶段。

**Decision**: 增加显式开发者 trace 命令，而不是把调试输出塞进生产 ingest report 或日志。

**Consequences**:

* 生产 ingest 行为保持稳定。
* trace 会写入本地数据库，适合验收/调试，不适合默认用户流程。
* 输出只包含 preview 和结构化 refs，避免泄露完整源文。
* 当前差异会被明确输出：没有显式 block AST、没有 row-group chunking、没有 OCR/vision。

## Out of Scope

* 不实现显式 `MarkdownBlock` AST 重构。
* 不实现大表 row group chunking。
* 不实现 OCR、vision summary、embedding 或 rerank。
* 不增加 HTTP/MCP trace 工具。
* 不把 trace 输出写入持久化 audit table。

## Technical Notes

* Parser: `src/pkcs/ingest/parsers.py`
* Ingest service: `src/pkcs/ingest/service.py`
* DB models/repositories: `src/pkcs/db/models.py`, `src/pkcs/db/repositories.py`
* CLI: `src/pkcs/cli.py`
* Existing tests: `tests/test_ingest.py`, `tests/test_context_pack.py`, `tests/test_search.py`

