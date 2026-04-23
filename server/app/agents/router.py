"""Router / Decision agent — tool-use enforced."""

from __future__ import annotations

import json
from dataclasses import dataclass

from app.agents._schema_helpers import openai_strict_schema
from app.core.config import get_settings
from app.core.logging import get_logger
from app.prompts.router import SYSTEM, USER_TEMPLATE
from app.schemas.common import FieldStatus, Outcome, Severity
from app.schemas.decision import Discrepancy, RouterOutput
from app.schemas.validation import ValidatorOutput
from app.services.llm import ToolCallUsage, call_tool

logger = get_logger(__name__)

_TOOL_NAME = "submit_decision"
_TOOL_DESCRIPTION = (
    "Submit the final routing decision (auto_approve / human_review / "
    "draft_amendment) with reasoning and an ordered discrepancy list."
)
_TOOL_PARAMETERS = openai_strict_schema(RouterOutput)


@dataclass
class RouterResult:
    output: RouterOutput
    tool_content: dict
    tool_output: dict
    usage: ToolCallUsage


async def run_router(validation: ValidatorOutput) -> RouterResult:
    settings = get_settings()

    validation_payload = {
        "overall_status": validation.overall_status.value,
        "summary": validation.summary,
        "results": {
            name: {
                "status": v.status.value,
                "found": v.found,
                "expected": v.expected,
                "severity": v.severity.value,
                "reasoning": v.reasoning,
            }
            for name, v in validation.results.items()
        },
    }
    user = USER_TEMPLATE.format(
        validation_json=json.dumps(validation_payload, ensure_ascii=False, indent=2),
    )

    result = await call_tool(
        model=settings.OPENAI_MODEL_REASONING,
        system=SYSTEM,
        user_content=user,
        tool_name=_TOOL_NAME,
        tool_description=_TOOL_DESCRIPTION,
        tool_parameters=_TOOL_PARAMETERS,
        temperature=0.0,
        max_tokens=1200,
    )

    parsed = RouterOutput.model_validate(result.tool_arguments)
    parsed = _enforce_outcome_invariants(parsed, validation)
    tool_output = parsed.model_dump(mode="json")

    logger.info(
        "router_done",
        extra={
            "outcome": parsed.outcome,
            "discrepancy_count": len(parsed.discrepancies),
        },
    )

    return RouterResult(
        output=parsed,
        tool_content=result.tool_content,
        tool_output=tool_output,
        usage=result.usage,
    )


def _enforce_outcome_invariants(
    out: RouterOutput,
    validation: ValidatorOutput,
) -> RouterOutput:
    has_critical_mismatch = any(
        v.status == FieldStatus.MISMATCH and v.severity == Severity.CRITICAL
        for v in validation.results.values()
    )
    has_mismatch = any(v.status == FieldStatus.MISMATCH for v in validation.results.values())
    has_uncertain = any(v.status == FieldStatus.UNCERTAIN for v in validation.results.values())

    expected: Outcome
    if has_critical_mismatch:
        expected = Outcome.DRAFT_AMENDMENT
    elif has_mismatch or has_uncertain:
        expected = Outcome.HUMAN_REVIEW
    else:
        expected = Outcome.AUTO_APPROVE

    outcome = expected if out.outcome != expected else out.outcome
    discrepancies: list[Discrepancy] = [] if outcome == Outcome.AUTO_APPROVE else _build_discrepancies(validation)
    reasoning = out.reasoning
    if outcome != out.outcome:
        reasoning = (
            f"[override] Outcome adjusted to {outcome.value} to match validator "
            f"signals. Original model reasoning: {out.reasoning}"
        )

    return out.model_copy(update={
        "outcome": outcome,
        "reasoning": reasoning,
        "discrepancies": discrepancies,
    })


_SEVERITY_ORDER = {Severity.CRITICAL: 0, Severity.MAJOR: 1, Severity.MINOR: 2}


def _build_discrepancies(validation: ValidatorOutput) -> list[Discrepancy]:
    items: list[Discrepancy] = []
    for field_name, v in validation.results.items():
        if v.status == FieldStatus.MATCH:
            continue
        items.append(Discrepancy(
            field=field_name,
            found=v.found,
            expected=v.expected,
            severity=v.severity,
            reasoning=v.reasoning,
        ))
    items.sort(key=lambda d: _SEVERITY_ORDER.get(d.severity, 99))
    return items
