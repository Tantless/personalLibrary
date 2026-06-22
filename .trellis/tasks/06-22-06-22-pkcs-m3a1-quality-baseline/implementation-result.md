# M3A1 quality baseline implementation result

## Result

Implemented a repeatable M3 baseline evaluation scaffold without changing retrieval behavior.

## Changes

* Added `pkcs.eval` with M3 eval query schema, JSONL loader, baseline evaluator, and report dataclasses.
* Added `tests/fixtures/m3_eval_queries.jsonl` with non-private no-marker query rows that reference the completed M3 corpus v1 canonical keys.
* Added `tests/test_m3_eval.py` covering fixture shape, invalid row validation, search metrics, Context Pack metrics, and unsatisfied support.
* Updated backend specs so future work treats `src/pkcs/eval/` as the owner of local eval query parsing and baseline report calculation.

## Verification

Passed:

```text
uv run pytest tests/test_m3_eval.py tests/test_health.py tests/test_acceptance.py::test_mvp_eval_fixture_corpus_and_queries_have_required_shape -q
uv run python -m compileall -q src\pkcs\eval
git diff --check
```

Post-Docker validation on 2026-06-22:

```text
docker compose ps postgres
uv run alembic upgrade head
uv run pytest
```

Result: PostgreSQL healthy, Alembic at head, full pytest passed with 66 passed and 1 warning.

## Baseline Run

Generated a private local report:

```text
data/private/eval-runs/m3a1-baseline-20260622-093935.json
```

Summary:

* query_count: 6
* top_1_hit_rate: 0.0
* top_5_hit_rate: 0.0
* top_10_hit_rate: 0.0
* context_support_rate: 0.0
* traceability_rate: 1.0
* caveats_rate: 1.0
* empty_result_count: 6

Interpretation: the committed M3 eval fixture uses Chinese natural questions over mostly English corpus content. Current PostgreSQL `simple` FTS returns empty results for these mixed-language questions. English title-style smoke queries still hit the expected M3 corpus sources, so the corpus is searchable; M3B should treat Chinese/no-marker query normalization or keyword extraction as a first-class router/fusion requirement.

## Scope Notes

This task intentionally did not implement QueryRouter, lexical fusion, Context Pack v1, semantic retrieval, or reranking.
