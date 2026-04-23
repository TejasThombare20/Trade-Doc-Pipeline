"""Validator agent input/output contracts."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import FieldStatus, OverallStatus, Severity


class FieldValidation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: FieldStatus
    found: str | None = None
    expected: str | None = None
    severity: Severity
    reasoning: str
    rule_id: str | None = Field(
        default=None, description="Rule that produced this result, if any."
    )


class ValidatorOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    overall_status: OverallStatus
    results: dict[str, FieldValidation]
    summary: str = Field(
        description="One or two sentences a human can read to understand the overall state."
    )
