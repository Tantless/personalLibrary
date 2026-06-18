---
name: pkcs-ingest
description: "当用户明确要求把本地 Markdown、PDF、DOCX、XLSX、HTML 等资料摄入 PKCS/知识库时使用。该 skill 编排本地文件准备、可选图片理解、PKCS ingest，并在批量或公网资料场景中先做下载验证、smoke batch、timeout 和降级策略。"
---

# PKCS Ingest

## Overview

这个 skill 是 PKCS 文档摄入入口。核心链路仍然是：

```text
本地源文件或已准备好的 document.md package
  -> agent 运行 pkcs prepare-ingest
  -> 生成 document.md + assets/ + tables/ + source-info.json + ingest-log.json
  -> agent 根据 assets/ 中的本地图片生成可选 image-enrichment.json
  -> agent 调用 PKCS ingest_source 或等价 CLI ingest
  -> 返回摄入结果和保真度说明
```

`prepare-ingest` 只负责 pre-ingest 规范化；`ingest_source` / `pkcs ingest` 负责真正写入 PKCS。不要把 URL 直接传给 MCP ingest。

## Input Modes

### Single-file mode

适用于用户给出 1 个或少量本地文件，并希望立即摄入。支持：

- `.md`, `.markdown`, `.mdx`
- `.pdf`
- `.docx`
- `.xlsx`
- `.html`, `.htm`

Markdown 输入不需要 Docling。PDF/DOCX/XLSX/HTML 默认尝试外部 `docling` CLI；Docling 不属于 PKCS 主依赖，也不要求 MCP server 启动时加载。

### Batch / public corpus mode

适用于用户给出一批公网 URL、JSONL manifest、或 20 个以上文件。此时不要直接开始全量 prepare/ingest。先执行：

1. **Source validation**: 下载或保存为本地文件，记录成功、失败、HTTP 状态、文件大小和最终路径。
2. **Smoke batch**: 选 10-12 个样本，覆盖本批中的主要格式和领域，先跑 prepare；必要时只摄入 smoke batch。
3. **Batch execution**: 每批最多 20 个文件；PDF/DOCX/XLSX 这类重格式每批最多 5 个。
4. **Append-only reports**: 从第一批开始写 JSONL/JSON 报告，记录每个文件的状态、耗时、warning、fallback、document_path。
5. **Failure queue**: 下载失败、转换失败、超时和需要替换来源的条目进入失败队列，不阻塞其他已准备好的条目。

批量模式的目标要先说清楚：是高保真 artifact ingest，还是 degraded text baseline。两者允许的 fallback 不同。

### Timeout and retry policy

批量模式必须给每个文件设置 timeout，不允许无界等待：

- Markdown / HTML snapshot prepare: 30s。
- DOCX prepare: 90s。
- PDF Docling prepare: 120s；超时或 hard fail 后进入 fallback/失败队列。
- Ingest: 30s。
- 下载：每个 URL 最多一次直接下载和一次明确 fallback；403/404 不做盲目重试。

这些数值是默认执行策略。用户明确要求高保真或超大文件时，可以调大，但要在报告中说明。

## Command Choice

在 Windows 长批处理里，优先使用虚拟环境内的 console script：

```powershell
.venv\Scripts\pkcs.exe prepare-ingest <source-path> --output-root data/private/ingest-prep
```

如果刚开始环境尚未同步，先运行 `uv sync`。小规模一次性命令可以使用：

```powershell
uv run pkcs prepare-ingest <source-path> --output-root data/private/ingest-prep
```

长批处理不要反复用 `uv run` 包裹每个文件；它在 Windows 上更容易放大启动成本，并且中断/超时后更难判断残留进程状态。

## Workflow

### 0. Preflight

在摄入前确认：

- Docker/PostgreSQL 已启动。
- `pkcs health` 返回 ok。
- 用户给的是本地文件；如果给的是 URL/manifest，先下载验证成 local file/snapshot。
- 对批量任务，确认是否接受 degraded text baseline。

推荐 health check：

```powershell
.venv\Scripts\pkcs.exe health
```

### 1. Prepare Package

单文件或小批量：

```powershell
.venv\Scripts\pkcs.exe prepare-ingest <source-path> --output-root data/private/ingest-prep --slug <readable-name> --timeout-seconds 300
```

如果只做一次性手动摄入，也可以使用等价 `uv run pkcs prepare-ingest ...`。

命令会输出 JSON。读取这些字段：

- `status`
- `document_path`
- `prep_dir`
- `source_info_path`
- `ingest_log_path`
- `counts`
- `warnings`
- `errors`

状态处理：

- `success`: 继续 ingest。
- `success_with_warnings`: 继续 ingest，并向用户报告 warning。
- `soft_fail`: 单文件模式默认暂停说明；批量 degraded text baseline 中，如果 warning 不影响文本证据，可记录后继续 ingest。
- `hard_fail`: 停止该文件，记录 `errors` 和 `ingest_log_path`，进入失败队列。

### 2. Conversion Fallbacks

Docling 是高保真首选路径，不是所有格式的无条件稳定路径。

- Public HTML: 优先保存为本地 HTML；如果 Docling 对现代页面失败，可用 `pandoc` 转成 Markdown snapshot 后再跑 `prepare-ingest`。说明 JS、交互 UI 和部分媒体会降级。
- PDF: 如果 Docling 超时、内存敏感或 hard fail，且本任务接受 degraded text baseline，可用 `pdftotext` 生成 plain Markdown snapshot 后摄入。说明 layout、图片和表格会降级。
- DOCX: Docling 失败但需要保留文本时，可用 `pandoc` 转 Markdown snapshot 后摄入。说明复杂布局和部分嵌入对象会降级。
- Markdown: 如果编码不是 UTF-8，先转成 UTF-8；缺失本地图片通常是 `soft_fail`，文本证据仍可保留。

不要在未说明降级影响的情况下把 fallback 结果当作高保真摄入。

### 3. Enrich Local Images

如果 package 的 `assets/` 中存在本地图片，且当前 agent CLI 使用的模型支持图片理解，则在 ingest 前分析这些图片并写入：

```text
<prep_dir>/image-enrichment.json
```

MVP schema：

```json
{
  "schema_version": 1,
  "images": [
    {
      "asset_path": "assets/diagram.png",
      "vision_summary": "A system diagram showing retrieval, ranking, and context assembly.",
      "ocr_text": "Retriever -> Reranker -> Context Pack",
      "visual_type": "diagram",
      "key_elements": ["Retriever", "Reranker", "Context Pack"],
      "confidence": "high"
    }
  ]
}
```

要求：

- `asset_path` 使用 package 内 normalized path，例如 `assets/diagram.png`。
- `vision_summary` 用于后续检索和上下文生成，应描述图片表达的关键信息。
- `ocr_text` 没有可读文字时写空字符串或省略。
- `visual_type` 使用 `diagram`、`chart`、`screenshot`、`photo`、`other`。
- `confidence` 使用 `high`、`medium`、`low`。
- 单张图片理解失败时，可写 `failure_code` / `failure_message`，不要中断整个 ingest。

不要要求用户单独配置视觉模型 API，也不要在 PKCS 内启动本地视觉服务。图片理解由当前 agent 能力完成；PKCS 只消费 `image-enrichment.json`。

如果当前 agent 不具备图片理解能力，或者图片分析失败，可以跳过该文件，继续 ingest。PKCS 会保留 Markdown 中已有的 alt/caption/nearby 信息。

### 4. Ingest

优先使用当前 Codex 会话中可用的 PKCS MCP tool：

```text
ingest_source(
  path="<document_path from prepare-ingest JSON>",
  knowledge_type="document",
  canonical_key="<optional user-provided key>"
)
```

`canonical_key` 仅在用户明确提供稳定身份，或批量 manifest 中已有稳定 ID 时传入。用户没有提供时，让 PKCS 自动生成。

如果当前会话没有暴露 PKCS MCP tool，或者 MCP server 因启动顺序不可用，可使用同一项目 service 的 CLI 等价路径：

```powershell
.venv\Scripts\pkcs.exe ingest <document_path> --knowledge-type document --canonical-key <canonical_key>
```

使用 CLI 等价路径时，必须在结果中说明：这不是字面 MCP tool 调用，但写入路径复用同一 PKCS ingest service。

### 5. Report Result

向用户报告：

- `prepare-ingest` status
- `document_path`
- local image / remote image / missing image 计数
- `image-enrichment.json` 是否生成；如未生成，说明已按普通图片 metadata 降级摄入
- inline table / sidecar table 计数
- ingest status、`source_id`、`version_id`、`canonical_key`
- 影响资料保真度的 warnings 和 fallback

批量任务还要报告：

- 总数、成功数、失败数、soft fail 数、duplicate skipped 数
- 每种格式的 prepare 成功/失败/耗时概况
- 失败队列和替换/重试建议
- 是否存在 degraded text baseline

## Package Shape

`prepare-ingest` 生成：

```text
data/private/ingest-prep/YYYY-MM-DD-source-slug/
  document.md
  assets/
  tables/
  source-info.json
  ingest-log.json
  image-enrichment.json  # 可选，agent 生成
```

规范化行为：

- 本地图片复制到 `assets/`，Markdown/HTML/reference image 引用同步改写。
- 同名图片使用数字后缀，例如 `logo.png`、`logo-2.png`。
- 远程图片 URL 保持原样，默认不下载。
- 小表保留 Markdown table。
- 大表保存到 `tables/table-001.md`，`document.md` 中保留 `Table: ...` 引用。
- 可选图片理解信息写入 `image-enrichment.json`，ingest 会消费该文件生成 image artifact 的 `vision_summary` / `ocr_text`。
- 转换和校验问题写入 `ingest-log.json`。

## Failure Handling

常见失败：

- Docling 未安装：PDF/DOCX/XLSX/HTML 会返回 `hard_fail`，提示安装外部 `docling` CLI。
- 本地图片缺失：返回 `soft_fail`，保留原引用并记录搜索路径；批量 degraded text baseline 可继续。
- 图片理解不可用或失败：不阻断 ingest；跳过 `image-enrichment.json` 或记录单图失败信息。
- Docling 转换超时或失败：返回 `hard_fail`，记录短错误摘要；按任务目标决定是否使用 Markdown/text fallback。
- `document.md` 为空：返回 `hard_fail`。
- URL 被 403/404/反爬阻断：不要重试到失控；记录失败并替换来源或请求用户确认。

日志只用于排查，不要把完整私有文档内容粘贴给用户。

## Examples

用户说：“把这个 PDF 摄入 PKCS。”

执行：

```powershell
.venv\Scripts\pkcs.exe prepare-ingest C:\path\paper.pdf --output-root data/private/ingest-prep --slug paper
```

然后从 JSON 读取 `document_path`，调用 MCP：

```text
ingest_source(path="<document_path>", knowledge_type="document")
```

如果 MCP tool 当前不可用，使用 CLI 等价路径并说明：

```powershell
.venv\Scripts\pkcs.exe ingest <document_path> --knowledge-type document
```

用户说：“把这个 README 摄入 PKCS，图片也要能正常溯源。”

执行：

```powershell
.venv\Scripts\pkcs.exe prepare-ingest C:\path\README.md --output-root data/private/ingest-prep --slug readme
```

检查 JSON 中 `missing_local_images`。如果为 0，调用 `ingest_source` 摄入 `document_path`。

如果 `assets/` 中有图片，并且当前 agent 支持视觉理解，先生成 `image-enrichment.json`，再调用 `ingest_source`。

用户说：“按 manifest 批量摄入 100 篇公网资料。”

执行策略：

1. 下载验证 manifest，先不要 prepare/ingest。
2. 选 10-12 条 smoke batch 覆盖主要格式。
3. smoke 通过后每批最多 20 条执行 prepare；重格式限流。
4. 对每条写 append-only 状态报告。
5. 对 prepare 成功或可接受 soft fail 的 `document.md` 执行 MCP ingest；MCP 不可用时用 CLI 等价路径并说明。
