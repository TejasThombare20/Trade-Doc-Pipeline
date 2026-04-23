"""Rule book contracts.

Rules are extracted from a customer-provided PDF. Each rule targets one
canonical field and declares how that field should be validated.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import Severity


RuleType = Literal["equals", "regex", "one_of", "required", "range", "custom"]


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
    spec: dict[str, Any] = Field(default_factory=dict)
    severity: Severity
    description: str | None = None


class RuleBookExtractionOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    customer_name_in_book: str | None = Field(
        default=None,
        description="If the rule book identifies the customer, capture it here for sanity-checking.",
    )
    rules: list[RuleSpec]
    notes: str | None = None
