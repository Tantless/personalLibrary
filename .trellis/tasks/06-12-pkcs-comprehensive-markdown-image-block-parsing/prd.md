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

### Approach A: Extend Current Line Scanner With Targeted Parsers

How it works:

* Add dedicated parsers for common image line shapes.
* Keep current section/line scanning.
* Add grouping logic around detected image lines.

Pros:

* Smallest code change.
* No new explicit dependency.
* Easy to keep line locators.

Cons:

* Markdown inline parsing gets fragile quickly.
* Hard to correctly support nested brackets, escaped parens, reference definitions, HTML attrs, and edge cases.
* Likely to repeat the same problem when more syntax appears.

### Approach B: Use `markdown-it-py` Token Stream For Inline Image Detection (Recommended)

How it works:

* Add explicit dependency on `markdown-it-py`.
* Parse Markdown into block and inline tokens.
* Detect image tokens, link-open wrappers around image tokens, html_inline/html_block `<img>` tags.
* Preserve line maps from block tokens for locator.
* Keep current table parser initially, or gradually route table recognition through the same block stream later.
* Add a thin `MarkdownImageBlockParser` helper that returns image block candidates; current chunker consumes these candidates.

Pros:

* Matches real Markdown structure better than regex.
* Naturally handles linked images and reference-style images.
* Gives a cleaner path toward a public `MarkdownBlock` AST later.
* Still deterministic and local; no model dependency.

Cons:

* Adds a declared dependency.
* Need careful line map handling and tests.
* HTML `<img>` still needs safe attribute parsing; standard library `html.parser` is enough for MVP.

### Approach C: Build Full Internal MarkdownBlock AST First

How it works:

* Introduce explicit `MarkdownBlock` dataclasses for heading, paragraph, table, image, list, blockquote, code.
* Parse block stream first, then chunk from block stream.
* Use AST as public internal contract for future table/image/OCR/enrichment.

Pros:

* Best long-term architecture.
* Simplifies future artifact types and trace tooling.

Cons:

* Larger refactor.
* Higher regression risk.
* Too much if the immediate problem is image recognition coverage.

## Recommendation

Use Approach B for MVP: introduce `markdown-it-py` explicitly and build a focused image block detector from its token stream, without doing a full parser rewrite yet.

This gives enough correctness for common Markdown while keeping the PR small. A later PR can use the same token stream to replace table detection and produce a formal `MarkdownBlock` AST.

## Requirements (Evolving)

* Recognize standalone Markdown image lines.
* Recognize blockquote Markdown image lines.
* Recognize linked image lines such as `[![alt](thumb)](target "title")`.
* Recognize reference-style Markdown images when reference definitions exist in the same document.
* Recognize single-line and simple multi-line HTML `<img>` tags.
* Recognize linked HTML image patterns when `<a>` wraps `<img>`.
* Group image-dominant lines plus immediately related caption/callout lines into one image block.
* Preserve Raw Archive source text and line locator for every image artifact.
* Continue copying local image assets through ingest service; remote image URLs should become artifacts with `asset_path=None`.
* Store syntax/container/link/dimension metadata in artifact metadata.
* Update `trace-ingest` so it shows detected image syntax and block locator.

## Acceptance Criteria (Evolving)

* [ ] A synthetic fixture with standalone, blockquote, linked, reference, and HTML images creates one `image_artifact` per visible image.
* [ ] The user example creates one `image_artifact` whose `original_uri` is the YouTube thumbnail URL and whose metadata contains the outer YouTube link.
* [ ] The user example image block includes the first explanatory blockquote as `caption` and preserves broader adjacent note as `nearby_text`.
* [ ] HTML `<img alt="Average price" src="images/chart.png" width="50%">` creates an image artifact with `alt_text`, `original_uri`, and dimensions in metadata.
* [ ] Local assets from blockquote/HTML images are copied to Raw Archive when the file exists.
* [ ] Remote image URLs do not attempt local asset copying and keep `asset_path=None`.
* [ ] Images inside fenced code blocks are ignored.
* [ ] Existing table/image artifact tests still pass.
* [ ] `trace-ingest` reports the richer image syntax counts.

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

