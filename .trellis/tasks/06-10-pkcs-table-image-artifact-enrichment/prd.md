# PKCS Table/Image Artifact Enrichment Brainstorm

## Goal

将 Markdown 中穿插出现的表格和图片从普通文本 chunking 升级为 artifact-aware retrieval 设计：Raw Archive 保真保存原文和资源，表格/图片解析为结构化 artifact，再派生适合 BM25/FTS 和 embedding 的 retrieval chunks，并能在召回时回到原文上下文。

## What I Already Know

* 当前 MVP parser 是 heading/line-based chunking：按 Markdown heading 分 section，再按字符/行切 chunk。
* 当前数据库只有 `sources`、`source_versions`、`chunks`、`citations` 等基础表，没有 table/image artifact 表。
* 当前 Markdown 表格会作为普通文本行进入 chunk；不会丢，但没有结构化 rows/columns，也不会 table-aware chunking。
* 当前 Markdown 图片引用只是普通文本；不会复制相对图片资产，不做 OCR，不做视觉理解。
* 后续 BM25 + embedding 检索需要更细粒度的 retrieval chunks，同时仍要保持 evidence 可追溯到 Raw Archive locator。
* 用户希望知识库主要服务有视觉理解能力的 agent，并考虑是否可在 ingest 时利用 Codex 的视觉能力完成图片 OCR、视觉理解和对象化。

## Current Design Summary

### Three-Layer Model

The design has three physical/logical layers:

```text
Raw Archive layer
  Original Markdown and copied local image assets. This is the evidence source of truth.

Artifact layer
  Structured table/image records discovered from Markdown blocks.

Retrieval chunk layer
  Searchable text projections for FTS/BM25 and future embedding retrieval.
```

Raw Archive content is never replaced by artifact objects. Artifacts and chunks are derived from the archived source version and must point back to `source_id`, `version_id`, and locator.

### Artifact-Aware Chunking

Markdown ingest 不应直接把整篇文档重新拼成字符串粗切，而应先解析成 block stream：

```text
heading block
paragraph block
table block
paragraph block
image block
paragraph block
```

chunker 遍历 block stream：

* 普通 paragraph/list/code/heading block 进入 narrative buffer。
* table/image block 作为原子 block，不被普通文本切块拆开。
* 遇到 table/image block 时创建最小 artifact record，并在 narrative buffer 中留下短 placeholder。
* artifact record 再派生自己的 retrieval chunks。
* 如果用户选择 enrichment，则后续补全 artifact 的 `summary`、`ocr_text`、`vision_summary` 等字段，并重建相关 derived chunks。

### Narrative Chunk

narrative chunk 负责保留文档叙事连续性和 artifact 所在位置，例如：

```text
# RAG Guide

这段说明 RAG 的整体流程。

[Table tbl_001: Component / Role, line 5-8]

上表说明了检索链路。

[Image img_001: RAG architecture, line 12]

这张图展示了从 query 到 answer 的路径。
```

召回 narrative chunk 时，Context Pack 可以按预算 hydrate 其引用的 artifact：

* Level 0：只返回 placeholder。
* Level 1：返回 artifact 摘要。
* Level 2：返回相关 rows / OCR / vision summary。
* Level 3：返回完整表格或完整图片派生内容。

默认推荐 Level 1-2，不默认展开超大表格或长 OCR。

### Placeholder And Artifact Linking

placeholder 主要是给人和 agent 读的，不应作为唯一可靠关联来源：

```text
[Table tbl_001: Component / Role, line 5-8]
[Image img_001: RAG architecture, line 12]
```

可靠关联应存入 chunk metadata，例如：

```json
{
  "chunk_kind": "narrative",
  "linked_artifacts": [
    {
      "artifact_type": "table",
      "artifact_id": "tbl_001",
      "locator": "line 5-8",
      "role": "inline_reference"
    },
    {
      "artifact_type": "image",
      "artifact_id": "img_001",
      "locator": "line 12",
      "role": "inline_reference"
    }
  ]
}
```

召回 narrative chunk 时，Context Pack builder 读取 `linked_artifacts`，再按 `artifact_type + artifact_id` 查询 table/image artifact，并按 query 和 budget hydrate 对象摘要、相关 rows、OCR 或 vision summary。

artifact-derived chunks 也必须反向指回对象和上下文：

```json
{
  "chunk_kind": "table_rows",
  "artifact_type": "table",
  "artifact_id": "tbl_001",
  "parent_narrative_chunk_id": "chunk_parent_001"
}
```

因此关系是：

```text
narrative chunk metadata.linked_artifacts -> artifact primary key
artifact -> source/version/locator and optional parent/nearby chunk ids
artifact-derived chunks -> artifact primary key and narrative context
```

### Table Artifact

表格原文保留在 Raw Archive Markdown 中；同时生成结构化表格对象：

```text
table_id
source_id
version_id
locator
heading_path
columns
rows
normalized_markdown
summary
```

基础 ingest 时就应创建 table artifact，而不是等 enrichment 再发现表格。第一版 artifact 可包含确定性字段：`columns`、`rows`、`normalized_markdown`、`heading_path`、`locator`。增强阶段只补充自然语言 `summary` 或更高质量的 schema interpretation。

表格派生 chunk：

* `table_summary`：表格标题、列名、简短描述。
* `table_rows`：按 row group 切，每个 chunk 重复表头和行内容。
* 可选 `table_column`：大表或配置表中按列生成辅助 chunk。

### Image Artifact

图片原文件应复制到 Raw Archive 附近或统一 asset archive；Markdown 原引用保留。

```text
image_id
source_id
version_id
locator
asset_path
alt_text
caption
nearby_text
ocr_text
vision_summary
```

基础 ingest 时就应创建 image artifact。第一版 artifact 可包含确定性字段：`asset_path`、`alt_text`、`caption`、`nearby_text`、`locator`。增强阶段再补充 `ocr_text`、`vision_summary`、`detected_entities` 等字段。

图片派生 chunk：

* `image_summary`：alt/caption/nearby_text/vision_summary。
* `image_ocr`：OCR 文本，长 OCR 可按 region/block 切。
* 可选 `image_labels`：架构图、流程图中的关键实体和边。

## Proposed Next Direction

下一步不应直接接 embedding 或视觉模型，而应先实现 artifact-aware ingest skeleton。推荐 MVP 范围：

1. Markdown block parser：识别 heading/paragraph/list/code/table/image block，并保留 line locator。
2. Artifact schema：新增 table/image artifact 表，建立 `chunks.artifact_type/artifact_id/chunk_kind` 或等价 metadata。
3. Narrative chunk metadata：保存 `linked_artifacts`，不要依赖 placeholder 正则解析。
4. Table MVP：Markdown table detection、columns/rows 解析、`normalized_markdown`、basic summary chunk、row-group chunks。
5. Image MVP：复制相对图片资产，提取 alt/caption/nearby_text，生成 image artifact 和 minimal image_summary chunk。
6. Context Pack hydration：召回 narrative chunk 时，能按 budget 展开 linked artifact 的基础摘要/相关内容。
7. Enrichment provider：预留 OCR/vision/table-summary provider 接口，但第一版 provider 可为空实现或只做 deterministic summary。

## Codex Vision Discussion

Codex CLI 支持把图片作为 prompt context（例如 `codex --image img.png "Summarize this diagram"`），也可以把 Codex CLI 作为 MCP server 暴露给其他 orchestrator。但这更适合人工辅助、原型验证和一次性 agent 工作流，不适合作为 PKCS 后端 ingest 的默认稳定依赖。

原因：

* Codex 是编码 agent surface，不是稳定的文档 OCR/vision enrichment API。
* Codex 调用可能涉及会话、审批、sandbox、上下文和交互式行为，不适合放进数据库 ingest 事务。
* 后端 ingest 需要幂等、可重试、可缓存、可审计、可批处理；Codex session 输出不如专用 provider 易控。
* 如果服务只对视觉 agent 使用，也仍然需要最低限度文本代理，否则 BM25/FTS/embedding 很难召回图片。

更合理的设计是抽象 `EnrichmentProvider`：

```text
TableSummaryProvider
OcrProvider
VisionSummaryProvider
```

可选实现：

* `none`：只做 deterministic extraction。
* `local_ocr`：Tesseract/PaddleOCR 等本地 OCR。
* `openai_vision_api`：通过可编程 API 生成 vision summary。
* `codex_agent_manual`：只作为离线/人工触发的实验 provider，不作为默认 ingest path。

确认后的策略：

```text
基础 ingest 永远不依赖 Codex/Claude Code 的视觉能力。
基础 ingest 生成最小 table/image artifacts 和基础 chunks。
用户选择增强时，agent 或其他 provider 读取 artifact 的 locator/asset_path，补全 artifact 字段，并重建增强 derived chunks。
```

Codex/Claude Code 可作为 `agent-assisted enrichment` 的可选 provider，用于人工触发或离线实验；不作为默认后端 ingest path，也不放入数据库事务主流程。

## Requirements (Evolving)

* Artifact-aware chunking 必须保持 Raw Archive 原文和 locator 可读回。
* 基础 ingest 必须创建最小 table/image artifacts；enhancement 是补全 artifact，不是重新发现 artifact。
* 表格和图片 placeholder 必须是原子 block，不能被 token/char 切块切断。
* placeholder 主要用于可读性；可靠关联必须写入 `linked_artifacts` metadata 或关联表。
* narrative chunk 超长时按 block flush，overlap 也按 block/heading/placeholder 做，不按字符硬切。
* table/image artifact chunk 被召回时，应能回到所属 narrative context。
* narrative chunk 被召回时，应能按预算 hydrate 其引用的 artifact 摘要或相关内容。
* 视觉/OCR/summary enrichment 必须可选、可缓存、可重跑，不能阻塞基础 ingest。
* Enrichment 更新 artifact 后，必须能重建对应 derived chunks，并标记 enrichment provider/version。

## Open Questions

* 下一步实现是否只覆盖 Markdown table + Markdown image references，还是同时处理 HTML/PDF 解析后的表格/图片？推荐只覆盖 Markdown。

## Acceptance Criteria

* [x] PRD 明确 table/image artifact-aware chunking 流程。
* [x] PRD 明确 Codex vision 的适用边界和不建议作为默认 ingest 依赖的理由。
* [x] PRD 明确基础 ingest 与可选 enrichment 的分层。
* [x] PRD 明确 placeholder 与 artifact 主键/metadata 的关联方式。
* [x] 决定下一步推荐实现范围：Markdown-only artifact-aware ingest skeleton。

## Definition of Done

* 设计方向记录到 Trellis task。
* MVP 范围和 out-of-scope 明确。
* 如进入实现，先补充数据库迁移、parser tests、retrieval tests。

## Out of Scope

* 当前讨论不立即实现 BM25、embedding、OCR 或 vision API。
* 不把 Codex CLI 直接绑定进生产 ingest path。
* 不在第一版 artifact-aware ingest 中处理 PDF/HTML/docx 解析。
* 不改变现有 M1+M2 MVP 行为。

## Decision (ADR-lite)

**Context**: PKCS 后续需要支持 BM25 + embedding 检索，并能处理 Markdown 中穿插的表格和图片。仅把表格/图片当普通文本会破坏召回质量；但直接依赖 Codex/Claude Code 做 ingest-time OCR/vision 会带来环境、幂等、批处理和失败恢复风险。

**Decision**:

* 采用 artifact-aware chunking。
* Raw Archive 保留原文和图片资产。
* 基础 ingest 创建最小 table/image artifacts 和基础 retrieval chunks。
* narrative chunks 使用 placeholder 保留叙事连续性，同时在 metadata 中保存 `linked_artifacts`。
* table/image derived chunks 通过 `artifact_id` 反向关联 artifact 和 narrative context。
* enrichment 是可选后处理；可由 agent-assisted provider、OpenAI Vision API、本地 OCR 或空 provider 实现。
* Codex/Claude Code 可用于人工/离线 agent-assisted enrichment，但不是默认 ingest 主路径。

**Consequences**:

* 系统基础 ingest 无额外模型配置也能运行。
* 后续可以逐步接入 Codex/Claude Code、OpenAI Vision API 或本地 OCR，不影响基础 schema。
* 检索和 Context Pack 需要支持 artifact hydration。
* 第一版实现需要数据库迁移和 parser 重构，复杂度高于当前 line-based chunking。

## Technical Notes

* 当前 parser：`src/pkcs/ingest/parsers.py`
* 当前 chunk model：`src/pkcs/db/models.py`
* Codex manual facts:
  * Codex CLI supports image inputs via `codex --image img.png "..."`.
  * Codex can run as an MCP server exposing `codex` and `codex-reply`.
  * These capabilities are useful for agent workflows, not a substitute for a deterministic backend enrichment provider.
