# brainstorm: PKCS raw archive image links

## Goal

修复 prepared Markdown package 经 MCP `ingest_source` 摄入后，raw archive 中 `document.md` 图片引用全部断裂的问题。目标是让未来摄入的 raw Markdown 可直接打开阅读，且 Markdown 中的本地图片相对路径能解析到同一 raw version 目录下的实际文件。

## What I Already Know

* 用户确认不处理已摄入的 `D00001` / `D0001` 迁移或修补；后续会清空 PostgreSQL 回归到空库再测试。
* `prepare-ingest` 阶段生成的 package 是正确的：`document.md` 中 6 个图片引用都能解析到 package 内 `assets/` 文件。
* raw archive 阶段后，`document.md` 仍引用 `assets/image_000000...png`，但实际 raw asset 被写为 `assets/img_001-image_000000...png`。
* DB `image_artifacts` 中同时保存了 `original_uri` 和 `asset_path`，因此 artifact 检索未坏，但 raw Markdown 文件本身不可直接阅读。
* `img_001-` 文件名前缀是此前测试/调试便利，不是 raw archive 的必要业务约束。
* `RawArchiveWriter.write_asset()` 当前用 `artifact_key` 前缀生成文件名，是导致 raw Markdown 引用失配的直接原因。

## Feasibility Assessment

直接舍弃 MCP/raw archive 摄入时的 `img_001-` 图片文件名前缀是可行的，而且是本任务推荐方案。

理由：

* prepared package 已经完成资产规范化和同名冲突处理，文件名如 `assets/logo.png`、`assets/logo-2.png` 是稳定可解析的。
* raw archive 的职责是保存可追溯证据；保留 normalized Markdown 的相对资产路径比重新命名更符合“原样可读”目标。
* artifact key 仍然保存在 `image_artifacts.artifact_key`、chunk metadata、context pack 中，不需要体现在 raw 文件名里。
* 去掉前缀能避免额外的 Markdown 回写逻辑，降低错误面。
* 需要保留路径安全校验，防止 `../`、绝对路径或异常 URI 写出 raw version 目录。

风险：

* 如果直接按 `original_uri` 写入 raw asset，必须确保该路径被规范化后仍位于 raw version 根目录内。
* 对非 prepared package 的普通 Markdown 摄入，可能出现多个图片引用同名但来自不同目录的情况。若统一落到 `assets/<basename>` 会冲突；应保留原相对路径，或在冲突/不安全场景 fallback。
* `image_artifacts.asset_path` 的值会从 `assets/img_001-foo.png` 风格变为 `assets/foo.png` 或原相对路径对应的 raw 路径；相关测试需要更新。

## Requirements

* raw archive 写入本地图片 asset 时，默认保留 Markdown 中可安全解析的相对 URI。
* raw archive 中的 `document.md` 不应因为 asset archive 重命名而出现断链。
* 对 prepared package 生成的 `assets/<filename>` 引用，raw archive 应复制到同名 `assets/<filename>`。
* 对普通 Markdown 的安全相对路径，例如 `images/diagram.png`，raw archive 应复制到同样相对路径或等价可解析路径，并保证 raw `document.md` 链接有效。
* 对远程 URL、data URI、mailto URI，不复制 asset，保持现有行为。
* 对绝对路径、包含 `..` 的路径、Windows drive/root 路径、或任何会逃逸 raw version 目录的路径，不按原路径写入。
* 若遇到不安全或冲突场景，需要有明确 fallback 策略，不得静默生成断链。

## Recommended Technical Approach

修改 `RawArchiveWriter.write_asset()` / `IngestService._archive_image_asset()` 的合同，让调用方传入 Markdown 中的 `original_uri`，由 raw archive writer 计算 raw version 内的目标相对路径。

推荐行为：

* 若 `original_uri` 是安全的相对本地路径：
  * 目标路径为 `raw/<knowledge_type>/<source_id>/<version_id>/<original_uri>`。
  * 例如 `assets/diagram.png` 写为 raw version 下的 `assets/diagram.png`。
  * `image_artifacts.asset_path` 保存该实际 raw 路径。
* 若 `original_uri` 不安全或不适合保留：
  * fallback 到 `assets/<source filename>` 或 `assets/<artifact_key>-<source filename>`。
  * 如果 fallback 会导致 raw Markdown 链接不可解析，则必须同步回写 raw `document.md`，或把该场景显式标记为不可保留并由测试覆盖。

本任务 MVP 倾向更窄实现：

* 先支持安全相对路径保留。
* prepared package 和普通安全相对 Markdown 必须通过。
* 不实现已摄入数据迁移。
* 不引入新的 DB schema。
* 不改变 chunk/image artifact key 生成规则。

## Decision (ADR-lite)

**Context**: 当前 raw archive asset 文件名添加 `img_001-` 前缀，导致 raw `document.md` 中的 `assets/foo.png` 引用与实际 `assets/img_001-foo.png` 文件不一致。prepared package 阶段已经正确规范化资产路径，问题发生在 ingest/archive 阶段。

**Decision**: 未来摄入时，raw archive 默认保留 Markdown 中安全的本地相对图片路径，不再为了 artifact key 给文件名加 `img_001-` 前缀。artifact identity 继续由数据库字段和 chunk metadata 承担。

**Consequences**:

* raw `document.md` 可以直接作为可读证据文件打开。
* prepared package 到 raw archive 的路径语义一致。
* 现有测试中期待 `img_001-...` 文件名的断言需要改为检查链接可解析和 `image_artifacts.asset_path` 指向实际文件。
* 必须增加路径安全测试，避免相对路径逃逸 raw version 目录。

## Acceptance Criteria

* [x] 新增回归测试：prepared package 摄入后，raw `document.md` 中所有 Markdown 图片链接都能从 raw `document.md` 所在目录解析到存在的文件。
* [x] 新增或更新测试：`image_artifacts.asset_path` 指向 raw 中真实存在的图片文件。
* [x] 新增路径安全测试：`../evil.png`、绝对路径、Windows drive path 等不允许写出 raw version 目录。
* [x] prepared Markdown package ingest 仍能生成 image artifact，并保留 image enrichment 匹配能力。
* [x] 普通 Markdown local image ingest 仍能复制 asset，并使 raw Markdown 链接有效。
* [x] 远程图片 URL 行为不变：不复制 asset，`asset_path` 为 `None`。
* [x] `uv run pytest` 通过，至少覆盖 ingest、normalization、raw archive 相关测试。

## Definition of Done

* Tests added/updated for the raw archive image-link regression.
* Implementation keeps changes scoped to ingest/raw archive path handling.
* No migration or one-off repair for existing `D00001` data.
* No schema migration unless implementation proves it is unavoidable.
* Relevant Trellis spec updated only if the raw archive contract changes in a way future agents must remember.
* Focused git commit created after verification.

## Out of Scope

* 修复或迁移已摄入的 `D00001` / `D0001` raw files。
* 清空 PostgreSQL 数据库。
* 重新摄入 arXiv PDF。
* 改善 PDF 双栏浮动图阅读顺序。
* 改变 `prepare-ingest` 的 package 命名规则。
* 改变 image artifact key，例如 `img_001`、`img_002`。
* 新增 image download 或远程图片缓存能力。

## Technical Notes

Relevant files inspected:

* `src/pkcs/ingest/normalization.py`
  * `PrepareIngestService._normalize_image_uri()` 已将本地图片复制到 prepared package `assets/` 并回写 Markdown 引用。
* `src/pkcs/ingest/service.py`
  * `_ingest_file()` 先将 `document.md` 原始 bytes 写入 raw archive。
  * `_create_image_artifacts()` 后续复制图片 asset。
  * `_archive_image_asset()` 当前只返回 copied asset path，不回写 raw Markdown。
* `src/pkcs/storage/raw_archive.py`
  * `write_asset()` 当前通过 `filename = f"{artifact_key}-{source_path.name or 'asset'}"` 添加前缀。
* `src/pkcs/ingest/parsers.py`
  * image artifact key 由 parser 生成，例如 `img_001`，应保留为 artifact identity，而不是 raw 文件命名依据。
* `tests/test_ingest_normalization.py`
  * 已覆盖 prepared package 可被 ingest，但当前只检查 copied asset 存在，没有检查 raw Markdown 链接有效。
* `tests/test_ingest.py`
  * 已覆盖 image artifact asset copy，但未覆盖 raw archive Markdown link integrity。

Observed reproduction:

```text
prepared package:
  document.md image links = 6
  missing links = 0

raw archive:
  document.md image links = 6
  missing links = 6
```

Example mismatch:

```text
raw document.md references:
  assets/image_000000_b4006d9e....png

raw assets actually contain:
  assets/img_001-image_000000_b4006d9e....png
```
