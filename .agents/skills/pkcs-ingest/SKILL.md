---
name: pkcs-ingest
description: "当用户明确要求把文件、目录、GitHub 文档、Markdown、PDF、DOCX、PPTX、XLSX、HTML 或其他文档摄入 PKCS/知识库时使用。该 skill 负责把输入整理为 PKCS MCP ingest 可接收的 normalized Markdown：转换格式、统一本地图片到 assets/、处理表格侧车文件、记录日志，并调用 PKCS MCP ingest 或 CLI fallback。"
---

# PKCS Ingest

## Overview

这个 skill 是 PKCS 文档摄入入口流程。它先把用户给的资料准备成一个本地 normalized Markdown 包，校验本地图片和表格引用，再把准备好的 `document.md` 交给项目 MCP tool `ingest_source`。

流程聚焦在文档准备、校验和 ingest 调用。用户接着要求 search、`read_source` 或 Context Pack 检查时，再按对应流程处理。

## Input Policy

用户明确要求把资料 ingest、import、add 或 load 到 PKCS 时，使用本 skill。

支持的输入：

- 已存在的 Markdown 或 text 文件。
- 本地非递归文档目录。
- 用户提供的 GitHub/repository 文档路径。
- PDF、DOCX、PPTX、XLSX、HTML、CSV、EPUB、图片型文档，或其他可转换为 Markdown 的 office-like 文档格式。

远程资料只抓取用户指定的 URL 或 repository path。对于 repository Markdown，保留足够的本地目录上下文，以便解析相对本地图片资源。

## Output Package

每份源文档创建一个准备目录：

```text
data/private/ingest-prep/YYYY-MM-DD-source-slug/
  document.md
  assets/
  tables/
  source-info.json
  ingest-log.json
```

传给 PKCS ingest 的文件是 `document.md`。准备目录只负责整理输入；`ingest_source` 运行后，由 PKCS 自己维护内部 archive。

`source-info.json` 建议包含：

- `source_kind`: `local_file`、`local_directory`、`url` 或 `repository_path`
- `original_name`
- `source_format`
- `normalized_format`: `md`
- `converter`
- `converter_version`，如果可获得
- `prepared_at`

`ingest-log.json` 建议包含：

- 每一步状态和耗时
- warnings 与 failures
- 本地图片从原始引用到 `assets/...` 的映射
- 表格从原始位置或 sheet name 到 `tables/...` 的映射
- 最终 MCP 或 CLI ingest report

## Workflow

### 1. Inspect The Source

在改动文件前，先识别资料类型和转换路径。确认：

- 输入路径或 URL 存在且可访问
- 源格式和文件数量
- 输入是一份文档还是小批量文档
- 用户是否提供了 `canonical_key`

本地目录默认只处理当前层级的文件。Repository 文档场景下，选定 Markdown 文件和解析本地 asset 引用所需的目录。

### 2. Convert To Markdown

对于 `.md`、`.markdown`、`.mdx`，保留 Markdown 内容，然后执行图片和表格规范化。

对于 `.txt`，创建 `document.md`，保留原文本内容；如果文件没有标题，用文件名生成一个简单标题。

其他格式使用 Docling 作为 v1 默认转换器。整个流程优先使用一个转换器，确保转换行为清晰、可排查。

常用 Docling CLI 形态：

```powershell
docling --to md --image-export-mode referenced --output <prep-dir> <source>
```

HTML 或 EPUB 中包含本地图片资源时，启用本地图片抓取：

```powershell
docling --to md --image-export-mode referenced --html-image-fetch local --output <prep-dir> <source>
```

转换完成后，把选定的 Markdown 输出移动或重命名为 `document.md`，再执行与原生 Markdown 相同的规范化和校验。

### 3. Normalize Images

`document.md` 引用的所有本地图片都应位于 `assets/` 下，并同步改写 Markdown 内部引用。

识别常见 Markdown 图片写法：

- 标准图片：`![alt](images/a.png)`
- 链接包裹图片：`[![alt](images/a.png)](https://example.com)`
- blockquote 图片：`> ![alt](images/a.png)`
- reference-style 图片：`![alt][image-id]` 加 `[image-id]: images/a.png`
- HTML 图片：`<img src="images/a.png" alt="alt">`

远程图片 URL 保持 URL 形式。在日志中统计远程图片数量，默认不下载远程图片。

本地图片处理规则：

- 从 Markdown 文件所在目录解析相对路径。
- 将每个存在的本地图片复制到 `assets/`。
- 将 Markdown 引用改写为 `assets/<filename>`。
- 第一份同名文件保留原 basename，例如 `assets/logo.png`。
- 重名时追加简单数字后缀，例如 `assets/logo-2.png`、`assets/logo-3.png`。
- 每条映射都记录到 `ingest-log.json`。

本地图片引用无法解析时，记录原始引用和已搜索路径。默认标记为 `soft_fail`；用户接受降级摄入时，可继续执行 ingest。

### 4. Normalize Tables

可读且规模适中的 Markdown 表格保留为 Markdown table。

对于大表、spreadsheet sheet，或会让 `document.md` 过度膨胀的转换结果：

- 将表格保存为 `tables/` 下的侧车文件。
- 小型结构化表优先用 `.md`，大型表格数据优先用 `.csv`。
- 在 `document.md` 的原表格附近保留短引用，例如：

```markdown
Table: `tables/sheet-1.csv`
```

Excel workbook 保留 sheet 边界，文件名可使用 `tables/Sheet1.csv` 或 `tables/Sheet1.md`，并在 `ingest-log.json` 记录 sheet name。

### 5. Validate The Package

调用 ingest 前检查：

- `document.md` 存在且非空。
- 所有本地图片引用都指向 `assets/`。
- 所有 `assets/...` 引用在磁盘上存在。
- 远程图片 URL 已单独计数。
- `tables/` 下的表格侧车引用存在。
- Markdown 可以被项目 ingest 路径解析。

需要检查 artifact trace 时运行：

```powershell
uv run pkcs trace-ingest <prep-dir>\document.md --knowledge-type document --output <prep-dir>\trace.json
```

用 trace 核对 image/table artifact 数量和 unsupported diagnostics。

### 6. Call PKCS Ingest

优先调用 PKCS MCP tool：

```text
ingest_source(path=<prep-dir>/document.md, knowledge_type="document", canonical_key=<optional>)
```

MCP 不可用时使用项目 CLI fallback：

```powershell
uv run pkcs ingest <prep-dir>\document.md --knowledge-type document
```

用户提供明确 canonical key 时：

```powershell
uv run pkcs ingest <prep-dir>\document.md --knowledge-type document --canonical-key <canonical-key>
```

将返回的 report 写入 `ingest-log.json`。

### 7. Report Back

向用户返回简洁结果：

- 准备目录
- normalized Markdown 路径
- 本地图片数量、远程图片数量、缺失本地图片数量
- inline table 数量和 sidecar table 数量
- MCP 或 CLI report 中的 ingest status 与 ID
- 影响资料保真度的 warnings

## Status Levels

`ingest-log.json` 使用这些准备状态：

- `success`: 已转换、规范化、校验并完成 ingest。
- `success_with_warnings`: 已 ingest，但存在不阻断的保真度 warning。
- `soft_fail`: 准备阶段发现可修复问题，例如缺失本地 asset 或转换细节不支持。
- `hard_fail`: 源无法访问、转换失败、无法生成 `document.md`，或 ingest 失败。

每条 warning 或 failure 都应包含简短原因、相关输入名和产生问题的步骤。日志中保留状态、计数、路径映射和短错误摘要，避免写入完整私有文档内容。

## Converter Choice

非 Markdown 文档格式默认使用 Docling。它支持 Markdown 导出、referenced image 导出、表格抽取、OCR-capable 文档转换和常见 office 格式。

Docling 未安装时，报告缺失依赖和原计划执行的命令。Docling 对某类源输出不可用时，把失败细节写入 `ingest-log.json`，并建议创建聚焦的单独任务评估转换改进。

## Examples

用户说：“把这个 PDF 摄入 PKCS。”

预期流程：

1. 使用 Docling 将 PDF 转成 Markdown，并导出 referenced images。
2. 将本地图片移动到 `assets/`，并改写 Markdown 引用。
3. 小表保留 inline，大表保存到 `tables/`。
4. 校验 `document.md`。
5. 调用 `ingest_source`，`knowledge_type="document"`。

用户说：“把这个 GitHub README 摄入 PKCS，图片也要能正常溯源。”

预期流程：

1. 获取 README 和它引用的本地 asset 文件。
2. 远程图片 URL 保持原样。
3. 将本地 asset 复制到 `assets/`，重名时使用数字后缀。
4. 改写 `document.md` 里的图片引用。
5. 校验，必要时 trace，然后 ingest。
