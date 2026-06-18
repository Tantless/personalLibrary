# M3 baseline corpus v1 replacement plan

## Summary

基于 v0 实际摄入结果，当前必须替换 5 条来源。其余问题主要归类为 `repair`：title 污染、missing images、PDF text-only fallback 或 HTML snapshot 降级。

## Must Replace

| ID | v0 Title | Problem | v1 Replacement |
|---|---|---|---|
| `M3-GAME-002` | Unreal Engine: Nanite Virtualized Geometry | v0 raw HTML snapshot 混入重复 JS/cookie challenge 文案 | `https://dev.epicgames.com/documentation/unreal-engine/nanite-virtualized-geometry-in-unreal-engine?lang=en-US` |
| `M3-GAME-003` | Unreal Engine 5.7 release notes | v0 raw HTML snapshot 混入大量 JS/cookie challenge 文案；`What's New` 概览页内容偏短 | `https://dev.epicgames.com/documentation/unreal-engine/unreal-engine-5-8-release-notes?lang=en-US` |
| `M3-GAME-006` | Unreal Engine EULA FAQ | v0 最终文档只有 spinner/page shell，公开 HTML 对 CLI 抓取返回 challenge/403 | `https://s3.amazonaws.com/EULA/04be6996-1cf1-4f50-9e75-b22db4680516-EULA.pdf` |
| `M3-GAME-015` | Unity Entities overview | v0 package root 只有 package home placeholder | `https://docs.unity3d.com/Packages/com.unity.entities%401.0/manual/concepts-intro.html` |
| `M3-GAME-016` | Unity Entities concepts | v0 文本过短，不足以支撑 baseline evaluation | `https://docs.unity3d.com/Packages/com.unity.entities%401.0/manual/whats-new.html` |

## Acquisition Rules

* Epic documentation pages must not be ingested from raw saved HTML if the snapshot contains `challenge-error-text` or `Enable JavaScript and cookies to continue`.
* For Epic docs, use a verified reader snapshot or Playwright-rendered snapshot, then run `prepare-ingest`.
* For Unreal EULA, prefer the downloadable official PDF over public HTML because the HTML endpoint is not CLI-stable.
* For Unity package docs, use concrete manual pages, not package root home pages; current smoke shows reader Markdown is more stable than direct HTML -> Docling for these pages.
* Replacement candidates still need to pass smoke quality gates before any clear/reingest step.

## Repair Classes

### PDF text-only fallback

These can remain in v1 only as `text_only`. They must not count toward artifact-ready coverage unless a successful Docling or PDF image/table extraction path is verified.

### Title pollution

Rows with DB title such as `Source Snapshot`, `License`, `Foreword`, or `1 Executive Summary` need source title repair. v1 expected title must come from the manifest, not wrapper heading or first Markdown heading.

### Missing images

Rows with missing local images can remain in text baseline if text evidence is preserved, but they cannot count as artifact-ready until image paths are resolved or the assets are downloaded.
