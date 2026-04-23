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
from app.prompts.extractor import SYSTEM, USER_PREAMBLE
from app.schemas.common import REQUIRED_FIELDS, DocType
from app.schemas.extraction import ExtractedField, ExtractorOutput
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


async def run_extractor(pre: PreprocessedDocument) -> ExtractorResult:
    settings = get_settings()

    if not pre.images_b64 and not pre.text:
        raise ValueError("preprocessed document has neither text nor images")

    user_content = build_vision_user_content(
        text_preamble=USER_PREAMBLE,
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
        max_tokens=1500,
    )

    parsed = ExtractorOutput.model_validate(result.tool_arguments)
    parsed = _ensure_all_required_fields(parsed)
    tool_output = parsed.model_dump(mode="json")

    logger.info(
        "extractor_done",
        extra={
            "doc_type": parsed.doc_type,
            "doc_type_confidence": parsed.doc_type_confidence,
            "fields_present": sum(1 for f in parsed.fields.values() if f.value),
            "fields_total": len(parsed.fields),
        },
    )

    return ExtractorResult(
        output=parsed,
        tool_content=result.tool_content,
        tool_output=tool_output,
        usage=result.usage,
    )


def _ensure_all_required_fields(out: ExtractorOutput) -> ExtractorOutput:
    filled: dict[str, ExtractedField] = {}
    for name in REQUIRED_FIELDS:
        filled[name] = out.fields.get(name, ExtractedField(value=None, confidence=0.0, source_snippet=None))
    for name, field in out.fields.items():
        if name not in filled:
            filled[name] = field
    return out.model_copy(update={"fields": filled})
