---
name: pkcs-ingest
description: "当用户明确要求把本地 Markdown、PDF、DOCX、XLSX、HTML 等单文件资料摄入 PKCS/知识库时使用。该 skill 使用项目命令 `uv run pkcs prepare-ingest` 生成 normalized Markdown package，然后调用 PKCS MCP `ingest_source` 摄入生成的 document.md。"
---

# PKCS Ingest

## Overview

这个 skill 是 PKCS 文档摄入入口。实际链路是：

```text
用户提供本地文件
  -> agent 运行 uv run pkcs prepare-ingest
  -> 生成 document.md + assets/ + tables/ + source-info.json + ingest-log.json
  -> agent 根据 assets/ 中的本地图片生成可选 image-enrichment.json
  -> agent 调用 MCP ingest_source(path=document.md)
  -> 返回摄入结果
```

用户入口是 skill；`prepare-ingest` 只负责 pre-ingest 规范化，MCP `ingest_source` 负责真正写入 PKCS。

## Supported Inputs

MVP 支持本地单文件：

- `.md`, `.markdown`, `.mdx`
- `.pdf`
- `.docx`
- `.xlsx`
- `.html`, `.htm`

Markdown 输入不需要 Docling。PDF/DOCX/XLSX/HTML 依赖外部 `docling` CLI；Docling 不属于 PKCS 主依赖，也不要求 MCP server 启动时加载。

## Workflow

### 1. Prepare Package

在仓库根目录运行：

```powershell
uv run pkcs prepare-ingest <source-path> --output-root data/private/ingest-prep
```

可选参数：

```powershell
uv run pkcs prepare-ingest <source-path> `
  --output-root data/private/ingest-prep `
  --slug <readable-name> `
  --timeout-seconds 300
```

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

- `success`: 继续调用 MCP ingest。
- `success_with_warnings`: 继续调用 MCP ingest，并向用户报告 warning。
- `soft_fail`: 默认暂停，说明 warning；用户接受降级摄入后再继续。
- `hard_fail`: 停止，报告 `errors` 和 `ingest_log_path`。

### 2. Enrich Local Images

如果 package 的 `assets/` 中存在本地图片，且当前 agent CLI 使用的模型支持图片理解，则在调用 MCP ingest 前分析这些图片并写入：

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

如果当前 agent 不具备图片理解能力，或者图片分析失败，可以跳过该文件，继续 MCP ingest。PKCS 会保留 Markdown 中已有的 alt/caption/nearby 信息。

### 3. Call MCP Ingest

`prepare-ingest` 成功，且可选图片理解步骤完成后，调用 PKCS MCP tool：

```text
ingest_source(
  path="<document_path from prepare-ingest JSON>",
  knowledge_type="document",
  canonical_key="<optional user-provided key>"
)
```

`canonical_key` 仅在用户明确提供稳定身份时传入。用户没有提供时，让 PKCS 自动生成。

### 4. Report Result

向用户报告：

- `prepare-ingest` status
- `document_path`
- local image / remote image / missing image 计数
- `image-enrichment.json` 是否生成；如未生成，说明已按普通图片 metadata 降级摄入
- inline table / sidecar table 计数
- MCP ingest status、`source_id`、`version_id`、`canonical_key`
- 影响资料保真度的 warnings

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
- 可选图片理解信息写入 `image-enrichment.json`，MCP ingest 会消费该文件生成 image artifact 的 `vision_summary` / `ocr_text`。
- 转换和校验问题写入 `ingest-log.json`。

## Failure Handling

常见失败：

- Docling 未安装：PDF/DOCX/XLSX/HTML 会返回 `hard_fail`，提示安装外部 `docling` CLI。
- 本地图片缺失：返回 `soft_fail`，保留原引用并记录搜索路径。
- 图片理解不可用或失败：不阻断 ingest；跳过 `image-enrichment.json` 或记录单图失败信息。
- Docling 转换超时或失败：返回 `hard_fail`，记录短错误摘要。
- `document.md` 为空：返回 `hard_fail`。

日志只用于排查，不要把完整私有文档内容粘贴给用户。

## Examples

用户说：“把这个 PDF 摄入 PKCS。”

执行：

```powershell
uv run pkcs prepare-ingest C:\path\paper.pdf --output-root data/private/ingest-prep --slug paper
```

然后从 JSON 读取 `document_path`，调用 MCP：

```text
ingest_source(path="<document_path>", knowledge_type="document")
```

用户说：“把这个 README 摄入 PKCS，图片也要能正常溯源。”

执行：

```powershell
uv run pkcs prepare-ingest C:\path\README.md --output-root data/private/ingest-prep --slug readme
```

检查 JSON 中 `missing_local_images`。如果为 0，调用 MCP `ingest_source` 摄入 `document_path`。

如果 `assets/` 中有图片，并且当前 agent 支持视觉理解，先生成 `image-enrichment.json`，再调用 MCP `ingest_source`。
