# PKCS Database Modeling Cleanup

## Goal

修正 MVP 数据库建模中 `source_type` 同时表达文件格式与内容语义的问题，把“原始文件格式”“规范化格式”“知识内容类型/用途”拆成清晰字段，并建立更一致的枚举字段建模规范。

## What I Already Know

* 当前 `source_type` 枚举为 `markdown_doc` 与 `ai_conversation`。
* `markdown_doc` 更像文件格式/载体命名，`ai_conversation` 更像内容语义/用途命名，二者不在同一分类维度。
* 当前 `source_type` 已进入 `sources`、`chunks`、`ingest_jobs`，并影响 parser 分发、Raw Archive 路径、search filter、Context Pack 展示、CLI/MCP 参数和验收语料。
* 旧设计中，`canonical_key` 未传时使用 `source_type + ":" + normalized_absolute_file_path`。
* 当前数据库枚举字段以字符串存储，例如 `source_type = "markdown_doc"`。
* 用户已提出数据库建模规范：枚举值字段应映射为 int 存储，并在中文注释中说明每个 int 对应含义。

## Assumptions

* 对外 CLI/MCP/HTTP 可以继续使用可读字符串参数，数据库内部用 int 存储；应用层负责映射。
* MVP 可以通过新增 migration 改造当前本地开发数据库，不需要兼容生产历史数据。
* 这次建模修正仍属于 MVP 收口后的模型清理，不引入 PDF/docx/xlsx 解析能力本身。

## Open Questions

* None. User chose the minimal MVP knowledge type set first, with richer preset categories reserved for a later step.

## Requirements

* 拆分当前 `source_type` 的职责，避免同一字段混合文件格式与内容语义。
* 数据库应记录原始文件格式，例如 md/jsonl/pdf/docx/xlsx，MVP 实际支持 md/txt/jsonl。
* 数据库应记录规范化后的内部格式；MVP 可先固定为 markdown/text 等受支持内部形态。
* 数据库应记录知识内容类型/用途，例如 AI 对话、普通文档、wiki、攻略、日记、邮件等。
* 解析分发应主要依据原始文件格式与知识内容类型共同决定，而不是只依赖旧 `source_type`。
* 检索过滤应面向知识内容类型，而不是文件格式。
* Raw Archive 路径分层应避免依赖旧 `source_type` 命名。
* 枚举字段在数据库中使用 int 存储，并在表/列注释中列出 int 到语义值的映射。
* 对外接口应避免暴露不清晰的 `markdown_doc` 命名。
* 更新 README、MVP PRD、测试夹具和验收查询字段命名，避免继续强化旧概念。
* MVP 第一阶段 `knowledge_type_code` 只落地 `1:document` 与 `2:ai_conversation`。
* 第二阶段再评估是否预置 wiki、game_guide、diary、email 等更细知识内容类型；本任务先保留字段设计位置，不实现复杂分类。
* 用户导入时的原始路径只作为单次输入路径，不作为长期资料链接或默认资料身份。
* Raw Archive 中的归档文件是 PKCS 内部认定的源文件，后续证据读取、版本回溯和 Context Pack 均以 Raw Archive 为准。
* 删除或废弃长期表中的用户原始路径字段：`sources.origin_uri`、`source_versions.file_path`。
* `ingest_jobs` 不保存完整用户输入路径，只保存文件名/目录名级别的 `input_name`。
* 未显式传 `canonical_key` 时，按知识类型前缀加五位递增编号自动生成，例如 `A00001`、`D00001`。
* 自动编号必须由数据库事务分配，避免重复。

## Acceptance Criteria

* [x] 数据库 schema 不再用单一 `source_type` 同时表达文件格式与内容语义。
* [x] 所有枚举字段以 int 存储，相关列注释说明每个 int 的含义。
* [x] CLI/MCP/HTTP 输入输出字段命名清晰，不再出现 `markdown_doc` 与 `ai_conversation` 作为同一维度的混合概念。
* [x] Ingest、search、read_source、context_pack 流程仍通过测试。
* [x] `canonical_key` fallback 策略同步调整，避免继续依赖旧 `source_type`。
* [x] README 和任务文档解释新字段含义、枚举映射和当前 MVP 支持范围。
* [x] 用户原始路径不再作为默认 `canonical_key` 来源。
* [x] `sources` 和 `source_versions` 不再保存用户原始完整路径。
* [x] `ingest_jobs` 不再保存用户原始完整路径，仅保存 `input_name`。
* [x] 未传 `canonical_key` 时按知识类型前缀和五位递增编号生成 key。
* [x] 删除原始文件后，`search -> read_source -> context_pack` 仍能从 Raw Archive 读回证据。

## Definition of Done

* Tests added/updated where behavior or schema changes.
* Docker-backed PostgreSQL migration passes from current head.
* Lint/typecheck/test gates pass where available.
* Database comments follow `中文名：解释`，外键注明关联目标，枚举列注明 int 映射。
* Coherent changes are committed as a focused commit after verification.

## Out of Scope

* 不实现 PDF/docx/xlsx 解析器。
* 不引入 LangChain/LlamaIndex 等框架。
* 不做真实个人资料导入。
* 不做 UI 或 DBeaver 专用视图。
* 不做远程服务、认证、权限系统。

## Technical Notes

* Current models: `src/pkcs/db/models.py`
* Current ingest constants: `src/pkcs/ingest/models.py`
* Current parser dispatch: `src/pkcs/ingest/parsers.py`
* Current search filter: `src/pkcs/search/providers.py`
* Current schema migration: `migrations/versions/20260604_0001_initial_schema.py`
* Current DB comment migrations: `migrations/versions/20260604_0002_add_schema_comments.py` through `20260604_0004_add_fk_targets_to_comments.py`
* Current user-facing docs: `README.md` and `.trellis/tasks/06-03-pkcs-mvp-m1-m2/prd.md`

## Initial Technical Direction

Candidate fields:

* `source_format_code`: 原始文件格式枚举。MVP: `1:md`、`2:txt`、`3:jsonl`；future reserved: `4:pdf`、`5:docx`、`6:xlsx`。
* `normalized_format_code`: 内部规范化格式枚举。MVP: `1:markdown`、`2:plain_text`；future reserved: `3:table_markdown`。
* `knowledge_type_code`: 知识内容类型枚举。MVP: `1:document`、`2:ai_conversation`；future reserved after validation: `3:wiki_article`、`4:game_guide`、`5:diary`、`6:email`。

## Decision (ADR-lite)

**Context**: The old `source_type` mixed format-like naming (`markdown_doc`) with semantic/use-case naming (`ai_conversation`), causing an inconsistent model and confusing future extension for PDF/docx/xlsx/email/wiki/game guide inputs.

**Decision**: First implement the minimal clean model: split file format, normalized format, and knowledge type; keep MVP `knowledge_type_code` to `1:document` and `2:ai_conversation`. After this works and tests pass, start the richer preset category phase by defining additional reserved values, but do not implement complex classification yet.

**Consequences**: The first migration stays focused and fixes the modeling error without over-classifying personal knowledge. Future categories have a planned place, but they should be added only when ingest/search behavior actually needs them.

## Decision (ADR-lite): Raw Archive Source Identity

**Context**: The previous fallback used `knowledge_type + normalized_absolute_file_path` as `canonical_key`. The user clarified that the original ingest path is not trustworthy as a long-lived link; it should be treated as one-time input only. PKCS should treat the Raw Archive copy as the internal source file.

**Decision**: Remove original full paths from long-lived source/version tables, stop using original paths for default `canonical_key`, store only input basename in ingest jobs/reports, and generate default canonical keys from knowledge-type prefix plus a five-digit database counter.

**Consequences**: Unkeyed imports become new PKCS sources with internal identities such as `D00001` or `A00001`. Users who want multiple imports to share one version chain must pass the same explicit `canonical_key`. Evidence recovery no longer depends on the original user path.

## Implementation Result

Initial split completed on 2026-06-05. Raw Archive source identity cleanup completed on 2026-06-08.

* Added `source_format_code`, `normalized_format_code`, and `knowledge_type_code` database modeling.
* Replaced public `source_type` CLI/MCP/service contract with `knowledge_type`.
* Search/read/context-pack outputs now expose `source_format`, `normalized_format`, and `knowledge_type` strings while the database stores int codes.
* Raw Archive now writes under `knowledge_type/source_id/version_id`.
* Updated README, backend specs, AGENTS, tests, and MVP PRD references.
* Removed persisted original full input paths from `sources`, `source_versions`, and `ingest_jobs`.
* Added `source_key_counters` and generated default keys such as `D00001` and `A00001`.
* Ingest reports now expose `input_name` instead of the full original input path.
* Added coverage proving Raw Archive read-back still works after deleting the original input file.

Verification:

* `docker compose ps postgres`
* `uv run alembic upgrade head`
* `uv run pytest`
* `git diff --check`
