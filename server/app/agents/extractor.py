"""Extractor agent.

Design note: Part 1 keeps a single tool (`extract_trade_document`) with a
`document_type` parameter. Splitting into one tool per doc type later is a
clean refactor: each doc type would define its own parameter schema but the
dispatch stays the same.

Every call goes through `call_tool` — the LLM MUST emit a tool call and we
log both the raw tool call (tool_content) and the post-processed result
(tool_output).
"""

from __future__ import annotations

from dataclasses import dataclass

from app.agents._schema_helpers import openai_strict_schema
from app.core.config import get_settings
from app.core.logging import get_logger
from app.prompts.extractor import NO_RULES_HINT, RULES_HINT_TEMPLATE, SYSTEM, USER_PREAMBLE
from app.schemas.extraction import ExtractorOutput
from app.schemas.rules import RuleSpec
from app.services.llm import ToolCallUsage, build_vision_user_content, call_tool
from app.services.preprocessing import PreprocessedDocument

logger = get_logger(__name__)

_TOOL_NAME = "extract_trade_document"
_TOOL_DESCRIPTION = (
    "Return the detected document type and the canonical trade-document fields "
    "extracted verbatim from the source, each with a 0.0-1.0 confidence and a "
    "short source snippet. Return nulls for fields you cannot find."
)
_TOOL_PARAMETERS = openai_strict_schema(ExtractorOutput)


@dataclass
class ExtractorResult:
    output: ExtractorOutput
    tool_content: dict
    tool_output: dict
    usage: ToolCallUsage


async def run_extractor(
    pre: PreprocessedDocument,
    rules: list[tuple[str, RuleSpec]] | None = None,
) -> ExtractorResult:
    settings = get_settings()

    if not pre.images_b64 and not pre.text:
        raise ValueError("preprocessed document has neither text nor images")

    rules_hint = _build_rules_hint(rules or [])
    preamble = USER_PREAMBLE.format(rules_hint=rules_hint)

    user_content = build_vision_user_content(
        text_preamble=preamble,
        extracted_text=pre.text or None,
        images_b64=pre.images_b64,
    )

    result = await call_tool(
        model=settings.OPENAI_MODEL_VISION,
        system=SYSTEM,
        user_content=user_content,
        tool_name=_TOOL_NAME,
        tool_description=_TOOL_DESCRIPTION,
        tool_parameters=_TOOL_PARAMETERS,
        temperature=0.0,
        max_tokens=2000,
    )

    parsed = ExtractorOutput.model_validate(_normalize_tool_args(result.tool_arguments))
    tool_output = parsed.model_dump(mode="json")

    fields_dict = parsed.fields.as_dict()
    logger.info(
        "extractor_done",
        extra={
            "doc_type": parsed.doc_type,
            "doc_type_confidence": parsed.doc_type_confidence,
            "fields_present": sum(1 for f in fields_dict.values() if f.value),
            "fields_total": len(fields_dict),
        },
    )

    return ExtractorResult(
        output=parsed,
        tool_content=result.tool_content,
        tool_output=tool_output,
        usage=result.usage,
    )


def _build_rules_hint(rules: list[tuple[str, RuleSpec]]) -> str:
    """Render rules into a prompt hint, skipping any with empty/meaningless specs.

    Empty specs (equals "", one_of [], regex "") are worse than no rule at all —
    they contradict the document and push the model toward returning null.
    """
    if not rules:
        return NO_RULES_HINT
    lines: list[str] = []
    for _, r in rules:
        if r.rule_type == "one_of":
            values = [v for v in (r.spec.values or []) if v]
            if not values:
                continue
            allowed = ", ".join(f'"{v}"' for v in values)
            lines.append(f"- {r.field_name}: must be one of [{allowed}]")
        elif r.rule_type == "equals":
            value = (r.spec.value or "").strip()
            if not value:
                continue
            lines.append(f"- {r.field_name}: must equal \"{value}\"")
        elif r.rule_type == "regex":
            pattern = (r.spec.pattern or "").strip()
            if not pattern:
                continue
            lines.append(f"- {r.field_name}: must match pattern {pattern}")
        elif r.rule_type == "required":
            lines.append(f"- {r.field_name}: required, must not be null")
        elif r.rule_type == "custom" and r.description:
            lines.append(f"- {r.field_name}: {r.description}")
    if not lines:
        return NO_RULES_HINT
    return RULES_HINT_TEMPLATE.format(rules_lines="\n".join(lines))


def _normalize_tool_args(args: dict) -> dict:
    """Handle LLMs that return extracted fields at the top level instead of under 'fields'.

    GPT-4o occasionally flattens the schema and emits:
      {"doc_type": ..., "consignee_name": {"value": ...}, ...}
    instead of:
      {"doc_type": ..., "fields": {"consignee_name": {"value": ...}, ...}}
    Detect this by checking whether 'fields' is missing and any REQUIRED_FIELDS
    key is present at the top level, then re-nest them.
    """
    from app.schemas.common import REQUIRED_FIELDS

    top_level_keys = set(args.keys())
    known_top_level = {"doc_type", "doc_type_confidence", "fields", "notes"}
    stray_field_keys = top_level_keys & set(REQUIRED_FIELDS)

    if stray_field_keys and "fields" not in args:
        nested: dict = {}
        clean: dict = {}
        for k, v in args.items():
            if k in known_top_level:
                clean[k] = v
            else:
                nested[k] = v
        clean["fields"] = nested
        return clean

    return args


