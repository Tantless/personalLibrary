# M3D Diagnostic Query Set Handoff

Status: ready for follow-up task

## Naming Boundary

In this handoff, `M3D` means the first expanded diagnostic query-set task after M3C.

Older M3 planning notes used `M3D` for "Context Pack v1". That label is now stale for the immediate next step. Context Pack v1 selection and rendering work should be revisited after the diagnostic query set exists, because the selection changes need a broader report to prove they help.

## Objective

Create the first expanded diagnostic query set that exercises mixed-language retrieval beyond the six locked regression rows.

M3D should answer:

* Which queries work with `original` pass only?
* Which queries depend on `source_alias`?
* Which queries depend on `glossary_expansion`?
* Which queries still fail planned search?
* Which queries hit the expected source but fail Context Pack evidence support?
* Which failures look like true `semantic_gap` rather than missing aliases or glossary terms?

## Scope

Include:

* A committed, non-private diagnostic query fixture or fixtures.
* Query rows using M3 eval schema v2.
* A local comparison report generated with `M3ComparisonEvaluator`.
* A short task report summarizing failure classes and recommended next retrieval work.

Exclude:

* No retrieval behavior changes in the first M3D PR.
* No translation, LLM planner, embeddings, pgvector, reranker, or language-specific analyzer.
* No private source content or private report committed.
* No hard CI gate for diagnostic rows until the team explicitly accepts thresholds.

## Recommended Fixture Shape

Keep the existing locked regression fixture stable:

```text
tests/fixtures/m3_eval_queries.jsonl
```

Add diagnostic rows in a separate file first:

```text
tests/fixtures/m3_diagnostic_queries.jsonl
```

Rationale: the locked regression fixture can remain a gate, while diagnostic rows can be report-only until thresholds are accepted.

Each diagnostic row should use schema v2 fields:

```json
{
  "query": "Agents SDK 如何处理工具调用？",
  "query_type": "official_doc_lookup",
  "suite": "diagnostic",
  "language": "mixed",
  "query_style": "natural_question",
  "expected_intent": "official_doc_lookup",
  "expected_pass_names": ["glossary_expansion", "source_alias", "combined"],
  "diagnostic_tags": ["mixed_language", "technical_term"],
  "expected_canonical_keys": ["m3-corpus:ai:openai-agents-python-tools"],
  "expected_evidence_terms": ["tools", "function tools"],
  "must_not_canonical_keys": [],
  "support_required": true,
  "notes": "Diagnostic row; report-only until thresholds are accepted."
}
```

## Query Matrix

Target at least 20 diagnostic rows in the first pass if enough non-private/public-reference corpus coverage exists.

Minimum useful coverage:

| Dimension | Required coverage |
|-----------|-------------------|
| `language` | `zh`, `en`, `ja`, `mixed` |
| `query_style` | `exact_title`, `natural_question`, `paraphrase`, `broad_recall`, `negative_or_ambiguous` |
| `query_type` | current M3 corpus types such as official docs, safety reports, broad project docs, recent technical docs |
| expected pass | rows expected to work through original, glossary, source alias, combined, and rows expected to expose gaps |

Japanese rows may be limited at first if the current corpus does not support them well. If Japanese rows are included, mark them clearly with `language="ja"` and diagnostic tags such as `japanese_query` or `cross_language_gap`.

## Report Process

Generate the local report by loading locked regression and diagnostic rows together:

```python
from pathlib import Path
from pkcs.eval import M3ComparisonEvaluator, load_m3_eval_queries, write_m3_comparison_report

rows = [
    *load_m3_eval_queries(Path("tests/fixtures/m3_eval_queries.jsonl")),
    *load_m3_eval_queries(Path("tests/fixtures/m3_diagnostic_queries.jsonl")),
]
report = M3ComparisonEvaluator.from_settings().evaluate(rows)
write_m3_comparison_report(report, Path("data/private/eval-runs/m3d-diagnostic.json"))
```

The generated report stays under `data/private/eval-runs/`.

## Acceptance Criteria

M3D first PR is complete when:

* The locked regression rows still pass planned top-10 and planned Context Pack support.
* Diagnostic fixture rows load through `load_m3_eval_queries()`.
* `M3ComparisonEvaluator` can generate a report over locked plus diagnostic rows.
* The task report lists failure counts by `failure_classes`.
* The task report recommends one of:
  * no retrieval change yet; expand diagnostics further;
  * deterministic alias/glossary/evidence fix;
  * translation adapter design;
  * semantic/hybrid spike design.

## Decision Rules After M3D Report

Use the report to decide the next PR:

| Dominant finding | Next step |
|------------------|-----------|
| Locked regression failure | Fix regression before all other work |
| Many `missing_alias` failures | Add reusable source aliases or improve alias extraction |
| Many `missing_glossary` failures | Add reusable glossary terms with tests |
| Many `evidence_selection_gap` failures | Improve Context Pack evidence selection |
| Many `semantic_gap` failures after lexical fixes | Design semantic/hybrid or translation spike |
| High noisy result count | Tune fusion, top-k selection, or source diversity before adding new backend |

Do not add translation or semantic retrieval in the same PR that introduces the diagnostic query set. The diagnostic set should first create a stable report baseline.
