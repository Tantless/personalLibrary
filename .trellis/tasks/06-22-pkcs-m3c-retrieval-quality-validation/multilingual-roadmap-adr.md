# M3C Multilingual Retrieval Roadmap ADR

Status: accepted on 2026-06-22

## Context

M3A1 showed a concrete mixed-language failure: the current six Chinese or mixed-language no-marker queries returned empty simple FTS results against mostly English corpus content. M3B fixed those six examples with deterministic query planning, source aliases, glossary expansion, multi-pass FTS, and fusion. M3C then added eval schema v2 and a comparison report that can measure simple search, planned search, and planned Context Pack support side by side.

The current private M3C comparison smoke report shows:

* `simple_top_10_hit_rate=0.0`
* `planned_top_10_hit_rate=1.0`
* `planned_context_support_rate=1.0`
* `locked_regression_pass_rate=1.0`

This proves the current locked regression set is fixed, but it does not prove language-independent recall. The corpus and query set are still too small to justify a translation adapter, LLM planner, embeddings, pgvector, reranker, or language-specific analyzer.

## Decision

M3C ends at measurement and roadmap definition. The next step is a diagnostic query-set task, not another retrieval backend change.

The retrieval roadmap is:

1. Keep the six current M3B rows as locked regression.
2. Add an expanded diagnostic query set as the next task.
3. Use `M3ComparisonEvaluator` reports to classify failures before changing retrieval behavior.
4. Apply deterministic lexical fixes only when failures are clearly `missing_alias`, `missing_glossary`, or evidence-selection related.
5. Consider a query-only translation adapter only after the diagnostic report shows repeated cross-language lexical gaps that can plausibly be fixed by bounded query rewriting.
6. Consider semantic/hybrid retrieval only after repeated `semantic_gap` failures remain after alias, glossary, and evidence selection fixes.

Translation, LLM planning, embeddings, pgvector, reranking, OpenSearch, and language-specific analyzers remain out of scope for M3C.

## Entry Criteria

### Deterministic Lexical Hardening

Use deterministic lexical hardening when the diagnostic report shows failures that can be explained by observable text mismatch:

* `missing_alias`: expected source is not reached because source title, canonical key, or known source alias terms are missing from the plan.
* `missing_glossary`: the query contains a stable technical phrase whose English terms are known and reusable.
* `evidence_selection_gap`: planned search reaches the expected source, but Context Pack evidence terms are not selected.

Rules:

* Do not map whole eval questions directly to source-specific queries.
* Add reusable aliases or glossary terms only when they generalize beyond one exact query.
* Compare before/after with `M3ComparisonEvaluator`.
* Locked regression must not regress.

### Query-Only Translation Adapter

Consider a translation adapter only when the diagnostic set exists and reports repeated cross-language lexical gaps:

* At least five diagnostic failures, or at least 20% of diagnostic rows, are not solved by current alias/glossary planning.
* Failure analysis shows the expected source would be reachable if query terms were rewritten into the corpus language.
* The adapter can run as an optional retrieval pass and fail closed without blocking deterministic passes.
* The adapter does not write translated text into source records, chunks, Raw Archive, or canonical metadata.

Required proof before keeping it:

* Quality delta against the simple and planned baselines.
* Locked regression remains at 100% planned top-10 and Context Pack support.
* Query latency impact is measured.
* Privacy behavior is explicit. If any remote LLM or translation API is used, private corpus and private query usage must be opt-in and documented.
* Reports include pass-level diagnostics for the translation pass.

### Semantic / Hybrid Retrieval

Consider semantic or hybrid retrieval only when the diagnostic report shows repeated `semantic_gap` failures that lexical and translation-style passes cannot explain.

Required proof before keeping it:

* Quality delta: diagnostic top-10 hit rate and Context Pack support improve meaningfully without reducing locked regression quality.
* Precision guardrail: must-not source violations and noisy result query counts do not increase materially.
* Latency and cost: report indexing time, storage growth, query p50/p95, model/API cost, and local resource requirements.
* Privacy: define whether embeddings are local or remote, what text leaves the machine, and how private data is excluded or explicitly opted in.
* Reindex path: document how chunks receive vectors, how stale vectors are detected, and how vector rebuilds are triggered.
* Rollback: semantic/hybrid retrieval must be disabled without losing PostgreSQL FTS search, source identity, citations, Raw Archive evidence, or `read_source`.

Semantic/hybrid retrieval must be an adapter or feature-flagged path. It must not replace the source/version/chunk/citation model.

## Future Spike Contract

Any future pgvector, embedding, reranker, or hybrid-search spike must produce a short report with:

* Eval input paths and suite names.
* Baseline report path and candidate report path.
* Quality delta for locked regression and diagnostic rows.
* Failure-class movement before and after the change.
* Latency, indexing time, storage size, and dependency changes.
* Privacy analysis for source text, query text, logs, and generated vectors.
* Reindex and rollback steps.

If the spike cannot show a measurable quality gain with bounded cost and a clear rollback path, it should be discarded.

## Consequences

This keeps the retrieval stack explainable while the eval harness matures. It delays broader multilingual recall improvements, but prevents adding translation or semantic infrastructure based on six successful examples. Future retrieval work has a concrete decision gate instead of relying on anecdotal demos.
