"""Rule-book extraction — tool-use enforced."""

from __future__ import annotations

from dataclasses import dataclass

from app.agents._schema_helpers import openai_strict_schema
from app.core.config import get_settings
from app.core.logging import get_logger
from app.prompts.rule_book import SYSTEM, USER_PREAMBLE
from app.schemas.rules import RuleBookExtractionOutput
from app.services.llm import ToolCallUsage, build_vision_user_content, call_tool
from app.services.preprocessing import PreprocessedDocument

logger = get_logger(__name__)

_TOOL_NAME = "submit_rule_book"
_TOOL_DESCRIPTION = (
    "Submit the structured rules extracted from the rule book PDF. Each rule "
    "must target one canonical field and declare its rule_type and spec."
)
_TOOL_PARAMETERS = openai_strict_schema(RuleBookExtractionOutput)


@dataclass
class RuleBookExtractionResult:
    output: RuleBookExtractionOutput
    tool_content: dict
    tool_output: dict
    usage: ToolCallUsage


async def extract_rule_book(pre: PreprocessedDocument) -> RuleBookExtractionResult:
    settings = get_settings()

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
        max_tokens=2500,
    )

    parsed = RuleBookExtractionOutput.model_validate(result.tool_arguments)
    tool_output = parsed.model_dump(mode="json")

    logger.info(
        "rule_book_extracted",
        extra={
            "rule_count": len(parsed.rules),
            "customer_name_in_book": parsed.customer_name_in_book,
        },
    )

    return RuleBookExtractionResult(
        output=parsed,
        tool_content=result.tool_content,
        tool_output=tool_output,
        usage=result.usage,
    )
