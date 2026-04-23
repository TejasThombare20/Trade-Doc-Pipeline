"""OpenAI client wrapper — every agent call goes through tool use.

Every LLM call defines a single tool; the model must call that tool (via
tool_choice="required") and we treat the tool arguments as the agent's
structured output. tool_content (model's tool call) and tool_output
(post-processed result) are logged per step.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any

from openai import AsyncOpenAI, APITimeoutError, APIStatusError, APIConnectionError, RateLimitError
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.core.config import get_settings
from app.core.errors import LLMError
from app.core.logging import get_logger

logger = get_logger(__name__)

_client: AsyncOpenAI | None = None


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(api_key=get_settings().OPENAI_API_KEY)
    return _client


@dataclass
class ToolCallUsage:
    model: str
    tokens_in: int
    tokens_out: int
    latency_ms: int


@dataclass
class ToolCallResult:
    tool_name: str
    tool_arguments: dict[str, Any]
    tool_content: dict[str, Any]
    usage: ToolCallUsage


_RETRYABLE = (APITimeoutError, APIConnectionError, RateLimitError)


async def call_tool(
    *,
    model: str,
    system: str,
    user_content: list[dict] | str,
    tool_name: str,
    tool_description: str,
    tool_parameters: dict,
    temperature: float = 0.0,
    max_tokens: int = 2000,
) -> ToolCallResult:
    """Force the model to emit exactly one tool call and return its arguments."""
    settings = get_settings()
    client = _get_client()

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user_content},
    ]

    tool = {
        "type": "function",
        "function": {
            "name": tool_name,
            "description": tool_description,
            "parameters": tool_parameters,
        },
    }

    started = time.perf_counter()
    resp = None
    last_exc: Exception | None = None

    async for attempt in AsyncRetrying(
        stop=stop_after_attempt(1 + settings.MAX_RETRIES_PER_NODE),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        retry=retry_if_exception_type(_RETRYABLE),
        reraise=False,
    ):
        with attempt:
            try:
                resp = await client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    tools=[tool],
                    tool_choice={"type": "function", "function": {"name": tool_name}},
                )
            except APIStatusError as e:
                if 400 <= e.status_code < 500:
                    logger.error(
                        "llm_4xx_error",
                        extra={"status": e.status_code, "error": str(e)},
                    )
                    raise LLMError(
                        "LLM service configuration error. Please contact support.",
                        details={"status": e.status_code},
                    ) from e
                last_exc = e
                raise
            except _RETRYABLE as e:
                last_exc = e
                raise

    latency_ms = int((time.perf_counter() - started) * 1000)
    if resp is None:
        logger.error("llm_exhausted_retries", extra={"error": str(last_exc)})
        raise LLMError("LLM service temporarily unavailable. Please try again later.") from last_exc

    choice = resp.choices[0]
    tool_calls = choice.message.tool_calls or []
    if not tool_calls:
        raise LLMError("llm_no_tool_call", details={"model": model, "tool": tool_name})
    call = tool_calls[0]
    if call.function.name != tool_name:
        raise LLMError(
            "llm_wrong_tool_called",
            details={"expected": tool_name, "got": call.function.name},
        )

    try:
        arguments = json.loads(call.function.arguments or "{}")
    except json.JSONDecodeError as exc:
        raise LLMError(
            "llm_tool_args_parse_failed",
            details={"raw": (call.function.arguments or "")[:500]},
        ) from exc

    usage = resp.usage
    tokens_in = usage.prompt_tokens if usage else 0
    tokens_out = usage.completion_tokens if usage else 0

    logger.info(
        "llm_tool_call",
        extra={
            "model": model,
            "tool_name": tool_name,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "latency_ms": latency_ms,
        },
    )

    tool_content = {
        "tool_name": tool_name,
        "tool_call_id": call.id,
        "arguments": arguments,
    }

    return ToolCallResult(
        tool_name=tool_name,
        tool_arguments=arguments,
        tool_content=tool_content,
        usage=ToolCallUsage(
            model=model,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            latency_ms=latency_ms,
        ),
    )


def build_vision_user_content(
    *,
    text_preamble: str,
    extracted_text: str | None,
    images_b64: list[str],
) -> list[dict]:
    """Construct the multipart user content array for a vision call."""
    parts: list[dict] = [{"type": "text", "text": text_preamble}]
    if extracted_text:
        truncated = extracted_text[:12_000]
        parts.append({
            "type": "text",
            "text": f"\n\n--- EXTRACTED TEXT (may be noisy) ---\n{truncated}",
        })
    for b64 in images_b64:
        parts.append({
            "type": "image_url",
            "image_url": {
                "url": f"data:image/png;base64,{b64}",
                "detail": "high",
            },
        })
    return parts
