# PKCS Comprehensive Markdown Image Block Parsing Brainstorm

## Goal

设计一套更全面的 Markdown 图片识别与 image block 划分方案，让 PKCS 不只识别独立行 `![alt](path)`，也能识别真实技术文档中常见的 blockquote 图片、图片链接、HTML `<img>`、reference image，以及图片后紧跟的说明段落，并将它们稳定对象化为 `image_artifacts` 与 `image_summary` chunks。

## What I Already Know

* 用户发现 `ML-For-Beginners/2-Regression/3-Linear/README.md` 中有多种图片写法，但当前只识别 1 张 standalone Markdown image。
* 当前 parser 只匹配 `^\s*!\[...\]\(...\)\s*$`，即整行只有普通 Markdown 图片。
* 当前未识别的真实写法包括：
  * blockquote image：`>![calculate the slope](images/slope.png)`
  * linked image：`[![ML for beginners ...](https://img.youtube.com/.../0.jpg)](https://youtu.be/... "title")`
  * HTML image：`<img alt="Average price by month" src="../2-Data/images/barchart.png" width="50%"/>`
* 用户希望 linked image 及其下面的说明段落，例如 `> 🎥 Click the image above...`，可整体划为 image block。
* 当前 `ParsedImageArtifact` 已有 `original_uri`、`alt_text`、`caption`、`nearby_text` 字段，可以承载更多 deterministic metadata；数据库也已有 `caption`、`nearby_text`。
* 当前实现中 trace 工具已经能暴露 parser counts、asset resolution、database rows，适合用于本任务验收。
* 近期显式 block graph 任务已完成：Markdown 摄入现在先生成 transient `ParsedMarkdownBlockGraph`，再从 block graph 生成 narrative chunks、artifact bindings、artifact summary chunks。
* 当前 graph 已有 `block_id`、`block_type`、`follows` edges、`artifact_bindings`、`source_block_id`、`bound_block_ids`，并通过 trace v2 暴露。
* 当前 standalone `![alt](path)` 已成为 `block_type=image`，但 `[![alt](thumb)](target)` 仍是 `paragraph`，`<img ...>` 仍是 `html`，只在 diagnostics 中标记 `unsupported_linked_markdown_image` / `unsupported_html_image`。
* 当前 artifact 提取只消费 `block_type=image` 的 block；因此 image 增强的最小改动点是把更多可见图片语法提升为 image block，而不是另建一套并行 artifact 解析链路。

## Research Notes

### Common Markdown / GFM Conventions

* GFM 是 CommonMark 的严格超集，并以 CommonMark 语法为基础。
* Markdown 图片本质上是 inline 结构，不是 block 结构；标准图片可以出现在 paragraph、blockquote、list item、link text 等上下文中。
* GFM inline link 允许 link text 内含 inline nodes，因此 `[![alt](image)](target)` 合法：外层是 link，内层是 image。
* GFM 支持 raw HTML；真实 README 中常用 `<img src="...">` 来控制宽度/高度。
* GitLab 文档也明确说明 image 可使用 inline/reference link 形式，并且可以用 HTML `<img>` 来设置尺寸。

Sources:

* GFM specification: https://github.github.com/gfm/
* GitLab Markdown images docs: https://docs.gitlab.com/user/markdown/

### Repo Constraints

* Parser layer must return plain dataclasses and must not write DB/filesystem.
* Ingest service owns artifact row creation, asset archive copying, and metadata ID resolution.
* Context Pack hydration must continue resolving artifacts via `metadata_json.artifact_id`, not by parsing placeholder text.
* Current project has `markdown_it` importable in the environment but not declared in `pyproject.toml`; using it should add an explicit dependency.
* Current line-based parser preserves simple `line N-M` locators; any AST approach must preserve source line mapping.
* After the explicit block graph change, `ParsedMarkdownBlockGraph` is the ingest parser's internal structure contract for Markdown artifacts. New image recognition should integrate there first.

## Recent Code Delta After Explicit Block Graph

Recent commits changed the implementation boundary for this task:

* `a1886d1 docs: plan explicit markdown block graph` / `20cf3db docs: confirm transient block graph scope` defined the graph as transient, not persisted.
* `7e209c1 feat: add transient markdown block graph` added `ParsedMarkdownBlock`, `ParsedMarkdownBlockEdge`, `ParsedArtifactBinding`, and `ParsedMarkdownBlockGraph`; parser output now carries `markdown_block_graph`.
* `11f7699 docs: complete markdown block graph task` recorded acceptance for trace v2. The Linear Regression README trace shows `blocks=298`, `artifact_bindings=3`, and diagnostics including unsupported linked/HTML images.

Current code path:

```text
Markdown sections
  -> _build_markdown_block_graph()
  -> _artifacts_from_block_graph()
  -> _rendered_block_entries()
  -> _narrative_chunks_from_blocks()
  -> _artifact_chunks()
  -> ingest service persistence
```

Implication for this task:

* Image recognition should be implemented as block graph classification/enrichment.
* `unsupported_linked_markdown_image` and `unsupported_html_image` should become regression fixtures: after this task, those visible images should become `image` blocks and image artifacts.
* Caption/nearby grouping should be represented through `bound_block_ids`, artifact metadata, and trace output, not only by concatenating nearby raw text.

## Proposed Image Recognition Model

### Two-Level Model

Use two levels instead of one regex:

```text
Image inline candidate
  A concrete image occurrence found inside Markdown inline content or HTML.

Image block
  A display-oriented block centered on one primary image candidate, optionally including caption/callout lines that describe it.
```

This matters because Markdown images are syntactically inline, but PKCS retrieval wants object-level blocks.

### Image Inline Candidate Types

MVP should recognize these deterministic forms:

| Type | Example | Fields |
| --- | --- | --- |
| `markdown_image` | `![alt](path "title")` | `alt_text`, `original_uri`, `title` |
| `blockquote_markdown_image` | `> ![alt](path)` | same as above, plus `container=blockquote` |
| `linked_markdown_image` | `[![alt](thumb.jpg)](video-url "title")` | image URI + outer link target/title |
| `reference_image` | `![alt][id]` + `[id]: path "title"` | resolved URI/title + reference id |
| `collapsed_reference_image` | `![alt][]` + `[alt]: path` | resolved URI/title |
| `shortcut_reference_image` | `![alt]` + `[alt]: path` | resolved URI/title |
| `html_img` | `<img alt="x" src="path" width="50%">` | `src`, `alt`, dimensions/attrs |
| `linked_html_img` | `<a href="..."><img src="..."></a>` | image src + outer link target |

Explicitly avoid detecting plain links to image files as image artifacts in MVP unless they are visibly embedded as images, because `[diagram](diagram.png)` may be a download link rather than displayed image.

### Image Block Grouping Rules

After candidate detection, promote a candidate to an image block when its containing rendered line/block is image-dominant.

Image-dominant examples:

```md
![alt](image.png)
```

```md
> ![alt](image.png)
```

```md
[![alt](thumb.jpg)](https://youtu.be/...)
```

```html
<img alt="Average price" src="images/chart.png" width="50%"/>
```

Then extend the image block with caption lines using bounded, deterministic rules:

* Include immediately following blockquote lines if they refer to the image/video above.
* Include immediately following italic/emphasis caption paragraphs such as `*Figure 1: ...*`.
* Include one immediately preceding short paragraph only as `nearby_text`, not as caption, unless it starts with `Figure`, `图`, `Caption`, or `Image`.
* Stop at blank line followed by heading/table/code block/another image block.
* Never cross section boundaries.
* Never include fenced code content.
* Default max caption extension: 3 nonblank lines or 600 chars.

For the user example:

```md
[![ML for beginners - Understanding Linear Regression](https://img.youtube.com/vi/CRxFT8oTDMg/0.jpg)](https://youtu.be/CRxFT8oTDMg "ML for beginners - Understanding Linear Regression")

> 🎥 Click the image above for a short video overview of linear regression.

> Throughout this curriculum, ...
```

Recommended block split:

* Image candidate: YouTube thumbnail image.
* Outer link target: `https://youtu.be/CRxFT8oTDMg`.
* Caption: first blockquote line, because it explicitly says "Click the image above".
* Nearby text: second blockquote line, because it is related learning-note context but broader than the image caption.
* Locator: line range covering image line through included caption/nearby lines.

### ParsedImageArtifact Metadata

No new DB columns required for MVP. Store extra deterministic fields in `metadata_json`:

```json
{
  "image_syntax": "linked_markdown_image",
  "container": "paragraph",
  "outer_link_url": "https://youtu.be/CRxFT8oTDMg",
  "outer_link_title": "ML for beginners - Understanding Linear Regression",
  "image_title": null,
  "html_attrs": {},
  "caption_lines": ["line 24"],
  "nearby_text_lines": ["line 26"]
}
```

`ParsedImageArtifact` may need a `metadata_json` field so parser can pass this metadata to ingest service and repository.

## Feasible Approaches

### Approach A: Enhance Existing Transient Block Graph (Recommended)

How it works:

* Keep `ParsedMarkdownBlockGraph` as the single Markdown ingest substrate.
* Replace the current single `_IMAGE_LINE_RE` branch with an image candidate classifier that runs before generic paragraph/html/blockquotes are emitted.
* Classify standalone, blockquote, linked Markdown image, reference image, HTML `<img>`, and linked HTML image as `block_type=image` when the rendered block is image-dominant.
* Store syntax details in `ParsedMarkdownBlock.metadata_json`: `image_syntax`, `container`, `original_uri`, `alt_text`, `image_title`, `outer_link_url`, `outer_link_title`, `html_attrs`, and reference id when present.
* Extend artifact binding from one source block to multiple bound blocks when caption/nearby blocks are attached.

Pros:

* Fits the current parser architecture after the explicit block graph change.
* No new explicit dependency.
* Easy to keep line locators.
* Trace v2 can show exactly where classification, binding, and artifact creation happened.
* Lowest regression risk because table parsing, chunking, and DB persistence keep their current contracts.

Cons:

* Targeted inline parsing must be carefully bounded.
* Some CommonMark edge cases around nested brackets/escaped parens may remain out of scope.

### Approach B: Block Graph First, `markdown-it-py` As Inline Helper

How it works:

* Add explicit dependency on `markdown-it-py`.
* Keep `_build_markdown_block_graph()` as the owner of block creation.
* Use `markdown-it-py` only inside image candidate classification for Markdown inline forms that are painful to parse with regex.
* Continue using stdlib HTML parsing for `<img>` attrs.

Pros:

* Matches real Markdown structure better than regex.
* Naturally handles linked images and reference-style images.
* Reduces custom parsing edge cases while preserving the graph-first architecture.

Cons:

* Adds a declared dependency.
* Need careful line map handling and tests.
* Could be heavier than necessary if current target fixtures can be covered by small deterministic parsers.

### Approach C: Separate Token-Stream Image Parser

How it works:

* Build a separate `MarkdownImageBlockParser` from `markdown-it-py` tokens.
* Merge its output back into the current line/block parser.

Pros:

* Strong Markdown syntax coverage.
* Can be developed as a focused helper.

Cons:

* Creates a second parser authority beside the block graph.
* More merge logic and higher risk of locator/chunk disagreement.
* Less aligned with the just-completed explicit block graph work.

## Recommendation

Use Approach A for MVP: enhance the existing transient `ParsedMarkdownBlockGraph` so visible image syntax becomes `block_type=image` with richer metadata and artifact bindings.

Only add `markdown-it-py` if targeted parsing cannot cover the accepted fixtures without fragile code. If added, it should be an inline candidate helper inside block graph construction, not a parallel ingest pipeline.

## User Scope Decision

User selected option 1 on 2026-06-12:

* Implement image recognition enhancement only.
* Do not introduce a full public/internal `MarkdownBlock` AST in this task.
* Keep table parsing and the rest of the chunking architecture scoped to the current implementation unless a small adapter is required for image blocks.

## Decision (ADR-lite)

**Context**: Real Markdown documents commonly use linked images, blockquote images, reference images, and HTML `<img>` tags. The current parser now has a transient Markdown block graph, but only whole-line plain Markdown image syntax is classified as `block_type=image`; linked and HTML images are diagnostics-only.

**Decision**: Use the existing transient `ParsedMarkdownBlockGraph` as the implementation surface. Add richer image candidate classification, image block metadata, and bounded caption/nearby block binding there. Do not create a separate parser pipeline and do not persist source blocks.

**Consequences**:

* The immediate gap in image artifact coverage can be fixed with limited blast radius and direct trace visibility.
* Table parsing, narrative chunking, artifact persistence, and Context Pack hydration remain stable.
* `bound_block_ids` becomes the mechanism for explaining which caption/nearby blocks belong to an image artifact.
* Some exotic Markdown edge cases remain out of scope unless `markdown-it-py` is deliberately introduced as a helper.

## Requirements (Evolving)

* Recognize standalone Markdown image lines.
* Recognize blockquote Markdown image lines.
* Recognize linked image lines such as `[![alt](thumb)](target "title")`.
* Recognize reference-style Markdown images when reference definitions exist in the same document.
* Recognize single-line and simple multi-line HTML `<img>` tags.
* Recognize linked HTML image patterns when `<a>` wraps `<img>`.
* Group image-dominant lines plus immediately related caption/callout lines into one image block.
* Promote supported linked/HTML/reference image syntax to `block_type=image` in `ParsedMarkdownBlockGraph` instead of emitting unsupported diagnostics.
* Preserve `source_block_id` and expand `bound_block_ids` when caption/nearby blocks are attached to an image artifact.
* Preserve Raw Archive source text and line locator for every image artifact.
* Continue copying local image assets through ingest service; remote image URLs should become artifacts with `asset_path=None`.
* Store syntax/container/link/dimension metadata in artifact metadata.
* Update `trace-ingest` so it shows detected image syntax and block locator.

## Acceptance Criteria (Evolving)

* [ ] A synthetic fixture with standalone, blockquote, linked, reference, and HTML images creates one `image_artifact` per visible image.
* [ ] The user example creates one `image_artifact` whose `original_uri` is the YouTube thumbnail URL and whose metadata contains the outer YouTube link.
* [ ] The user example image block includes the first explanatory blockquote as `caption` and preserves broader adjacent note as `nearby_text`.
* [ ] In the user Linear Regression README trace, the linked YouTube thumbnail line is `block_type=image`, no longer an `unsupported_linked_markdown_image` diagnostic.
* [ ] HTML `<img alt="Average price" src="images/chart.png" width="50%">` creates an image artifact with `alt_text`, `original_uri`, and dimensions in metadata.
* [ ] HTML image blocks are no longer emitted only as generic `html` blocks with `unsupported_html_image` diagnostics.
* [ ] Local assets from blockquote/HTML images are copied to Raw Archive when the file exists.
* [ ] Remote image URLs do not attempt local asset copying and keep `asset_path=None`.
* [ ] Images inside fenced code blocks are ignored.
* [ ] Existing table/image artifact tests still pass.
* [ ] `trace-ingest` reports richer image syntax counts plus source/bound block ids for attached caption/nearby text.

## Definition of Done

* PRD accepted.
* Phase 2 context configured before implementation.
* Unit/integration tests added for each supported syntax family.
* `uv run pytest` passes with PostgreSQL healthy.
* Relevant backend spec updated if parser contracts change.
* No OCR/vision/model enrichment added in this task.

## Out of Scope

* OCR, vision summary, detected entities.
* Downloading remote image URLs into Raw Archive by default.
* Treating plain links to image files as embedded image artifacts.
* Full PDF/HTML/docx artifact extraction.
* Full public `MarkdownBlock` AST refactor unless selected explicitly.
* Perfect CommonMark conformance for every nested/escaped edge case in the first PR.

## Technical Notes

* Current parser: `src/pkcs/ingest/parsers.py`
* Current image regex: `_IMAGE_LINE_RE`
* Current image model: `src/pkcs/ingest/models.py::ParsedImageArtifact`
* Current ingest persistence: `src/pkcs/ingest/service.py::_create_image_artifacts`
* Current trace tool: `src/pkcs/ingest/trace.py`
* Tests to extend: `tests/test_ingest.py`, `tests/test_ingest_trace.py`, `tests/test_context_pack.py`
* Recent explicit block graph task: `.trellis/tasks/06-12-pkcs-explicit-markdown-block-graph/`
