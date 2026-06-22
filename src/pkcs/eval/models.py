from dataclasses import asdict, dataclass, field
from typing import Any


M3_EVAL_LANGUAGE_VALUES = {"zh", "en", "ja", "mixed"}
M3_EVAL_QUERY_STYLE_VALUES = {
    "broad_recall",
    "exact_title",
    "natural_question",
    "negative_or_ambiguous",
    "paraphrase",
}
M3_EVAL_SUITE_DIAGNOSTIC = "diagnostic"
M3_EVAL_SUITE_LOCKED_REGRESSION = "locked_regression"
M3_EVAL_SUITE_PRIVATE_DIAGNOSTIC = "private_diagnostic"
M3_EVAL_SUITE_VALUES = {
    M3_EVAL_SUITE_DIAGNOSTIC,
    M3_EVAL_SUITE_LOCKED_REGRESSION,
    M3_EVAL_SUITE_PRIVATE_DIAGNOSTIC,
}
M3_FAILURE_EVIDENCE_SELECTION_GAP = "evidence_selection_gap"
M3_FAILURE_MISSING_ALIAS = "missing_alias"
M3_FAILURE_MISSING_GLOSSARY = "missing_glossary"
M3_FAILURE_SEMANTIC_GAP = "semantic_gap"
M3_FAILURE_CLASSES = {
    M3_FAILURE_EVIDENCE_SELECTION_GAP,
    M3_FAILURE_MISSING_ALIAS,
    M3_FAILURE_MISSING_GLOSSARY,
    M3_FAILURE_SEMANTIC_GAP,
}


class M3EvalInputError(ValueError):
    pass


@dataclass(frozen=True)
class M3EvalQuery:
    query: str
    query_type: str
    expected_canonical_keys: list[str]
    expected_evidence_terms: list[str]
    must_not_canonical_keys: list[str] = field(default_factory=list)
    support_required: bool = True
    notes: str = ""
    suite: str = M3_EVAL_SUITE_LOCKED_REGRESSION
    language: str | None = None
    query_style: str | None = None
    expected_intent: str | None = None
    expected_pass_names: list[str] = field(default_factory=list)
    diagnostic_tags: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.expected_intent is None:
            object.__setattr__(self, "expected_intent", self.query_type)

    @classmethod
    def from_dict(cls, payload: dict[str, Any], *, line_number: int | None = None) -> "M3EvalQuery":
        prefix = f"m3 eval line {line_number}: " if line_number is not None else "m3 eval row: "
        query = _required_string(payload, "query", prefix)
        query_type = _required_string(payload, "query_type", prefix)
        expected_canonical_keys = _required_string_list(payload, "expected_canonical_keys", prefix)
        expected_evidence_terms = _required_string_list(payload, "expected_evidence_terms", prefix)
        must_not_canonical_keys = _optional_string_list(payload, "must_not_canonical_keys", prefix)
        suite = _optional_string(
            payload,
            "suite",
            prefix,
            default=M3_EVAL_SUITE_LOCKED_REGRESSION,
            allowed_values=M3_EVAL_SUITE_VALUES,
        )
        language = _optional_string(
            payload,
            "language",
            prefix,
            allowed_values=M3_EVAL_LANGUAGE_VALUES,
        )
        query_style = _optional_string(
            payload,
            "query_style",
            prefix,
            allowed_values=M3_EVAL_QUERY_STYLE_VALUES,
        )
        expected_intent = _optional_string(payload, "expected_intent", prefix, default=query_type)
        expected_pass_names = _optional_string_list(payload, "expected_pass_names", prefix)
        diagnostic_tags = _optional_string_list(payload, "diagnostic_tags", prefix)
        support_required = payload.get("support_required", True)
        if not isinstance(support_required, bool):
            raise M3EvalInputError(f"{prefix}support_required must be a boolean")
        notes = payload.get("notes", "")
        if notes is None:
            notes = ""
        if not isinstance(notes, str):
            raise M3EvalInputError(f"{prefix}notes must be a string when present")
        return cls(
            query=query,
            query_type=query_type,
            expected_canonical_keys=expected_canonical_keys,
            expected_evidence_terms=expected_evidence_terms,
            must_not_canonical_keys=must_not_canonical_keys,
            support_required=support_required,
            notes=notes,
            suite=suite or M3_EVAL_SUITE_LOCKED_REGRESSION,
            language=language,
            query_style=query_style,
            expected_intent=expected_intent,
            expected_pass_names=expected_pass_names,
            diagnostic_tags=diagnostic_tags,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class M3SearchQuality:
    result_count: int
    expected_source_rank: int | None
    top_1_hit: bool
    top_5_hit: bool
    top_10_hit: bool
    must_not_violations: list[str]
    empty_result: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class M3ContextPackQuality:
    evidence_count: int
    sources_count: int
    expected_evidence_terms_found: list[str]
    expected_evidence_terms_missing: list[str]
    all_expected_evidence_terms_found: bool
    all_evidence_traceable: bool
    must_not_sources_in_pack: list[str]
    followup_read_suggestions_count: int
    caveats_present: bool
    support_satisfied: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class M3EvalQueryResult:
    query: str
    query_type: str
    expected_canonical_keys: list[str]
    search: M3SearchQuality
    context_pack: M3ContextPackQuality
    notes: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "query_type": self.query_type,
            "expected_canonical_keys": self.expected_canonical_keys,
            "search": self.search.to_dict(),
            "context_pack": self.context_pack.to_dict(),
            "notes": self.notes,
        }


@dataclass(frozen=True)
class M3EvalSummary:
    query_count: int
    top_1_hit_rate: float
    top_5_hit_rate: float
    top_10_hit_rate: float
    context_support_rate: float
    traceability_rate: float
    caveats_rate: float
    search_must_not_violation_count: int
    context_must_not_violation_count: int
    empty_result_count: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class M3EvalReport:
    generated_at: str
    search_top_k: int
    context_top_k: int
    context_budget_tokens: int | None
    summary: M3EvalSummary
    results: list[M3EvalQueryResult]

    def to_dict(self) -> dict[str, Any]:
        return {
            "generated_at": self.generated_at,
            "search_top_k": self.search_top_k,
            "context_top_k": self.context_top_k,
            "context_budget_tokens": self.context_budget_tokens,
            "summary": self.summary.to_dict(),
            "results": [result.to_dict() for result in self.results],
        }


@dataclass(frozen=True)
class M3ComparisonPassDiagnostics:
    pass_result_counts: dict[str, int]
    pass_error_types: dict[str, str]
    expected_source_pass_names: list[str]
    missing_expected_pass_names: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class M3ResultDistribution:
    result_count: int
    distinct_canonical_key_count: int
    dominant_canonical_key: str | None
    dominant_canonical_key_count: int
    dominant_canonical_key_share: float
    unexpected_result_count: int
    unexpected_result_ratio: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class M3ComparisonQueryResult:
    query: str
    query_type: str
    suite: str
    language: str | None
    query_style: str | None
    expected_intent: str | None
    expected_canonical_keys: list[str]
    diagnostic_tags: list[str]
    simple_search: M3SearchQuality
    planned_search: M3SearchQuality
    planned_context_pack: M3ContextPackQuality
    pass_diagnostics: M3ComparisonPassDiagnostics
    planned_result_distribution: M3ResultDistribution
    failure_classes: list[str]
    notes: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "query_type": self.query_type,
            "suite": self.suite,
            "language": self.language,
            "query_style": self.query_style,
            "expected_intent": self.expected_intent,
            "expected_canonical_keys": self.expected_canonical_keys,
            "diagnostic_tags": self.diagnostic_tags,
            "simple_search": self.simple_search.to_dict(),
            "planned_search": self.planned_search.to_dict(),
            "planned_context_pack": self.planned_context_pack.to_dict(),
            "pass_diagnostics": self.pass_diagnostics.to_dict(),
            "planned_result_distribution": self.planned_result_distribution.to_dict(),
            "failure_classes": self.failure_classes,
            "notes": self.notes,
        }


@dataclass(frozen=True)
class M3ComparisonSummary:
    query_count: int
    simple_top_10_hit_rate: float
    planned_top_10_hit_rate: float
    simple_to_planned_top_10_delta: float
    planned_context_support_rate: float
    locked_regression_query_count: int
    locked_regression_pass_rate: float
    planned_empty_result_count: int
    context_support_miss_count: int
    noisy_result_query_count: int
    source_concentration_query_count: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class M3ComparisonPassSummary:
    original_hit_count: int
    ascii_entity_hit_count: int
    glossary_hit_count: int
    source_alias_hit_count: int
    combined_hit_count: int
    pass_result_counts: dict[str, int]
    pass_error_counts: dict[str, int]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class M3ComparisonReport:
    suite: str
    generated_at: str
    search_top_k: int
    context_top_k: int
    context_budget_tokens: int | None
    summary: M3ComparisonSummary
    pass_diagnostics: M3ComparisonPassSummary
    failure_classes: dict[str, int]
    results: list[M3ComparisonQueryResult]

    def to_dict(self) -> dict[str, Any]:
        return {
            "suite": self.suite,
            "generated_at": self.generated_at,
            "search_top_k": self.search_top_k,
            "context_top_k": self.context_top_k,
            "context_budget_tokens": self.context_budget_tokens,
            "summary": self.summary.to_dict(),
            "pass_diagnostics": self.pass_diagnostics.to_dict(),
            "failure_classes": self.failure_classes,
            "results": [result.to_dict() for result in self.results],
        }


def _required_string(payload: dict[str, Any], field_name: str, prefix: str) -> str:
    value = payload.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise M3EvalInputError(f"{prefix}{field_name} must be a non-empty string")
    return value.strip()


def _required_string_list(payload: dict[str, Any], field_name: str, prefix: str) -> list[str]:
    values = _optional_string_list(payload, field_name, prefix)
    if not values:
        raise M3EvalInputError(f"{prefix}{field_name} must contain at least one string")
    return values


def _optional_string_list(payload: dict[str, Any], field_name: str, prefix: str) -> list[str]:
    value = payload.get(field_name, [])
    if not isinstance(value, list):
        raise M3EvalInputError(f"{prefix}{field_name} must be a list of strings")
    values: list[str] = []
    for index, item in enumerate(value, start=1):
        if not isinstance(item, str) or not item.strip():
            raise M3EvalInputError(f"{prefix}{field_name}[{index}] must be a non-empty string")
        values.append(item.strip())
    return values


def _optional_string(
    payload: dict[str, Any],
    field_name: str,
    prefix: str,
    *,
    default: str | None = None,
    allowed_values: set[str] | None = None,
) -> str | None:
    value = payload.get(field_name, default)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise M3EvalInputError(f"{prefix}{field_name} must be a non-empty string when present")
    normalized = value.strip()
    if allowed_values is not None and normalized not in allowed_values:
        allowed = ", ".join(sorted(allowed_values))
        raise M3EvalInputError(f"{prefix}{field_name} must be one of: {allowed}")
    return normalized
