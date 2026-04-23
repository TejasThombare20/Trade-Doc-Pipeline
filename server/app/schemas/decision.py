"""Router / Decision agent output contract."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from app.schemas.common import Outcome, Severity


class Discrepancy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field: str
    found: str | None
    expected: str | None
    severity: Severity
    reasoning: str


class RouterOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    outcome: Outcome
    reasoning: str
    discrepancies: list[Discrepancy] = []
