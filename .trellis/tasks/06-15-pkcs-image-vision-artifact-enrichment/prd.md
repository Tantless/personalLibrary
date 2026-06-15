# brainstorm: PKCS image vision artifact enrichment

## Goal

完善 Markdown 图片 block 摄入后的 image artifact 内容生成能力：在不要求用户单独接入视觉模型 API、也不要求本地部署额外视觉服务的前提下，利用 agent CLI 已具备的多模态能力，为图片生成可入库、可追溯、可复用的视觉理解信息。

## What I already know

* 当前项目已经增强过 Markdown image block 识别，并能在 ingest trace / artifact 侧生成图片对象的结构信息。
* 当前缺口是图片内容理解：image 对象里还没有稳定的视觉语义描述、图表/截图内容摘要或可检索字段。
* 用户希望入口仍然围绕 `pkcs-ingest` skill：agent 先执行 pre-ingest，再调用 MCP ingest。
* 用户不希望普通使用者自行申请视觉模型 API，或本地部署视觉模型服务。
* 倾向方案是由具备多模态模型的 agent CLI 在 ingest 前处理图片，生成 image artifact 所需视觉理解信息。

## Assumptions (temporary)

* 图片理解信息应在 normalized Markdown package 或其旁车文件中落地，供后续 MCP ingest 使用。
* MCP ingest 本身不直接调用外部视觉模型；它只消费 pre-ingest 阶段已经准备好的结构化结果。
* 视觉理解结果需要可追溯到图片原始路径、normalized assets 路径和 Markdown block。

## Open Questions

* 无多模态能力、图片不可读、agent 生成旁车失败时，MVP 应如何降级和记录？

## Requirements (evolving)

* 支持对 Markdown 中已识别的本地图片 block 生成结构化视觉理解信息。
* 视觉理解应由 agent CLI 能力完成，而不是要求用户配置独立视觉 API 或本地服务。
* 结果应能被后续 MCP ingest 消费，并生成更完整的 image artifact。
* 用户入口保持为 `pkcs-ingest` skill：skill 编排 pre-ingest、图片理解、MCP ingest，而不是让用户手动拼接步骤。
* `prepare-ingest` / Docling 先生成标准 package；图片理解只处理 package 中已经规范化的本地图片资产。
* block 生成 image 对象时消费图片理解旁车信息，之后继续复用现有 chunking、artifact linking、raw archive、search/context pack 链路。
* `image-enrichment.json` v1 使用精简字段集：`asset_path`、`vision_summary`、`ocr_text`、`visual_type`、`key_elements`、`confidence`。

## Acceptance Criteria (evolving)

* [x] 现状已核清：当前 image block 做了什么、缺什么、已有预留点是什么。
* [x] 方案明确：pre-ingest 阶段如何生成视觉理解旁车数据，MCP ingest 如何消费。
* [x] MVP 字段明确：image 对象至少包含哪些视觉语义字段。
* [ ] 失败策略明确：无多模态能力、图片不可读、格式不支持时如何降级和记录。

## Definition of Done (team quality bar)

* Tests added/updated where implementation changes behavior.
* Lint / typecheck / test suite pass.
* README / `pkcs-ingest` skill updated after implementation is verified.
* Trellis task status and acceptance notes stay synchronized with repo state.

## Out of Scope (explicit)

* 不在本 task 中引入独立视觉模型服务。
* 不要求用户配置额外视觉模型 API key。
* 不把远程图片下载策略扩大到新的爬取范围。

## Technical Approach

目标闭环：

```text
用户调用 pkcs-ingest skill
  -> agent 运行 uv run pkcs prepare-ingest <source>
  -> Docling/Markdown normalizer 生成标准 package
       document.md
       assets/
       tables/
       source-info.json
       ingest-log.json
  -> agent 自己或派发子代理读取 assets/ 中的本地图片
  -> agent 生成 image-enrichment.json
  -> agent 调用 MCP ingest_source(path=document.md)
  -> Markdown block graph 识别 image block
  -> image artifact 创建时按图片路径 / block metadata 消费 image-enrichment.json
  -> 后续 chunking、artifact summary、artifact linking、raw archive、search/context pack 继续走现有链路
```

建议 package 形态：

```text
data/private/ingest-prep/YYYY-MM-DD-source-slug/
  document.md
  assets/
  tables/
  source-info.json
  ingest-log.json
  image-enrichment.json
```

`image-enrichment.json` 由 agent 生成，PKCS 只校验和消费。MVP 先以 normalized asset path 作为主匹配键，例如 `assets/diagram.png`；远程图片默认不做视觉理解，只保留已有 URI、alt/caption/nearby metadata。

### Image Enrichment Sidecar v1

MVP schema:

```json
{
  "schema_version": 1,
  "images": [
    {
      "asset_path": "assets/diagram.png",
      "vision_summary": "A system architecture diagram showing retrieval, ranking, and context assembly.",
      "ocr_text": "Retriever -> Reranker -> Context Pack",
      "visual_type": "diagram",
      "key_elements": ["Retriever", "Reranker", "Context Pack"],
      "confidence": "high"
    }
  ]
}
```

字段约束：

* `asset_path`: 必填，使用 package 内 normalized path，例如 `assets/diagram.png`。MVP 主匹配键。
* `vision_summary`: 必填，面向检索和上下文生成的自然语言摘要。
* `ocr_text`: 可为空字符串；有可读文字时提取图片内文字。
* `visual_type`: 枚举建议为 `diagram`、`chart`、`screenshot`、`photo`、`other`。
* `key_elements`: 关键对象、标签、坐标轴、UI 元素、实体名等。
* `confidence`: 枚举为 `high`、`medium`、`low`，用于记录 agent 对视觉理解可靠性的自评。

## Decision (ADR-lite)

**Context**: PKCS 已能识别 Markdown 图片 block 并持久化 image artifact，但视觉语义字段没有生成来源。用户希望复用 agent CLI 的多模态能力，而不是让普通用户额外接入视觉模型 API 或部署本地服务。

**Decision**: 采用 agent-generated sidecar 方案。`pkcs-ingest` skill 编排完整链路：先用 `prepare-ingest` 生成标准 package，再由 agent/子代理分析本地图片并写入 `image-enrichment.json`，最后调用 MCP `ingest_source`。MCP ingest 保持确定性，只消费旁车数据。

**Consequences**: 方案对 Codex / Claude Code / OpenCode 更友好，避免把视觉模型依赖塞进 MCP server。代价是实现时需要定义稳定的旁车 schema、匹配规则和降级日志，并更新 skill 教会 agent 生成该文件。

## Technical Notes

### Current Implementation Status

当前不是“一点都没做”。已有内容分三层：

* Markdown block 层：`src/pkcs/ingest/parsers.py` 已把常见图片语法提升为 `block_type=image`，并生成 `ParsedImageArtifact`。支持 standalone / blockquote / linked Markdown image / HTML img / reference image 等语法，且会绑定 caption / nearby text。
* 持久化层：`src/pkcs/db/models.py` 的 `ImageArtifact` 已有 `ocr_text`、`vision_summary`、`metadata_json` 字段，repository 创建接口也能接收 `ocr_text` 和 `vision_summary`。
* trace/debug 层：`src/pkcs/ingest/trace.py` 已暴露 `ocr_text_present`、`vision_summary_present`，README 也明确当前 OCR 和 vision summaries 尚未实现。

当前缺口：

* `src/pkcs/ingest/models.py` 的 `ParsedImageArtifact` 只有 `original_uri`、`alt_text`、`caption`、`nearby_text`、`metadata_json`，没有 `ocr_text` / `vision_summary` 字段。
* `src/pkcs/ingest/service.py` 创建 image artifact 时只传 `asset_path`、`alt_text`、`caption`、`nearby_text` 和 metadata，没有传 OCR/vision 结果。
* `src/pkcs/ingest/parsers.py` 的 image summary chunk 只渲染 URI、locator、alt、caption、nearby text，没有视觉模型生成的内容。
* `prepare-ingest` 当前只做格式转换、assets 归一化、tables sidecar，没有生成 image enrichment sidecar。

### Research Notes

Relevant current tool capabilities:

* Codex CLI supports image inputs via paste / `-i` / `--image`, and supports subagents. It also supports `codex exec --json` and `--output-schema` for machine-readable automation.
  * https://developers.openai.com/codex/cli/features
  * https://developers.openai.com/codex/noninteractive
* Claude Code official docs support image workflows via drag/drop, paste, or providing a local image path.
  * https://code.claude.com/docs/en/common-workflows
* OpenCode official docs say images can be dragged into the terminal and scanned into the prompt.
  * https://opencode.ai/docs/
* MCP tool results can include image content blocks, but this project’s preferred direction should keep MCP ingest deterministic and have it consume prepared structured enrichment rather than ask MCP server to invoke a model.
  * https://modelcontextprotocol.io/specification/draft/server/tools

### Feasible Approaches

**Approach A: Agent-generated enrichment sidecar during pre-ingest** (recommended)

* `prepare-ingest` continues to generate `document.md` and `assets/`.
* The `pkcs-ingest` skill asks the current agent CLI to analyze local images from the prepared package and write a deterministic sidecar, for example `image-enrichment.json`.
* MCP ingest reads `image-enrichment.json` next to `document.md`, matches entries by normalized asset path / original URI / block metadata, and persists `vision_summary`, optional `ocr_text`, and additional metadata.
* This keeps model usage in the agent layer and keeps PKCS server deterministic.

**Approach B: New PKCS command shells out to Codex CLI**

* Add a project command such as `uv run pkcs enrich-images <prep-dir>` that invokes `codex exec --image ... --output-schema ...`.
* This is more automated for Codex specifically, but less portable across Claude Code / OpenCode and couples PKCS to a specific CLI contract.

**Approach C: MCP server returns image content and asks client/model to enrich**

* Add MCP tools/resources that return image bytes or resource links for image artifacts.
* This aligns with MCP image content support, but makes ingest a multi-turn model/client protocol and weakens deterministic ingest behavior.

Recommended MVP direction: Approach A first, with a sidecar schema stable enough that different agent CLIs can produce it.
