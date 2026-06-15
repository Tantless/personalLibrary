# brainstorm: PKCS ingest normalization tooling with Docling

## Goal

将 Docling 引入 PKCS 的 ingest 前置规范化流程，主要解决 PDF、DOCX、XLSX、HTML、MD 等常见资料进入系统前统一转换为 normalized Markdown 的问题，并与已有 `pkcs-ingest` skill、PKCS MCP `ingest_source` 串联成完整 ingest 工作流。

## What I already know

* 当前 PKCS 后端 ingest 主链路已经支持本地 Markdown/text 文件和非递归目录。
* 当前 Markdown parser 已支持 table/image artifact，包括常见 Markdown image block 增强。
* 新增的 `.agents/skills/pkcs-ingest/SKILL.md` 已定义预处理规范：`document.md`、`assets/`、`tables/`、`source-info.json`、`ingest-log.json`。
* 用户希望主要支持 PDF/DOCX/XLSX/HTML/MD 格式。
* 用户希望最终能与已有 skill 和 MCP 串联，而不只是说明文档。
* 初步判断：Docling 适合作为 ingest 前置转换器，不宜直接塞入核心 MCP ingest 事务路径。
* `src/pkcs/source_metadata.py` 已预留 `pdf/docx/xlsx` source format code，但当前 `document` ingest 只支持 `.md/.txt`，且 PDF/DOCX 没有 normalized format mapping。
* 当前 `IngestService.ingest_source()` 会拒绝 URL，只接受本地路径；MCP `ingest_source` 也是同一约束。
* 当前 image asset copy 由 `IngestService._archive_image_asset()` 基于 Markdown 中的相对路径执行，因此 normalizer 需要确保 `document.md` 中的本地图片路径能从 `document.md` 所在目录解析。

## Assumptions (temporary)

* normalized Markdown 仍是 PKCS ingest 主链路的稳定输入。
* v1 应优先以本地 CLI/subprocess 形式调用 Docling，减少对 PKCS 服务启动、测试和运行内存的影响。
* MD 输入也应经过统一 package/asset/table/log 规范化，但不需要 Docling 转换。

## Open Questions

* 暂无阻塞问题。用户已选择 dependency strategy：先外部 CLI，验收稳定后再评估 optional dependency。

## Requirements (evolving)

* 支持单文件 PDF、DOCX、XLSX、HTML、MD 输入。
* 生成 normalized Markdown package：`document.md`、`assets/`、`tables/`、`source-info.json`、`ingest-log.json`。
* 本地图片引用统一落到 `assets/` 并改写 Markdown 引用。
* 表格按大小或来源保留 inline Markdown table 或落到 `tables/` 侧车文件。
* 准备完成后由 agent/skill 自动调用 MCP `ingest_source` 串联完成 ingest。
* 保留转换、校验和失败原因日志。
* Docling 不应成为 PKCS MCP server 启动的硬依赖；调用方式应支持缺失依赖时给出清晰错误。
* `.agents/skills/pkcs-ingest/SKILL.md` 应更新为真实链路说明书：先调用项目 pre-ingest 命令，再调用 MCP `ingest_source`。
* 命令输出机器可读 JSON，方便 agent 稳定读取 `document_path`、status、warnings 和 failure reason。

## Acceptance Criteria (evolving)

* [x] Markdown 输入可生成规范化 package，并可被现有 PKCS ingest 成功摄入。
* [x] PDF 输入可通过 Docling 转为 `document.md`，并保留可解析的图片/表格引用。
* [x] DOCX 输入可通过 Docling 转为 `document.md`。
* [x] XLSX 输入可生成 Markdown 摘要与 `tables/` 侧车文件。
* [x] HTML 输入可通过 Docling 转为 `document.md`，本地图片资源可被复制到 `assets/`。
* [x] 缺失本地图片、Docling 不可用、转换失败等场景有可追踪日志。
* [x] 生成的 `document.md` 可通过 MCP `ingest_source` 完成 ingest。
* [x] `pkcs-ingest` skill 说明 agent 如何执行 `pre-ingest command -> MCP ingest_source` 链路。
* [x] `prepare-ingest` CLI 返回 JSON，包含 `status`、`prep_dir`、`document_path`、`source_info_path`、`ingest_log_path`、`counts`、`warnings`、`errors`。

## Definition of Done (team quality bar)

* Tests added/updated for normalizer behavior and ingest integration.
* `uv run pytest` passes with PostgreSQL healthy where integration tests require it.
* `pkcs-ingest` skill updated after the implemented command and MCP chain are verified.
* README updated only after the implemented feature is verified, so user-facing setup instructions match the real behavior.
* Relevant backend spec updated if new command/module contracts are introduced.
* Rollout/rollback considered for Docling dependency and large-file behavior.

## Out of Scope (explicit)

* OCR/vision summary/detected entities enrichment.
* Remote image downloading by default.
* Replacing current PKCS Markdown parser or image/table artifact logic.
* Persisting a new source block table.
* Making Docling a mandatory dependency for MCP server startup unless explicitly chosen.
* 在 MVP 中新增一键 ingest CLI 替代 MCP `ingest_source`。
* 在 MVP 中新增新的 MCP ingest tool；先复用现有 `ingest_source`。
* MVP 不做目录批量 pre-ingest；先把单文件链路打通。

## Research Notes

### Docling 官方能力

* Docling 支持 PDF、DOCX、XLSX、PPTX、Markdown、HTML、CSV、图片等输入格式，并可导出 Markdown、HTML、JSON、text 等格式。
* Docling CLI 默认输出 Markdown，`--to md` 可显式指定 Markdown 输出。
* Docling CLI 的 `--image-export-mode referenced` 会把图片导出为文件并在 Markdown 中引用；这和 PKCS 现有 image artifact asset copy 机制匹配。
* HTML/EPUB 场景下，Docling CLI 有 `--html-image-fetch none|local|remote|all`。本项目 v1 应只使用 `local` 或默认不抓远程图，符合既有“远程图片不默认下载”的约束。
* Docling 官方推荐 Python API，但 CLI 对本项目更适合作为第一版隔离边界。
* Docling `docling-slim` 已将能力拆成 extras；minimal base 标注约 50MB，PDF/office/web/OCR/model 能力是可选 extras。
* Docling full/standard 会引入 local models、OCR、PDF layout 等较重依赖；`docling-serve` 镜像存在数 GB 级体积，适合作为后续隔离服务，不适合第一版直接纳入 PKCS 核心服务。

Sources:

* Docling supported formats: https://docling-project.github.io/docling/usage/supported_formats/
* Docling CLI reference: https://docling-project.github.io/docling/reference/cli/
* Docling installation/extras: https://docling-project.github.io/docling/getting_started/installation/
* Docling GitHub / quickstart: https://github.com/docling-project/docling
* Docling slim pyproject: https://github.com/docling-project/docling/blob/main/pyproject.toml
* Docling serve: https://github.com/docling-project/docling-serve

### Constraints from PKCS repo

* 当前项目依赖很轻，`pyproject.toml` 只有 FastAPI/MCP/SQLAlchemy/Typer/PostgreSQL 相关依赖。
* 当前 `pkcs ingest` 和 MCP `ingest_source` 复用同一个 `IngestService`，只吃本地路径。
* 当前 Markdown parser 和 artifact persistence 已经能处理 Markdown 中的 table/image artifact；normalizer 应复用这条链路，不重写 artifact 逻辑。
* 当前 source/version 的 `source_format_code` 会根据实际传入文件后缀计算。若 v1 传入 `document.md`，数据库 source format 会是 `md`；原始源格式应先记录在 `source-info.json` 与 version metadata 中，是否新增 DB 字段另起任务评估。
* 当前 Raw Archive 会归档 ingest 传入的文件；v1 应让 evidence 指向 normalized `document.md`，并通过日志保留原始来源信息。

## Feasible Approaches

### Approach A: CLI normalizer + existing MCP ingest (Recommended)

How it works:

* 新增 `pkcs prepare-ingest <source>` 命令。
* 对 MD/TXT 走轻量 normalization；对 PDF/DOCX/XLSX/HTML 调用 Docling CLI/subprocess。
* 输出 `document.md`、`assets/`、`tables/`、`source-info.json`、`ingest-log.json`。
* skill 调用 `prepare-ingest` 后，再调用 MCP `ingest_source(path=<prep-dir>/document.md)`。

Pros:

* 对现有 MCP server 和核心 ingest service 冲击最小。
* Docling 进程结束后释放内存；大依赖不影响 server 启动。
* 易于记录转换日志和失败原因。
* 最符合已有 `pkcs-ingest` skill 的流程。
* 最终用户入口仍是 skill，命令只是 agent 可调用的稳定工具。

Cons:

* 需要 agent 正确执行“prepare command -> MCP ingest_source”两步。
* 需要处理 Docling CLI 输出文件名、图片目录和路径改写。
* Python API 的结构化表格能力暂时不能充分利用。

### Approach B: Python API normalizer module inside PKCS

How it works:

* 新增 `pkcs.ingest.normalization` 模块，直接 import Docling `DocumentConverter`。
* CLI 和可选 MCP tool 调用该模块，拿 DoclingDocument 后导出 Markdown/JSON，并做 assets/tables 规范化。

Pros:

* 可以更精细地处理表格、图片和 Docling JSON。
* 更容易做单元测试和未来扩展。

Cons:

* Docling 依赖进入 Python runtime，可能拖慢启动并增加内存常驻压力。
* 依赖冲突和模型下载更容易影响 PKCS 后端。
* v1 工程风险高于 CLI/subprocess。

### Approach C: Docling sidecar service

How it works:

* 使用 `docling-serve` 或自建转换服务。
* PKCS normalizer 通过 HTTP 调用 sidecar，把转换结果整理成本地 package。

Pros:

* 资源隔离最好，可以给 sidecar 单独设置内存/CPU。
* 适合多人/批量转换和未来远程部署。

Cons:

* 初始部署复杂度最高。
* 镜像体积和运维成本明显增加。
* 本地优先 MVP 阶段不够轻。

## Recommendation

采用 Approach A 作为 MVP：新增本地 `prepare-ingest` normalizer，Docling 以 CLI/subprocess 方式作为可选外部转换器；准备完成后由 `pkcs-ingest` skill 指导 agent 调用现有 MCP `ingest_source` 完成写入。

核心原则：

* PKCS ingest 主链路继续以 normalized Markdown 为输入。
* Docling 位于 ingest 前置准备层，不进入数据库事务主路径。
* `pkcs-ingest` skill 是最终用户入口和 agent 使用说明，实际 pre-ingest 命令由本 task 实现。
* v1 不把 Docling full package 加入主 dependencies；优先检测系统是否可调用 `docling` CLI，必要时给出安装建议。
* Dependency strategy: 先依赖外部 `docling` CLI，验收稳定后再评估是否加入 `docling-slim[cli,format-pdf,format-office,format-web]` optional dependency。
* README 中的“无环境用户使用链路”必须等功能实现并验收后再写入。

## User Scope Decision

用户确认最终入口是 `pkcs-ingest` skill：

```text
用户调用 skill
  -> agent 调用 PKCS pre-ingest 命令生成 normalized package
  -> agent 调用 MCP ingest_source 摄入 document.md
```

因此本任务目标是验证并固化 `pre-ingest command + MCP ingest` 这条链路，而不是把任意格式文档直接塞进 MCP ingest 主工具。任务完成后，需要更新 `.agents/skills/pkcs-ingest/SKILL.md`，让 skill 成为这条链路的说明书。

## Decision (ADR-lite)

**Context**: PKCS 当前 MCP `ingest_source` 只接收本地 Markdown/text 路径，并已复用稳定的 ingest service、Raw Archive、artifact parser 和检索链路。Docling 可解决非 Markdown 文件转换，但依赖和内存压力不适合进入 MCP server 主进程。

**Decision**: 新增项目级 `prepare-ingest` 命令作为 pre-ingest normalizer。Agent 通过 `pkcs-ingest` skill 调用该命令生成 `document.md` package，再调用现有 MCP `ingest_source` 完成写入。MVP 不新增一键 ingest CLI 替代 MCP，也不让 Docling 成为 MCP server 启动依赖。

**Consequences**:

* 用户入口保持为 skill，符合 agent-first 使用方式。
* 规范化中间产物可验收、可调试、可重跑。
* MCP ingest 主链路保持稳定。
* 自动化链路依赖 agent 正确执行两步，需在 skill 中写清命令、校验点和失败处理。
* README 更新被放到验收之后，避免文档提前承诺未验证的安装和使用路径。

## Command Contract

新增 CLI 命令：

```powershell
uv run pkcs prepare-ingest <source-path> --output-root data/private/ingest-prep
```

可选参数：

```text
--output-root <dir>       准备目录根路径，默认 data/private/ingest-prep
--slug <name>             准备目录可读名称，默认由源文件名生成
--timeout-seconds <n>     Docling subprocess 超时，默认 300
--overwrite               允许覆盖同名准备目录；默认自动追加数字后缀
```

命令只接受本地单文件路径。输出 JSON 到 stdout，供 agent/skill 读取：

```json
{
  "status": "success",
  "prep_dir": "data/private/ingest-prep/2026-06-15-example",
  "document_path": "data/private/ingest-prep/2026-06-15-example/document.md",
  "source_info_path": "data/private/ingest-prep/2026-06-15-example/source-info.json",
  "ingest_log_path": "data/private/ingest-prep/2026-06-15-example/ingest-log.json",
  "counts": {
    "local_images": 2,
    "remote_images": 1,
    "missing_local_images": 0,
    "inline_tables": 1,
    "sidecar_tables": 2
  },
  "warnings": [],
  "errors": []
}
```

Agent 串联 MCP ingest：

```text
ingest_source(
  path="<document_path from prepare-ingest JSON>",
  knowledge_type="document",
  canonical_key="<optional user-provided key>"
)
```

## Package Contract

准备目录结构：

```text
data/private/ingest-prep/YYYY-MM-DD-source-slug/
  document.md
  assets/
  tables/
  source-info.json
  ingest-log.json
```

`source-info.json`：

```json
{
  "source_kind": "local_file",
  "original_name": "example.pdf",
  "original_path_name": "example.pdf",
  "source_format": "pdf",
  "normalized_format": "md",
  "converter": "docling-cli",
  "converter_version": "x.y.z",
  "prepared_at": "2026-06-15T00:00:00+08:00"
}
```

`ingest-log.json`：

```json
{
  "status": "success",
  "steps": [
    {"name": "inspect", "status": "success"},
    {"name": "convert", "status": "success"},
    {"name": "normalize_assets", "status": "success"},
    {"name": "normalize_tables", "status": "success"},
    {"name": "validate", "status": "success"}
  ],
  "asset_mappings": [
    {"original": "images/logo.png", "normalized": "assets/logo.png"}
  ],
  "table_mappings": [
    {"original": "Sheet1", "normalized": "tables/Sheet1.csv"}
  ],
  "warnings": [],
  "errors": []
}
```

## Normalization Rules

### Markdown / MD

* Copy the source Markdown to `document.md`.
* Resolve local image references relative to the source Markdown location.
* Copy local assets into `assets/` and rewrite references.
* Keep remote image URLs unchanged and count them.
* Preserve existing Markdown tables unless they exceed the large-table threshold.

### PDF / DOCX / HTML

* Run Docling CLI with Markdown output and referenced image export.
* Move or rename selected Markdown output to `document.md`.
* Normalize all local image refs into `assets/`.
* Keep remote image URLs unchanged.
* Validate generated Markdown before MCP ingest.

### XLSX

* Use Docling as the primary conversion path.
* Generate `document.md` with workbook/sheet summary and references to table sidecars when tables are large.
* Save sheet data under `tables/` as `.csv` or `.md`.
* Preserve sheet names in `ingest-log.json`.

### Asset naming

* First basename keeps original filename: `assets/logo.png`.
* Collisions append numeric suffixes: `assets/logo-2.png`, `assets/logo-3.png`.
* Do not use hashes for normal asset names.

## Failure Behavior

Status levels:

* `success`: package generated and validation passed.
* `success_with_warnings`: package generated with non-blocking fidelity issues.
* `soft_fail`: package incomplete but user/agent may decide whether to proceed.
* `hard_fail`: no valid `document.md` can be produced.

Examples:

* Docling not installed: `hard_fail`, include install hint and intended command.
* Docling timeout: `hard_fail`, include elapsed time and timeout.
* Missing local image in Markdown: `soft_fail` by default, include original reference and searched path.
* Remote image URL: warning/count only, not a failure.
* Empty converted Markdown: `hard_fail`.

## Test Plan

Unit-level tests:

* Markdown asset normalization rewrites local image refs to `assets/...`.
* Asset name collision uses numeric suffixes.
* Remote image URLs remain unchanged.
* Missing local asset produces `soft_fail` diagnostics.
* Output package JSON files follow the expected schema.

CLI tests:

* `prepare-ingest` works for Markdown without Docling.
* Docling missing produces clear JSON failure.
* Docling subprocess call can be monkeypatched/faked for PDF/DOCX/HTML/XLSX conversion tests without downloading real models.

Integration tests:

* Prepared Markdown package can be ingested through existing `IngestService`.
* Prepared `document.md` can be ingested through MCP `ingest_source`.
* Existing ingest/search/context-pack tests continue passing.

Manual acceptance:

* Run one real PDF/DOCX/XLSX/HTML fixture through `prepare-ingest`.
* Inspect `document.md`, `assets/`, `tables/`, `source-info.json`, `ingest-log.json`.
* Call MCP `ingest_source` with `document_path`.

## Implementation Plan

PR1: Normalizer skeleton and Markdown path

* Add `pkcs.ingest.normalization` module with dataclasses for package report, source info, logs, and status.
* Add `pkcs prepare-ingest` CLI command.
* Implement Markdown input normalization, local asset copy/rewrite, JSON logs, and validation.
* Add unit/CLI tests for Markdown path and failure statuses.

PR2: Docling CLI adapter

* Add subprocess adapter for Docling CLI with timeout, version detection, and clear missing-dependency errors.
* Implement PDF/DOCX/HTML conversion path using mocked Docling outputs in automated tests.
* Normalize Docling-produced assets into PKCS package shape.

PR3: XLSX/table handling and chain acceptance

* Implement XLSX table sidecar policy.
* Add tests for sidecar table references.
* Add MCP chain acceptance test: `prepare-ingest` output `document.md` -> `ingest_source`.
* Update `.agents/skills/pkcs-ingest/SKILL.md` to call the real command.
* After the chain is verified, update `README.md` with the confirmed zero-environment setup and usage flow.

## Expansion Sweep

### Future evolution

* 后续可增加 `prepare-ingest --from-url`、batch/retry、Docling JSON 留存、converter profile。
* 若转换频率升高，可将 Docling 从 CLI 迁移到 sidecar service，以隔离内存和模型依赖。

### Related scenarios

* `pkcs-ingest` skill 应更新为调用真实 `pkcs prepare-ingest` 命令，再调用 MCP `ingest_source`。
* MCP 先保持 `ingest_source` 不变；如未来需要 agent 单 tool 完成任意格式 ingest，再新增 `prepare_ingest_source` 或 `ingest_document` MCP tool。

### Failure and edge cases

* Docling 未安装、版本不兼容、转换超时、大文件内存压力、输出 Markdown 为空。
* 本地图片引用缺失、同名 asset 冲突、HTML 远程图片、XLSX 大表膨胀。
* 准备目录重复、重复 ingest、canonical_key 与多文件输入冲突。

## Technical Notes

* Current CLI entry: `src/pkcs/cli.py`.
* Current MCP ingest tool: `src/pkcs/mcp/server.py::ingest_source`.
* Current ingest service: `src/pkcs/ingest/service.py`.
* Current Markdown parser: `src/pkcs/ingest/parsers.py`.
* Existing ingest skill: `.agents/skills/pkcs-ingest/SKILL.md`.
* Current metadata mapping: `src/pkcs/source_metadata.py`.
