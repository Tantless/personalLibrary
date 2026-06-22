from dataclasses import asdict, dataclass, field
from typing import Any


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

    @classmethod
    def from_dict(cls, payload: dict[str, Any], *, line_number: int | None = None) -> "M3EvalQuery":
        prefix = f"m3 eval line {line_number}: " if line_number is not None else "m3 eval row: "
        query = _required_string(payload, "query", prefix)
        query_type = _required_string(payload, "query_type", prefix)
        expected_canonical_keys = _required_string_list(payload, "expected_canonical_keys", prefix)
        expected_evidence_terms = _required_string_list(payload, "expected_evidence_terms", prefix)
        must_not_canonical_keys = _optional_string_list(payload, "must_not_canonical_keys", prefix)
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
