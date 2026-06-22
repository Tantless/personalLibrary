from pathlib import Path

import pytest

from pkcs.eval import load_m3_eval_queries
from pkcs.search.planning import (
    PASS_ASCII_ENTITY,
    PASS_COMBINED,
    PASS_GLOSSARY_EXPANSION,
    PASS_ORIGINAL,
    PASS_SOURCE_ALIAS,
    QueryPlanner,
    QueryPlanningInputError,
    SourceAlias,
)


M3_EVAL_FIXTURE = Path("tests/fixtures/m3_eval_queries.jsonl")


def test_query_planner_builds_mixed_language_agents_tools_plan() -> None:
    planner = QueryPlanner(source_aliases=m3_source_aliases())

    plan = planner.plan("Agents SDK 如何处理工具调用？")

    assert plan.intent == "official_doc_lookup"
    assert [item.name for item in plan.passes] == [
        PASS_ORIGINAL,
        PASS_ASCII_ENTITY,
        PASS_GLOSSARY_EXPANSION,
        PASS_SOURCE_ALIAS,
        PASS_COMBINED,
    ]
    assert pass_query(plan, PASS_ASCII_ENTITY) == "Agents SDK"
    assert pass_query(plan, PASS_GLOSSARY_EXPANSION) == (
        "tools function tools tool calling function calling"
    )
    assert pass_query(plan, PASS_SOURCE_ALIAS) == "OpenAI Agents Python Tools docs"
    assert "OpenAI Agents Python Tools docs" in pass_query(plan, PASS_COMBINED)
    assert "function tools" in pass_query(plan, PASS_COMBINED)


def test_query_planner_uses_terms_not_whole_query_hardcoding() -> None:
    planner = QueryPlanner(source_aliases=m3_source_aliases())

    full_query = planner.plan("Agents SDK 如何处理工具调用？")
    shorter_query = planner.plan("Agents SDK 工具调用")

    assert pass_query(full_query, PASS_SOURCE_ALIAS) == "OpenAI Agents Python Tools docs"
    assert pass_query(shorter_query, PASS_SOURCE_ALIAS) == "OpenAI Agents Python Tools docs"


def test_query_planner_handles_gpt5_safety_query() -> None:
    planner = QueryPlanner(source_aliases=m3_source_aliases())

    plan = planner.plan("GPT-5 system card 讨论了哪些安全评估类别？")

    assert plan.intent == "safety_report_lookup"
    assert pass_query(plan, PASS_ASCII_ENTITY) == "GPT-5 system card"
    assert pass_query(plan, PASS_SOURCE_ALIAS) == "OpenAI GPT-5 System Card"
    assert "safety evaluations" in pass_query(plan, PASS_GLOSSARY_EXPANSION)


def test_query_planner_falls_back_to_original_for_unstructured_query() -> None:
    plan = QueryPlanner().plan("这段材料讲了什么？")

    assert plan.intent == "broad_recall"
    assert [item.name for item in plan.passes] == [PASS_ORIGINAL]
    assert plan.passes[0].query == "这段材料讲了什么？"


def test_retrieval_plan_to_dict_has_stable_shape() -> None:
    plan = QueryPlanner(source_aliases=m3_source_aliases()).plan(
        "NVIDIA DiffusionGemma 文档的重点是什么？"
    )

    body = plan.to_dict()

    assert set(body) == {"query", "intent", "passes", "fusion", "metadata"}
    assert body["fusion"] == "reciprocal_rank_v1"
    assert body["passes"][0] == {
        "name": PASS_ORIGINAL,
        "query": "NVIDIA DiffusionGemma 文档的重点是什么？",
        "weight": 1.0,
        "metadata": {},
    }
    assert body["metadata"]["ascii_entities"] == ["NVIDIA DiffusionGemma"]
    assert body["metadata"]["source_alias_matches"][0]["source_alias"]["canonical_key"] == (
        "m3-corpus:ai:nvidia-run-diffusiongemma"
    )


def test_query_planner_covers_current_m3_eval_queries() -> None:
    planner = QueryPlanner(source_aliases=m3_source_aliases())

    rows = load_m3_eval_queries(M3_EVAL_FIXTURE)
    plans = [planner.plan(row.query) for row in rows]

    assert all(PASS_ORIGINAL in [item.name for item in plan.passes] for plan in plans)
    assert all(PASS_ASCII_ENTITY in [item.name for item in plan.passes] for plan in plans)
    assert all(PASS_COMBINED in [item.name for item in plan.passes] for plan in plans)
    assert [pass_canonical_keys(plan) for plan in plans] == [
        ["m3-corpus:ai:openai-agents-python-guardrails"],
        ["m3-corpus:ai:openai-agents-python-tools"],
        ["m3-corpus:ai:openai-agents-python-tracing"],
        ["m3-corpus:ai:openai-gpt-5-system-card"],
        ["m3-corpus:game:bevy-readme"],
        ["m3-corpus:ai:nvidia-run-diffusiongemma"],
    ]


def test_query_planner_rejects_empty_query() -> None:
    with pytest.raises(QueryPlanningInputError, match="query must not be empty"):
        QueryPlanner().plan("  ")


def pass_query(plan, name: str) -> str:
    for item in plan.passes:
        if item.name == name:
            return item.query
    raise AssertionError(f"missing pass: {name}")


def pass_canonical_keys(plan) -> list[str]:
    matches = plan.metadata["source_alias_matches"]
    return [
        item["source_alias"]["canonical_key"]
        for item in matches
        if item["source_alias"]["canonical_key"]
    ]


def m3_source_aliases() -> list[SourceAlias]:
    return [
        SourceAlias(
            title="OpenAI Agents Python Guardrails docs",
            canonical_key="m3-corpus:ai:openai-agents-python-guardrails",
            aliases=("OpenAI Agents SDK", "Agents SDK", "OpenAI Agents Python"),
            terms=("guardrails", "input guardrails", "output guardrails"),
        ),
        SourceAlias(
            title="OpenAI Agents Python Tools docs",
            canonical_key="m3-corpus:ai:openai-agents-python-tools",
            aliases=("OpenAI Agents SDK", "Agents SDK", "OpenAI Agents Python"),
            terms=("tools", "function tools", "tool calling", "function calling"),
        ),
        SourceAlias(
            title="OpenAI Agents Python Tracing docs",
            canonical_key="m3-corpus:ai:openai-agents-python-tracing",
            aliases=("OpenAI Agents SDK", "Agents SDK", "OpenAI Agents Python"),
            terms=("tracing", "workflow", "observability", "events"),
        ),
        SourceAlias(
            title="OpenAI GPT-5 System Card",
            canonical_key="m3-corpus:ai:openai-gpt-5-system-card",
            aliases=("GPT-5 system card", "OpenAI GPT-5"),
            terms=("safety", "evaluations", "safety evaluations"),
        ),
        SourceAlias(
            title="Bevy README",
            canonical_key="m3-corpus:game:bevy-readme",
            aliases=("Bevy README", "Bevy", "README"),
            terms=("ECS", "game engine", "features", "capabilities"),
        ),
        SourceAlias(
            title="NVIDIA DiffusionGemma documentation",
            canonical_key="m3-corpus:ai:nvidia-run-diffusiongemma",
            aliases=("NVIDIA DiffusionGemma", "DiffusionGemma"),
            terms=("docs", "documentation", "overview", "highlights"),
        ),
    ]
