"""Rule book contracts.

Rules are extracted from a customer-provided PDF. Each rule targets one
canonical field and declares how that field should be validated.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.common import Severity


RuleType = Literal["equals", "regex", "one_of", "required", "range", "custom"]


class RuleSpecPayload(BaseModel):
    """Explicit rule-spec shape so OpenAI strict-mode schemas have concrete keys.

    Each rule_type uses a subset:
      - equals  -> value
      - regex   -> pattern
      - one_of  -> values
      - required-> (none)
      - range   -> min, max
      - custom  -> description
    Unused keys must be null for the rule_type in question.
    """

    model_config = ConfigDict(extra="forbid")

    value: str | None = Field(default=None, description="For rule_type=equals.")
    values: list[str] | None = Field(default=None, description="For rule_type=one_of.")
    pattern: str | None = Field(default=None, description="For rule_type=regex (Python regex).")
    min: float | None = Field(default=None, description="For rule_type=range.")
    max: float | None = Field(default=None, description="For rule_type=range.")
    description: str | None = Field(
        default=None,
        description="For rule_type=custom (free-text constraint for the validator).",
    )


class RuleSpec(BaseModel):
    """Extracted rule from a rule book PDF.

    `spec` is interpreted per rule_type:
      - equals: { "value": "ACME CORP" }
      - regex:  { "pattern": "^[0-9]{6,10}$" }
      - one_of: { "values": ["FOB", "CIF", "EXW"] }
      - required: {}
      - range: { "min": 0, "max": 100000 }
      - custom: { "description": "free-text constraint for the validator LLM" }
    """

    model_config = ConfigDict(extra="forbid")

    field_name: str
    rule_type: RuleType
    spec: RuleSpecPayload = Field(default_factory=RuleSpecPayload)
    severity: Severity
    description: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _coerce_legacy_spec(cls, data: Any) -> Any:
        """Accept raw dict specs from older stored rules ({} / {"value": ...}).

        Existing rule books in the database were saved before `spec` became a
        typed model; transparently wrap them so RuleSpec.model_validate works.
        """
        if isinstance(data, dict) and isinstance(data.get("spec"), dict):
            raw = data["spec"]
            known = {"value", "values", "pattern", "min", "max", "description"}
            if raw and set(raw.keys()).issubset(known):
                data["spec"] = raw
            elif not raw:
                data["spec"] = {}
        return data

    def spec_as_dict(self) -> dict[str, Any]:
        """Back-compat: return the non-null subset of spec fields."""
        return {k: v for k, v in self.spec.model_dump().items() if v is not None}


class RuleBookExtractionOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    customer_name_in_book: str | None = Field(
        default=None,
        description="If the rule book identifies the customer, capture it here for sanity-checking.",
    )
    rules: list[RuleSpec]
    notes: str | None = None
