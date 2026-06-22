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

Not run:

```text
docker compose ps postgres
uv run alembic upgrade head
uv run pytest
```

Reason: Docker Desktop was unavailable; Docker API connection failed for `npipe:////./pipe/dockerDesktopLinuxEngine`.

## Scope Notes

This task intentionally did not implement QueryRouter, lexical fusion, Context Pack v1, semantic retrieval, or reranking.
