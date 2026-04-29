"""Validator agent — tool-use enforced."""

from __future__ import annotations

import json
from dataclasses import dataclass

from app.agents._schema_helpers import openai_strict_schema
from app.core.config import get_settings
from app.core.logging import get_logger
from app.prompts.validator import SYSTEM, USER_TEMPLATE
from app.schemas.common import FieldStatus, OverallStatus
from app.schemas.extraction import ExtractorOutput
from app.schemas.rules import RuleSpec
from app.schemas.validation import FieldValidation, ValidatorOutput
from app.services.llm import ToolCallUsage, call_tool

logger = get_logger(__name__)

_TOOL_NAME = "submit_validation"
_TOOL_DESCRIPTION = (
    "Submit the field-by-field validation verdict. Every extracted field key "
    "must appear in results. Apply the confidence floor: if extractor "
    "confidence is below the threshold, the field status must be 'uncertain'."
)
_TOOL_PARAMETERS = openai_strict_schema(ValidatorOutput)


@dataclass
class ValidatorResult:
    output: ValidatorOutput
    tool_content: dict
    tool_output: dict
    usage: ToolCallUsage


async def run_validator(
    *,
    extraction: ExtractorOutput,
    rules: list[tuple[str, RuleSpec]],
) -> ValidatorResult:
    settings = get_settings()

    rules_payload = [
        {
            "rule_id": rule_id,
            "field_name": r.field_name,
            "rule_type": r.rule_type,
            "spec": r.spec_as_dict(),
            "severity": r.severity.value,
            "description": r.description,
        }
        for rule_id, r in rules
    ]
    extraction_payload = {
        "doc_type": extraction.doc_type.value,
        "doc_type_confidence": extraction.doc_type_confidence,
        "fields": {
            name: {
                "value": f.value,
                "confidence": f.confidence,
                "source_snippet": f.source_snippet,
            }
            for name, f in extraction.fields.as_dict().items()
        },
    }
    user = USER_TEMPLATE.format(
        rules_json=json.dumps(rules_payload, ensure_ascii=False, indent=2),
        extraction_json=json.dumps(extraction_payload, ensure_ascii=False, indent=2),
        low_confidence_threshold=settings.LOW_CONFIDENCE_THRESHOLD,
    )

    result = await call_tool(
        model=settings.OPENAI_MODEL_REASONING,
        system=SYSTEM,
        user_content=user,
        tool_name=_TOOL_NAME, 
        tool_description=_TOOL_DESCRIPTION,
        tool_parameters=_TOOL_PARAMETERS,
        temperature=0.0,
        max_tokens=2000,
    )

    parsed = ValidatorOutput.model_validate(result.tool_arguments)
    parsed = _fill_missing_rule_results(parsed, extraction, rules)
    parsed = _enforce_confidence_floor(parsed, extraction, settings.LOW_CONFIDENCE_THRESHOLD)
    parsed = _recompute_overall(parsed)
    tool_output = parsed.model_dump(mode="json")

    logger.info(
        "validator_done",
        extra={
            "overall_status": parsed.overall_status,
            "results_count": len(parsed.results),
        },
    )

    return ValidatorResult(
        output=parsed,
        tool_content=result.tool_content,
        tool_output=tool_output,
        usage=result.usage,
    )


_RULES_REQUIRING_VALUE = {"equals", "one_of", "regex", "required"}


def _fill_missing_rule_results(
    out: ValidatorOutput,
    extraction: ExtractorOutput,
    rules: list[tuple[str, RuleSpec]],
) -> ValidatorOutput:
    """Guarantee every rule-covered field has a result entry.

    When the LLM returns an empty or partial results dict (common when all
    extracted values are null), synthesize a deterministic verdict so the
    pipeline never silently approves an empty extraction:
      - null value for a rule that requires a value  → mismatch
      - non-null value but LLM omitted the entry     → uncertain (safe default)
    """
    new_results = dict(out.results)
    extracted_fields = extraction.fields.as_dict()
    for rule_id, r in rules:
        if r.field_name in new_results:
            continue
        extracted = extracted_fields.get(r.field_name)
        value_is_null = extracted is None or extracted.value is None

        if value_is_null and r.rule_type in _RULES_REQUIRING_VALUE:
            new_results[r.field_name] = FieldValidation(
                status=FieldStatus.MISMATCH,
                found=None,
                expected=r.description or r.rule_type,
                severity=r.severity,
                reasoning=f"Field is absent in the extracted document; rule '{r.rule_type}' requires a value.",
                rule_id=rule_id,
            )
        elif not value_is_null:
            new_results[r.field_name] = FieldValidation(
                status=FieldStatus.UNCERTAIN,
                found=extracted.value if extracted else None,
                expected=r.description or r.rule_type,
                severity=r.severity,
                reasoning="Validator did not return a result for this field; marking uncertain.",
                rule_id=rule_id,
            )

    return out.model_copy(update={"results": new_results})


def _enforce_confidence_floor(
    out: ValidatorOutput,
    extraction: ExtractorOutput,
    threshold: float,
) -> ValidatorOutput:
    new_results = dict(out.results)
    extracted_fields = extraction.fields.as_dict()
    for name, verdict in new_results.items():
        extracted = extracted_fields.get(name)
        if extracted is None:
            continue
        if extracted.confidence < threshold and verdict.status == FieldStatus.MATCH:
            new_results[name] = verdict.model_copy(update={
                "status": FieldStatus.UNCERTAIN,
                "reasoning": (
                    f"Extractor confidence {extracted.confidence:.2f} is below "
                    f"threshold {threshold:.2f}; escalating to uncertain. "
                    f"(original: {verdict.reasoning})"
                ),
            })
    return out.model_copy(update={"results": new_results})


def _recompute_overall(out: ValidatorOutput) -> ValidatorOutput:
    statuses = [v.status for v in out.results.values()]
    if any(s == FieldStatus.MISMATCH for s in statuses):
        overall = OverallStatus.HAS_MISMATCH
    elif any(s == FieldStatus.UNCERTAIN for s in statuses):
        overall = OverallStatus.HAS_UNCERTAIN
    else:
        overall = OverallStatus.ALL_MATCH
    return out.model_copy(update={"overall_status": overall})
