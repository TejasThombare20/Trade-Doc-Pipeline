"""Azure OpenAI provider — uses the same openai SDK with AzureOpenAI client.

Requires three env vars:
  AZURE_OPENAI_API_KEY   — API key for the Azure resource
  AZURE_OPENAI_ENDPOINT  — e.g. https://my-resource.openai.azure.com
  AZURE_OPENAI_API_VERSION — API version, e.g. 2024-06-01
"""

from __future__ import annotations

import json
import time
from typing import Any

from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AsyncAzureOpenAI,
    RateLimitError,
)
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.core.config import get_settings
from app.core.errors import LLMError
from app.core.logging import get_logger
from app.services.llm_providers.base import LLMProvider, ToolCallResult, ToolCallUsage

logger = get_logger(__name__)

_RETRYABLE = (APITimeoutError, APIConnectionError, RateLimitError)


class AzureOpenAIProvider(LLMProvider):
    """Azure OpenAI Service.

    The `model` parameter passed by agents is used as the Azure
    *deployment name* — make sure each deployment is named to match
    the model string in config (e.g. ``gpt-4o``).
    """

    def __init__(self) -> None:
        settings = get_settings()
        self._client = AsyncAzureOpenAI(
            api_key=settings.AZURE_OPENAI_API_KEY,
            azure_endpoint=settings.AZURE_OPENAI_ENDPOINT,
            api_version=settings.AZURE_OPENAI_API_VERSION,
        )
        self._max_retries = settings.MAX_RETRIES_PER_NODE

    async def call_tool(
        self,
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
        messages: list[dict[str, Any]] = [
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
            stop=stop_after_attempt(1 + self._max_retries),
            wait=wait_exponential(multiplier=1, min=1, max=8),
            retry=retry_if_exception_type(_RETRYABLE),
            reraise=False,
        ):
            with attempt:
                try:
                    resp = await self._client.chat.completions.create(
                        model=model,  # Azure uses this as deployment name
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
                            extra={"provider": "azure", "status": e.status_code, "error": str(e)},
                        )
                        raise LLMError(
                            "LLM service configuration error. Please contact support.",
                            details={"provider": "azure", "status": e.status_code},
                        ) from e
                    last_exc = e
                    raise
                except _RETRYABLE as e:
                    last_exc = e
                    raise

        latency_ms = int((time.perf_counter() - started) * 1000)
        if resp is None:
            logger.error("llm_exhausted_retries", extra={"provider": "azure", "error": str(last_exc)})
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
                "provider": "azure",
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
