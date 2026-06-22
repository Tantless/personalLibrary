# brainstorm: PKCS M3C retrieval quality validation and multilingual roadmap

## Goal

M3C 的目标是在 M3B 已修复 6 条混合语言查询之后，建立一套更稳的检索质量验证与长期多语言路线：证明 planned retrieval 不是只对当前 eval 样例有效，识别哪些查询仍依赖 glossary/source alias，明确什么时候需要进入 semantic / hybrid retrieval，而不是继续盲目扩词典。

## What I already know

* M3A1 建立了可重复 baseline evaluator，当前 eval schema 包含 `query`、`query_type`、`expected_canonical_keys`、`expected_evidence_terms`、`must_not_canonical_keys`、`support_required`、`notes`。
* M3A1 baseline 结果显示：6 条中文/混合语言 no-marker query 在 simple FTS 下 `empty_result_count=6/6`、top_10 hit rate 0.0、Context Pack support 0.0。
* M3B 已完成 deterministic `QueryPlanner`、`PlannedSearchService`、source-title-aware FTS、Context Pack planned retrieval 接入。
* M3B 本地验证显示：对当前 6 条 eval query，planned search + planned Context Pack 达到 top_10 hit rate 1.0、context_support_rate 1.0、traceability_rate 1.0、empty_result_count 0/6。
* 当前 `tests/fixtures/m3_eval_queries.jsonl` 只有 6 条，且主要围绕 M3B 修复样例；它适合回归测试，但不足以证明跨语言召回能力。
* 当前 planner 仍是 deterministic lexical：ASCII entity extraction、starter glossary、source alias、combined OR query；还没有 translation、LLM planner、embedding、pgvector、reranker 或 language analyzer。
* `PlannedSearchService` 已在 result metadata 中记录 `planned_retrieval.pass_hits`，Context Pack `retrieval_plan` 已包含 `query_plan`、`pass_runs`、`fusion`，这些字段可以用于质量诊断。
* 项目约束仍然是：不要让 LangChain/LlamaIndex/Haystack/pgvector/OpenSearch/reranker 接管核心 source/version/chunk/citation/Raw Archive/read_source 模型。

## Assumptions

* M3C 先做质量验证设计与最小实现，不直接引入新的 retrieval backend。
* M3C 应把“当前 6 条必须持续通过”与“扩展 query set 的探索性报告”分开，避免刚扩样本就制造脆弱 CI。
* 长期多语言能力需要 hybrid retrieval，但在进入 semantic 前必须先有能暴露失败类型的 eval/report。
* 私有 corpus 可以用于本地报告，但不能提交原文或包含隐私内容的报告。

## Requirements

* 扩展 M3 eval 覆盖面，至少区分：
  * `language`: `zh`、`en`、`ja`、`mixed`
  * `query_style`: `exact_title`、`natural_question`、`paraphrase`、`broad_recall`、`negative_or_ambiguous`
  * `expected_intent`
  * optional `expected_pass_names`
  * optional `diagnostic_tags`
* 保留当前 6 条 M3B eval 作为 locked regression set，后续改 planner/fusion 时不能回退。
* M3C 只为 expanded diagnostic set 预留 schema/report 能力；第一批 expanded diagnostic query set 延后到后续 M3D，避免把 evaluator/report 与样本扩展混在一个任务里。
* 质量报告必须同时比较 simple search 与 planned search，避免只看 Context Pack 的最终 support。
* 质量报告必须能回答：
  * 哪些 query 是 `original` pass 就能命中；
  * 哪些 query 依赖 `source_alias`；
  * 哪些 query 依赖 `glossary_expansion`；
  * 哪些 query planned search 仍失败；
  * 哪些 query 搜到源但 Context Pack evidence terms 不满足；
  * 哪些 query 的 top results 来源过于集中或噪声过高。
* Context Pack 验证继续要求 evidence 可追溯到 `chunk_id`、`source_id`、`version_id`、`locator`。
* 输出本地 JSON report 到 `data/private/eval-runs/`，不提交真实运行输出。
* 文档化长期 multilingual roadmap：deterministic lexical 的边界、translation adapter 的条件、semantic/hybrid retrieval 的进入标准。

## Acceptance Criteria

* [x] M3C 设计明确 eval schema v2 的新增字段和向后兼容策略。
* [x] M3C 设计明确 locked regression set 与 expanded diagnostic set 的区别。
* [x] M3C 设计明确 simple vs planned 的比较报告字段。
* [x] M3C 设计明确 pass-level diagnostics 和失败分类。
* [x] M3C 设计明确哪些结果进入 CI gate，哪些只进入本地报告。
* [x] M3C 设计明确 semantic/hybrid retrieval 的进入条件，不在本任务直接实现 pgvector/reranker。
* [x] 用户确认 M3C MVP 范围与 PR 顺序。

## Definition of Done

* PRD 被用户确认。
* 实现阶段必须有 schema/loader tests、report tests、至少一个 planned-vs-simple comparison test。
* Docker-backed `uv run pytest` 通过。
* `git diff --check` 通过。
* Trellis spec/task 文档同步。
* 每个 PR-sized step 提交一次。

## Technical Approach

### First principle

M3B 解决的是“当前 query 表达和英文 corpus 表达错位导致 0 召回”的一类问题。M3C 不继续直接加规则，而是先把问题拆开测量：

```text
query
  -> simple search baseline
  -> planned search
  -> pass-level hit analysis
  -> Context Pack evidence support
  -> failure classification
  -> roadmap decision
```

如果某个 query 失败，M3C 要能说清楚失败属于哪一类：

* query 没有可抽取实体；
* glossary 没覆盖关键术语；
* source title/canonical_key alias 不足；
* FTS 词面匹配不到，但语义上应命中；
* 搜到正确 source 但 evidence selection 没选到支持段；
* Context Pack 支持不足或 caveat 不够清楚。

### Eval schema v2 draft

保持旧字段可读，新增字段全部 optional，避免破坏 M3A1/M3B fixture：

```json
{
  "query": "Agents SDK 如何处理工具调用？",
  "query_type": "official_doc_lookup",
  "language": "mixed",
  "query_style": "natural_question",
  "expected_intent": "official_doc_lookup",
  "expected_pass_names": ["ascii_entity", "glossary_expansion", "source_alias", "combined"],
  "diagnostic_tags": ["mixed_language", "technical_term", "official_doc"],
  "expected_canonical_keys": ["m3-corpus:ai:openai-agents-python-tools"],
  "expected_evidence_terms": ["tools", "function tools"],
  "must_not_canonical_keys": [],
  "support_required": true,
  "notes": "No-marker query for tool invocation docs."
}
```

### Report shape draft

```json
{
  "suite": "m3c",
  "summary": {
    "query_count": 30,
    "simple_top_10_hit_rate": 0.25,
    "planned_top_10_hit_rate": 0.7,
    "planned_context_support_rate": 0.6,
    "locked_regression_pass_rate": 1.0
  },
  "pass_diagnostics": {
    "original_hit_count": 8,
    "source_alias_hit_count": 14,
    "glossary_hit_count": 11,
    "combined_hit_count": 16
  },
  "failure_classes": {
    "missing_alias": 3,
    "missing_glossary": 4,
    "semantic_gap": 5,
    "evidence_selection_gap": 2
  }
}
```

## Feasible Approaches

### Approach A: Eval expansion + comparator first (Recommended)

How it works:

* Extend eval schema with optional diagnostic metadata.
* Keep current 6 queries as locked regression.
* Reserve schema/report fields for future expanded diagnostic queries.
* Add evaluator/report code that compares simple search, planned search, and planned Context Pack.
* Classify failures using existing planned metadata.

Pros:

* Directly addresses the risk of overfitting M3B to 6 examples.
* Low dependency risk.
* Creates the evidence needed before deciding semantic/hybrid work.
* Keeps current architecture stable.

Cons:

* Does not immediately improve recall beyond current M3B.
* Does not add broader query coverage until the follow-up diagnostic query task.

### Approach B: Planner hardening first

How it works:

* Add more glossary terms, stronger alias extraction, language hints, and intent rules before expanding eval substantially.
* Use the current 6-query success as a base and manually add known gaps.

Pros:

* Faster visible behavior improvements.
* May solve some near-term mixed-language pain without new infrastructure.

Cons:

* High overfitting risk.
* Hard to know whether new rules improve general quality or just move failures around.

### Approach C: Semantic/hybrid spike first

How it works:

* Prototype multilingual embeddings and vector similarity as an optional adapter.
* Compare semantic results with planned lexical retrieval.

Pros:

* Closest to the long-term answer for Chinese/English/Japanese corpus mismatch.
* Can cover paraphrase and cross-language semantic gaps that lexical rules cannot.

Cons:

* Bigger dependency/schema/reindex/model-selection surface.
* Without stronger eval, success is anecdotal.
* Violates the current preference to avoid pgvector/reranker before the lexical/eval layer is mature.

## Recommended MVP Scope

Include:

* Eval schema v2 optional fields.
* Current 6-query locked regression gate.
* Schema/report support for future expanded diagnostic query set; no new expanded query set in this task.
* Planned-vs-simple comparison evaluator.
* Pass-level diagnostics from `planned_retrieval.pass_hits` and Context Pack `retrieval_plan.pass_runs`.
* Failure classification v1.
* Local JSON report under `data/private/eval-runs/`.
* Roadmap ADR for multilingual retrieval.

Exclude:

* Machine translation adapter.
* LLM query planner.
* Embeddings / pgvector.
* Reranker.
* New source types.
* Full Japanese analyzer/tokenizer changes.
* First expanded diagnostic query set; defer to follow-up M3D.

## Expansion Sweep

### Future evolution

* M3C reports should become the acceptance harness for M3D/M3E; every future retrieval backend must prove delta against it.
* Eval schema should leave room for future `source_profile`, `freshness`, `trust_level`, and `semantic_expected` metadata without changing existing rows.

### Related scenarios

* CLI/MCP external contracts should stay stable; quality reports can be a developer/eval path, not a user-facing MCP tool yet.
* Private local corpus reports should be supported without committing private content.

### Failure and edge cases

* Expanded diagnostic queries may intentionally fail in the follow-up task; M3C should support report-only rows without making them CI blockers.
* Query text can contain private intent, so reports committed to git must use synthetic/public queries only.
* If planned search fails because a pass errors, report should preserve pass error type without stopping the whole suite unless all passes fail.

## Proposed Implementation Plan

### PR1: Eval schema v2 and locked regression metadata

* Extend `M3EvalQuery` with optional fields: `language`, `query_style`, `expected_intent`, `expected_pass_names`, `diagnostic_tags`, `suite`.
* Keep old rows valid.
* Mark or default current 6 M3B rows as locked regression.
* Reserve `suite` values for future expanded diagnostic rows without adding those rows in M3C.
* Add tests for v1 compatibility and v2 validation.

Verification:

* `tests/test_m3_eval.py` covers old and new rows.
* Existing M3A1/M3B fixture still loads.

Status on 2026-06-22:

* Implemented locally in PR1: `M3EvalQuery` now accepts optional schema v2 metadata, old fixture rows default to `locked_regression`, and `expected_intent` defaults to `query_type`.
* Added loader tests for v1 compatibility, valid v2 diagnostic metadata, invalid suite values, and invalid expected pass names.
* Did not add expanded diagnostic query rows; that remains deferred to M3D.
* Verified with `uv run pytest tests\test_m3_eval.py -q`, `uv run alembic upgrade head`, `uv run pytest`, and `git diff --check`.

### PR2: Planned-vs-simple comparison report

* Add evaluator that runs simple `SearchService`, `PlannedSearchService`, and planned `ContextPackService` for each row.
* Add summary fields for simple/planned deltas.
* Add per-query pass diagnostics and failure classes.

Verification:

* Fake service tests prove summary math and failure classification.
* Real local M3 corpus smoke can generate private JSON report.

Status on 2026-06-22:

* Implemented locally in PR2: `M3ComparisonEvaluator` compares simple search, planned search, and planned Context Pack for each eval row.
* Added comparison report models with summary rates, locked regression pass rate, pass diagnostics, failure class counts, noisy result counts, source concentration counts, and per-query result details.
* Added `write_m3_comparison_report()` for local JSON output under gitignored `data/private/eval-runs/`.
* Added fake-service tests for simple-vs-planned deltas, pass hit diagnostics, pass error counts, missing alias/glossary classes, evidence selection gap, noisy/source-concentrated results, and JSON writing.
* Generated private smoke report at `data/private/eval-runs/m3c-comparison-pr2-20260622.json`; current 6 locked regression rows report `planned_top_10_hit_rate=1.0`, `planned_context_support_rate=1.0`, and `simple_top_10_hit_rate=0.0`.
* Verified with `uv run pytest tests\test_m3_eval.py tests\test_planned_search.py tests\test_context_pack.py -q`, `uv run alembic upgrade head`, `uv run pytest`, and `git diff --check`.

### PR3: Multilingual roadmap ADR and follow-up handoff

* Record entry criteria for translation adapter vs semantic/hybrid retrieval.
* Define what a future pgvector/embedding spike must prove: quality delta, cost, latency, privacy, reindex path, rollback.
* Create or document the follow-up M3D scope for the first expanded diagnostic query set.

Verification:

* Trellis PRD/spec updated.
* No runtime behavior change.

## Decision (ADR-lite draft)

### ADR-004: M3C Uses Eval Expansion Before More Retrieval Complexity

**Context**: M3B restored current mixed-language eval queries, but the eval set is only 6 rows and closely matches the failure mode M3B targeted. Adding more glossary rules or jumping to semantic retrieval now would improve examples without proving generality.

**Decision**: M3C implements eval schema v2 and planned-vs-simple diagnostics first, while deferring the first expanded diagnostic query set to a follow-up M3D task. Semantic/hybrid retrieval remains deferred until the diagnostic suite shows repeated lexical failure classes that cannot be addressed by source aliases, glossary, or evidence selection changes.

**Consequences**: M3C may not immediately improve user-facing recall or broaden query coverage, but it creates the measurement layer needed to make future retrieval changes and query-set expansion defensible.

## Open Questions

* None. User selected option 2 on 2026-06-22: M3C stops at schema + comparator/report; first expanded diagnostic query set is deferred.

## Out of Scope

* No translation/LLM planner/embedding/reranker implementation in M3C MVP.
* No new DB schema in the first PR unless the accepted design changes.
* No private source content or private eval report committed.
* No user-facing CLI/MCP eval command unless report-only pytest helpers become too awkward.
* No first expanded diagnostic query set; this is a follow-up task after the comparator exists.

## Technical Notes

Files inspected:

* `src/pkcs/eval/models.py`
* `src/pkcs/eval/m3_baseline.py`
* `src/pkcs/search/planning.py`
* `src/pkcs/search/planned.py`
* `tests/fixtures/m3_eval_queries.jsonl`
* `tests/test_m3_eval.py`
* `tests/test_planned_search.py`
* `tests/test_context_pack.py`
* `.trellis/tasks/06-16-06-16-pkcs-m3-retrieval-context-pack-design/prd.md`
* `.trellis/tasks/06-22-06-22-pkcs-m3a1-quality-baseline/prd.md`
* `.trellis/tasks/archive/2026-06/06-22-06-22-pkcs-m3b-mixed-language-query-planner/prd.md`

Current private report:

* `data/private/eval-runs/m3a1-baseline-20260622-093935.json`
