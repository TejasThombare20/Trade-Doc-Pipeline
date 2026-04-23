"""Google Gemini provider — uses the `google-genai` unified SDK.

Requires one env var:
  GEMINI_API_KEY — API key from Google AI Studio

The Gemini API uses a different content format for vision (inline_data
blocks) and returns function calls in its own structure, so both
`call_tool` and `build_vision_user_content` are fully implemented here.
"""

from __future__ import annotations

import json
import time
from typing import Any

from google import genai
from google.genai import types
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

# google-genai raises generic exceptions for transient issues; we retry on
# common network / rate-limit errors.
_RETRYABLE = (
    ConnectionError,
    TimeoutError,
)


class GeminiProvider(LLMProvider):
    """Google Gemini via the google-genai SDK."""

    def __init__(self) -> None:
        settings = get_settings()
        self._client = genai.Client(api_key=settings.GEMINI_API_KEY)
        self._max_retries = settings.MAX_RETRIES_PER_NODE

    # ------------------------------------------------------------------
    # Vision content — Gemini uses inline_data for base64 images
    # ------------------------------------------------------------------
    def build_vision_user_content(
        self,
        *,
        text_preamble: str,
        extracted_text: str | None,
        images_b64: list[str],
    ) -> list[dict]:
        """Build Gemini-compatible multipart content with inline_data blocks."""
        parts: list[dict] = [{"text": text_preamble}]
        if extracted_text:
            truncated = extracted_text[:12_000]
            parts.append({
                "text": f"\n\n--- EXTRACTED TEXT (may be noisy) ---\n{truncated}",
            })
        for b64 in images_b64:
            parts.append({
                "inline_data": {
                    "mime_type": "image/png",
                    "data": b64,
                },
            })
        return parts

    # ------------------------------------------------------------------
    # Core tool call
    # ------------------------------------------------------------------
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
        # Build the function declaration from the JSON schema
        func_decl = types.FunctionDeclaration(
            name=tool_name,
            description=tool_description,
            parameters=self._clean_schema_for_gemini(tool_parameters),
        )
        tools = [types.Tool(function_declarations=[func_decl])]

        # Build content parts
        if isinstance(user_content, str):
            contents = user_content
        else:
            contents = [types.Part(**part) for part in user_content]

        config = types.GenerateContentConfig(
            system_instruction=system,
            tools=tools,
            tool_config=types.ToolConfig(
                function_calling_config=types.FunctionCallingConfig(
                    mode=types.FunctionCallingConfigMode.ANY,
                ),
            ),
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            temperature=temperature,
            max_output_tokens=max_tokens,
        )

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
                    resp = await self._client.aio.models.generate_content(
                        model=model,
                        contents=contents,
                        config=config,
                    )
                except _RETRYABLE as e:
                    last_exc = e
                    raise
                except Exception as e:
                    # Non-retryable errors (auth, bad request, etc.)
                    logger.error(
                        "gemini_api_error",
                        extra={"error": str(e), "type": type(e).__name__},
                    )
                    raise LLMError(
                        "LLM service error. Please contact support.",
                        details={"error": str(e)},
                    ) from e

        latency_ms = int((time.perf_counter() - started) * 1000)
        if resp is None:
            logger.error("llm_exhausted_retries", extra={"provider": "gemini", "error": str(last_exc)})
            raise LLMError("LLM service temporarily unavailable. Please try again later.") from last_exc

        # Extract function call from the response
        function_calls = resp.function_calls
        if not function_calls:
            raise LLMError("llm_no_tool_call", details={"model": model, "tool": tool_name})

        call = function_calls[0]
        if call.name != tool_name:
            raise LLMError(
                "llm_wrong_tool_called",
                details={"expected": tool_name, "got": call.name},
            )

        # Gemini returns args as a dict (google.protobuf.Struct), convert
        arguments = dict(call.args) if call.args else {}
        # Deep-convert any protobuf MapComposite / RepeatedComposite to
        # plain Python dicts / lists so downstream JSON serialisation works.
        arguments = json.loads(json.dumps(arguments, default=str))

        # Token usage
        usage_meta = resp.usage_metadata
        tokens_in = usage_meta.prompt_token_count if usage_meta else 0
        tokens_out = usage_meta.candidates_token_count if usage_meta else 0

        logger.info(
            "llm_tool_call",
            extra={
                "provider": "gemini",
                "model": model,
                "tool_name": tool_name,
                "tokens_in": tokens_in,
                "tokens_out": tokens_out,
                "latency_ms": latency_ms,
            },
        )

        tool_content = {
            "tool_name": tool_name,
            "tool_call_id": f"gemini-{tool_name}-{int(time.time())}",
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

    # ------------------------------------------------------------------
    # Schema helpers — Gemini doesn't support `additionalProperties` or
    # certain OpenAI-strict extensions, so we strip them.
    # ------------------------------------------------------------------
    @staticmethod
    def _clean_schema_for_gemini(schema: dict) -> dict:
        """Remove OpenAI-specific schema keys that Gemini rejects."""
        return _strip_keys(schema, {"additionalProperties", "$defs"})


def _strip_keys(obj: Any, keys_to_remove: set[str]) -> Any:
    """Recursively remove unwanted keys from a JSON-like structure."""
    if isinstance(obj, dict):
        return {
            k: _strip_keys(v, keys_to_remove)
            for k, v in obj.items()
            if k not in keys_to_remove
        }
    if isinstance(obj, list):
        return [_strip_keys(v, keys_to_remove) for v in obj]
    return obj
