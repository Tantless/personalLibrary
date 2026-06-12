# PKCS Explicit Markdown Block Graph Brainstorm

## Goal

将 Markdown ingest 主链路从当前隐式 `_RenderedEntry` 流升级为显式 `MarkdownBlock` / block graph 流程：先把原始 Markdown 解析成稳定的文本、表格、图片等 block 节点，再从 block graph 派生 artifact、narrative chunks、artifact chunks 和落库 metadata。目标是让表格/图片对象化、chunk overlap、artifact link、trace debug 和后续 enrichment 的语义更干净。

## Scope Decision

用户已确认：block graph 本轮只承担 **parser/chunk planner 的内部中间模型** 与 **trace/debug 可视化输出** 两个职责。

这不是新增知识层、不是持久化 graph，也不是新的查询对象。block 的价值是帮助系统把文档稳定切分成 narrative chunks 与 artifact-derived chunks，并在调试时能看清“原始 Markdown -> blocks -> artifacts -> chunks”的每一步是否符合设计。

因此 MVP 明确采用：

```text
transient internal block graph
  -> derive artifacts/chunks
  -> expose summary in trace-ingest
  -> persist only existing artifacts/chunks/citations metadata
```

不新增 `source_blocks` 数据表，不增加 block repository，不让 block 承担 search/read/context-pack 的一等持久化职责。

## What I Already Know

* 用户最初设想的链路是：原始 Markdown -> 识别文本域/图片域/表格域 -> 分成 block -> 图片/表格生成对象 -> 对象再 chunking -> 落库。
* 当前代码已经实现 Markdown-only artifact-aware ingest skeleton，但 parser 内部不是显式 block graph，而是 heading section + `_RenderedEntry` 临时流。
* 当前 `_RenderedEntry` 同时承担三件事：保留可渲染文本、替换 table/image placeholder、携带 `linked_artifact` metadata。
* 当前 chunk overlap 按 rendered entry 做，可能让同一个 artifact placeholder 出现在多个 narrative chunks 中，因此多个 narrative chunks 都会 linked 到同一个 artifact。
* 当前 table artifact 会派生 `table_summary` 和 `table_rows` chunks；image artifact 会派生 `image_summary` chunk。
* `trace-ingest` 已经能输出 input -> parser -> asset resolution -> ingest report -> database 的全链路 JSON，适合对比重构前后差异。
* 现有任务 `06-12-pkcs-comprehensive-markdown-image-block-parsing` 只负责更全面的图片语法识别，并明确不做 full `MarkdownBlock` AST。
* `markdown-it-py` 当前环境可 import，但尚未在 `pyproject.toml` 声明依赖；如作为正式 parser substrate，需要显式加入依赖。

## Is This The Same As Markdown AST Refactor?

不是完全一回事，但高度相关。

**Markdown AST 重构**通常指“用 Markdown parser 把语法解析成语法树/token stream”，例如 paragraph、blockquote、link、image、table、html block 等。这是语法层能力，回答的是“Markdown 文本里有什么结构”。

**显式 block graph**是 PKCS 的内部 ingest/chunk planning 模型，回答的是“这些结构如何辅助切 chunk、生成 artifact、建立调试可见的 link”。它需要比 Markdown AST 多出少量 PKCS 语义：

* stable `block_id`
* `block_type`：text、heading、list、code、table、image、html、blockquote 等
* `line_start` / `line_end` locator
* `heading_path`
* parent/child relationship
* artifact binding：哪个 block 生成哪个 table/image artifact
* caption/nearby/context block relationship
* chunk ownership：哪些 block 被哪个 narrative chunk 主拥有，哪些只是 overlap context
* trace/debug projection

所以关系是：

```text
Markdown AST/token stream = 可选的解析原材料
PKCS MarkdownBlock graph = transient ingest/chunk planning contract
```

实现上可以用 `markdown-it-py` 或其他 CommonMark/GFM parser 来帮助构建 block graph；但最终不应把第三方 AST 直接暴露给 ingest service、trace 或 Context Pack。PKCS 应该拥有自己的稳定 internal dataclass，并且只在解析和 trace 阶段使用。

## Current Flow

当前 Markdown document flow：

```text
raw markdown bytes
  -> splitlines()
  -> _markdown_sections() by heading
  -> _chunks_from_markdown_sections()
       -> scan section lines
       -> detect table lines
       -> detect standalone image line
       -> create ParsedTableArtifact / ParsedImageArtifact
       -> append _RenderedEntry placeholder
       -> append normal _RenderedEntry text lines
  -> _narrative_chunks_from_entries()
       -> chunk rendered entries by max chars
       -> overlap copies last entries
  -> _artifact_chunks()
       -> create table_summary/table_rows/image_summary chunks
  -> IngestService persists artifacts then chunks/citations
```

Strengths:

* 已能稳定创建 table/image artifact rows。
* Raw Archive、locator、derived chunks 和 metadata ID resolution 已走通。
* 改动小，测试已有覆盖。

Weaknesses:

* 没有一等公民的 block node；文本、表格、图片只是扫描过程中的副作用。
* placeholder 和 artifact link 与 chunk overlap 耦合。
* 难以区分 artifact 的 primary narrative owner 与 overlap context owner。
* 难以表达 linked image、caption block、blockquote image、HTML image、table caption 等复杂关系。
* trace 只能看到 parser output，不能看到“原始文档如何变成 blocks”的核心中间态。

## Proposed Explicit Block Graph Flow

目标流程：

```text
raw markdown bytes
  -> MarkdownBlockGraphBuilder
       -> MarkdownDocumentGraph
          -> blocks[]
          -> edges[]
          -> sections[]
          -> diagnostics[]
  -> ArtifactExtractor
       -> ParsedTableArtifact / ParsedImageArtifact
       -> ArtifactBinding(block_id, artifact_key, role, locator)
  -> ChunkPlanner
       -> narrative chunk plans by block ownership
       -> artifact-derived chunk plans by artifact binding
       -> explicit overlap/context refs
  -> ParsedSource
       -> ParsedChunk[]
       -> table_artifacts[]
       -> image_artifacts[]
       -> traceable block graph summary
  -> IngestService persists artifacts then chunks/citations
```

### Core Dataclasses

Initial internal dataclasses:

```python
@dataclass(frozen=True)
class MarkdownBlock:
    block_id: str
    block_type: str
    line_start: int
    line_end: int
    heading_path: list[str]
    raw_text: str
    normalized_text: str | None = None
    parent_block_id: str | None = None
    metadata_json: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class MarkdownBlockEdge:
    source_block_id: str
    target_block_id: str
    edge_type: str


@dataclass(frozen=True)
class MarkdownDocumentGraph:
    title: str
    blocks: list[MarkdownBlock]
    edges: list[MarkdownBlockEdge]
    diagnostics: list[dict[str, Any]] = field(default_factory=list)
```

Likely block types:

* `heading`
* `paragraph`
* `blockquote`
* `list`
* `code_fence`
* `table`
* `image`
* `html`
* `thematic_break`
* `blank`

Initial edge types:

* `contains`
* `follows`
* `caption_of`
* `nearby_context_of`
* `artifact_source_for`

### Artifact Binding

Artifact extraction should be based on block IDs, not placeholder text:

```python
@dataclass(frozen=True)
class ArtifactBinding:
    artifact_type: Literal["table", "image"]
    artifact_key: str
    source_block_id: str
    bound_block_ids: list[str]
    role: Literal["primary", "caption", "nearby_context"]
    locator: str
```

Examples:

* A Markdown table block produces `tbl_001` with `source_block_id="blk_012"`.
* A linked image block produces `img_001` with `source_block_id="blk_003"` and metadata containing outer link target.
* A caption line can be linked by edge `caption_of -> image block` and included in `bound_block_ids`.

### Chunk Planning

Narrative chunks should be planned from block ownership:

```text
narrative chunk
  primary_block_ids: [blk_001, blk_002, blk_003]
  overlap_block_ids: [blk_000]
  linked_artifacts:
    - artifact_key: tbl_001
      source_block_id: blk_002
      role: primary_reference
```

If a table placeholder appears in an overlap range, the chunk should preserve readable context but metadata should distinguish:

* `role=primary_reference` when the chunk owns the artifact block.
* `role=context_reference` when the artifact appears only because of overlap.

This resolves the current ambiguity where multiple chunks can appear equally linked to `tbl_002`.

Artifact-derived chunks should point back to:

* `artifact_key`
* `source_block_id`
* `bound_block_ids`
* `parent_narrative_chunk_key`

## Example From Current Linear Regression Doc

Current selected Markdown:

```md
[![ML for beginners - Understanding Linear Regression](https://img.youtube.com/vi/CRxFT8oTDMg/0.jpg)](https://youtu.be/CRxFT8oTDMg "ML for beginners - Understanding Linear Regression")

> 🎥 Click the image above for a short video overview of linear regression.

> Throughout this curriculum, ...
```

Current implicit implementation:

* This linked image is not detected as an image artifact because `_IMAGE_LINE_RE` only matches a whole line starting with `![alt](uri)`.
* The line stays inside a narrative chunk as normal Markdown text.
* No `img_XXX` object is created for the YouTube thumbnail.
* No explicit relation exists between the thumbnail line and the following blockquote caption.

Explicit block graph target:

```text
blk_001 image
  image_syntax=linked_markdown_image
  image_uri=https://img.youtube.com/vi/CRxFT8oTDMg/0.jpg
  outer_link_url=https://youtu.be/CRxFT8oTDMg
  alt_text=ML for beginners - Understanding Linear Regression

blk_002 blockquote
  raw_text=> 🎥 Click the image above...
  edge: blk_002 caption_of blk_001

blk_003 blockquote
  raw_text=> Throughout this curriculum...
  edge: blk_003 nearby_context_of blk_001
```

Then:

* `blk_001` creates `img_001`.
* `img_001.caption` comes from `blk_002`.
* `img_001.nearby_text` may include `blk_003`.
* narrative chunk contains a readable placeholder for `img_001`.
* `image_summary` chunk points to `source_block_id=blk_001` and parent narrative chunk.

## Feasible Approaches

### Approach A: Internal Block Graph, No New DB Table (Recommended MVP)

How it works:

* Add internal dataclasses for `MarkdownBlock`, `MarkdownBlockEdge`, `MarkdownDocumentGraph`, and `ArtifactBinding`.
* Refactor Markdown parser to build graph first, then derive existing `ParsedSource`.
* Keep existing DB schema: `sources`, `source_versions`, `chunks`, `citations`, `table_artifacts`, `image_artifacts`.
* Persist block refs in existing `metadata_json` fields.
* Update `trace-ingest` to include a `block_graph` stage.

Pros:

* Solves parser/chunker semantics without immediate migration.
* Lower blast radius than adding persistent block tables.
* Existing search, read_source, Context Pack and artifact tables keep working.
* Easy to compare old/new output with trace.
* 符合用户确认的低成本边界：block 只辅助 chunking 和 debug，不承担持久化知识职责。

Cons:

* Block graph is not queryable after ingest except through metadata snapshots.
* Rebuilding enrichment from old versions still requires re-parsing Raw Archive.

### Approach B: Persist Source Blocks In Database (Rejected For MVP)

How it works:

* Add `source_blocks` table keyed by `source_id/version_id/block_id`.
* Store block type, locator, heading path, raw/normalized preview, parent ID and metadata.
* Artifacts and chunks can reference `source_blocks.id`.

Pros:

* Best debug visibility and future enrichment auditability.
* Enables block-level reprocessing and future graph queries.
* Makes artifact/source block relationship first-class.

Cons:

* Requires migration and repository changes.
* Larger implementation and test surface.
* Could be premature before block model stabilizes.
* 超出用户当前目标：block 本质上只是辅助 chunk 划分，不应增加不必要的持久化成本。

### Approach C: Full Markdown AST Parser Replacement First

How it works:

* Add `markdown-it-py` or another parser as the primary Markdown parser.
* Convert token stream into PKCS block graph.
* Replace current table/image/list/code parsing in one larger parser rewrite.

Pros:

* Best syntax correctness path.
* Avoids growing line-scanner special cases.

Cons:

* Highest regression risk.
* Requires careful line map tests.
* Harder to split into small PR-sized steps.

## Recommendation

Use Approach A as the confirmed first implementation step:

```text
Internal explicit block graph
  + existing DB schema
  + metadata block refs
  + trace-ingest block_graph stage
```

Do not implement Approach B in this task. A persisted `source_blocks` table can be reconsidered only if a later requirement needs block-level reprocessing, querying, or audit beyond trace debugging.

This also means the existing image parsing task can stay focused:

* Image task: improve syntax detection and image block grouping.
* Block graph task: define and enforce the document-to-block-to-artifact-to-chunk contract.

The two can share parser substrate later, but they are not the same task.

## Requirements (Evolving)

* Markdown document ingest must build an explicit internal block graph before artifact and chunk derivation.
* Each block must have stable per-version `block_id`, `block_type`, line locator, heading path, raw text, and metadata.
* Parser must distinguish at least text-like blocks, code fences, tables, and images.
* Artifact extraction must create table/image artifacts from source block IDs, not from placeholder text.
* Narrative chunk metadata must include primary block IDs and overlap/context block IDs.
* `linked_artifacts` must distinguish primary artifact references from overlap/context references.
* Artifact-derived chunks must include `source_block_id`, `bound_block_ids`, `artifact_key`, and parent narrative chunk key/id.
* `trace-ingest` must expose block graph output before parser artifact/chunk output.
* Existing Raw Archive locator behavior must stay stable.
* Existing table/image artifact DB schema must remain unchanged for MVP.
* Block graph must be transient: no `source_blocks` table, no block repository, no block-level public API.

## Acceptance Criteria (Evolving)

* [x] A Markdown fixture can be parsed into explicit `MarkdownDocumentGraph` blocks with deterministic block IDs and line locators.
* [x] Existing table/image artifact fixture still creates table/image artifacts and derived chunks.
* [x] Narrative chunk metadata contains `primary_block_ids` and `overlap_block_ids`.
* [x] When overlap includes an artifact placeholder, metadata marks it as `context_reference` instead of another primary link.
* [x] Artifact-derived chunks include `source_block_id` and `bound_block_ids`.
* [x] `trace-ingest` includes a `block_graph` stage showing block counts, block types, locators, edges, and artifact bindings.
* [x] No database migration is added for block persistence.
* [x] Current Linear Regression fixture shows why the linked YouTube image is or is not detected, with block-level diagnostics.
* [x] Existing ingest/search/context-pack tests pass.

## Definition Of Done

* PRD accepted.
* Phase 2 context configured before implementation.
* Backend guidelines read before coding.
* Unit tests added for block graph building, chunk ownership, overlap artifact roles, and trace shape.
* Integration tests prove existing DB ingest still works.
* `uv run pytest` passes with PostgreSQL healthy.
* `git diff --check` passes.
* Relevant README/spec notes updated if parser contract changes.

## Out Of Scope

* OCR, vision summary, embedding or rerank.
* Persisted `source_blocks` table.
* Block repository, block search API, or block-level read API.
* PDF/HTML/docx source ingest.
* Full CommonMark/GFM conformance for every edge case in the first PR.
* Remote image downloading.
* Changing MCP tool output shape unless Context Pack hydration later needs it.

## Open Questions

* 暂无阻塞问题。范围已确认：内部 transient block graph，只用于 chunk planning 和 trace/debug，不持久化 block。

## Technical Notes

* Current parser: `src/pkcs/ingest/parsers.py`
* Current parser models: `src/pkcs/ingest/models.py`
* Current ingest persistence: `src/pkcs/ingest/service.py`
* Current trace: `src/pkcs/ingest/trace.py`
* Current tests: `tests/test_ingest.py`, `tests/test_ingest_trace.py`, `tests/test_context_pack.py`
* Prior artifact design: `.trellis/tasks/06-10-pkcs-table-image-artifact-enrichment/prd.md`
* Trace debug task: `.trellis/tasks/06-12-pkcs-artifact-ingest-trace-debug/prd.md`
* Image syntax planning task: `.trellis/tasks/06-12-pkcs-comprehensive-markdown-image-block-parsing/prd.md`
