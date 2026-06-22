# PKCS M3A1 retrieval and Context Pack quality baseline

## Goal

在 M3 baseline corpus v1 已完成清洁重摄入后，建立一套可重复运行的检索与 Context Pack 质量评测。这个任务只记录当前 `PostgresFTSSearchProvider` + Context Pack v0 的 baseline，不改变检索排序、query planning、fusion 或 Context Pack 输出语义。

## What I already know

* M3 baseline corpus v1 已完成：100 sources、100 source versions、4248 chunks、412 image artifacts、75 table artifacts，最终 validation 100/100 pass，search smoke 100/100 pass。
* 当前 `SearchService` 仍是单路 PostgreSQL FTS；`ContextPackService` 仍是单次 search -> evidence select -> read_source -> artifact hydration -> Markdown。
* 现有 `tests/fixtures/eval_queries.jsonl` 是 MVP marker-based regression，适合防回归，但不能衡量真实 no-marker query 质量。
* M3 设计已确认 baseline-first：先有质量 baseline，再做 QueryRouter、multi-pass lexical fusion、Context Pack v1、semantic/rerank spike。

## Requirements

* 新增 M3 eval query schema，支持：
  * `query`
  * `query_type`
  * `expected_canonical_keys`
  * `expected_evidence_terms`
  * `must_not_canonical_keys`
  * `support_required`
  * `notes`
* 新增可提交的 schema/fixture shape 测试，确保 M3 eval rows 可被稳定解析。
* 新增 baseline evaluator helper，计算 search quality 与 Context Pack quality 指标。
* baseline evaluator 必须复用现有 `SearchService`、`ContextPackService`、`ReadSourceService`，不绕过应用服务。
* baseline report 必须包含 per-query 结果和 summary 指标，便于后续 M3B/M3C/M3D 对比。
* 私有 corpus 的原文和本地运行输出不提交；可提交 fixture schema、测试 helper 和说明。

## Acceptance Criteria

* [x] M3 eval row schema 有单元测试覆盖必填字段和最小合法 fixture。
* [x] baseline evaluator 能输出 search 指标：top1/top5/top10 hit、expected source rank、must-not violations、empty result count。
* [x] baseline evaluator 能输出 Context Pack 指标：evidence count、sources count、expected evidence terms found、traceability、must-not source inclusion、followup suggestions、caveats presence。
* [x] 现有 MVP acceptance eval 不被改坏。
* [x] 不引入 LangChain/LlamaIndex/Haystack/pgvector/OpenSearch/reranker。
* [x] 不修改 search ranking、Context Pack selection 或 MCP tool 名称。

## Definition of Done

* 聚焦测试通过。
* `git diff --check` 通过。
* 若本机 PostgreSQL/Docker 可用，运行相关 Docker-backed eval tests；若不可用，在任务记录中明确说明未跑原因。
* Trellis 任务状态和相关文件列表更新。
* 提交本任务变更。

## Out of Scope

* QueryRouter / `RetrievalPlan` v1 实现。
* Multi-pass lexical retrieval 和 fusion。
* Context Pack v1 输出升级。
* Semantic retrieval、pgvector、reranker。
* 新增资料类型或重摄入 corpus。

## Technical Notes

Expected files:

* `src/pkcs/eval/`
* `tests/test_m3_eval.py`
* `tests/fixtures/m3_eval_queries.jsonl`
* `.trellis/tasks/06-22-06-22-pkcs-m3a1-quality-baseline/`

Run shape:

```python
from pathlib import Path

from pkcs.eval import M3BaselineEvaluator, load_m3_eval_queries

queries = load_m3_eval_queries(Path("tests/fixtures/m3_eval_queries.jsonl"))
report = M3BaselineEvaluator.from_settings().evaluate(queries)
body = report.to_dict()
```

Focused validation run on 2026-06-22:

```text
uv run pytest tests/test_m3_eval.py tests/test_health.py tests/test_acceptance.py::test_mvp_eval_fixture_corpus_and_queries_have_required_shape -q
uv run python -m compileall -q src\pkcs\eval
git diff --check
```

Docker-backed tests were not run because Docker Desktop was unavailable: Docker API connection to `npipe:////./pipe/dockerDesktopLinuxEngine` failed.

Docker-backed validation was rerun after Docker Desktop became available:

```text
docker compose ps postgres
uv run alembic upgrade head
uv run pytest
```

Result: PostgreSQL healthy, Alembic at head, full pytest passed with 66 passed and 1 warning.

Baseline report generated at `data/private/eval-runs/m3a1-baseline-20260622-093935.json`. The report recorded 6/6 empty results for Chinese natural questions; English title-style smoke queries still hit expected corpus sources. This establishes a concrete M3B target: query normalization/keyword extraction for Chinese or mixed-language questions before or during lexical retrieval.
