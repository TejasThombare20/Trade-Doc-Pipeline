"""LLM service — provider selection + tool-call facade."""

from __future__ import annotations

import hashlib
import uuid

from app.core.config import get_settings
from app.core.logging import get_logger
from app.services.llm_providers.base import (
    LLMProvider,
    ToolCallResult,
    ToolCallUsage,
)

logger = get_logger(__name__)

__all__ = ["LLMService", "call_tool", "build_vision_user_content", "ToolCallResult", "ToolCallUsage"]


class LLMService:
    """Facade over the configured LLM provider. One instance per app (singleton)."""

    def __init__(self) -> None:
        self._provider: LLMProvider | None = None

    def _get_provider(self) -> LLMProvider:
        if self._provider is not None:
            return self._provider

        settings = get_settings()
        name = settings.LLM_PROVIDER

        if name == "openai":
            from app.services.llm_providers.openai_provider import OpenAIProvider
            self._provider = OpenAIProvider()
        elif name == "azure":
            from app.services.llm_providers.azure_provider import AzureOpenAIProvider
            self._provider = AzureOpenAIProvider()
        elif name == "gemini":
            from app.services.llm_providers.gemini_provider import GeminiProvider
            self._provider = GeminiProvider()
        else:
            raise ValueError(
                f"Unknown LLM_PROVIDER '{name}'. "
                "Supported values: openai, azure, gemini"
            )

        logger.info("llm_provider_initialized", extra={"provider": name})
        return self._provider

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
        provider = self._get_provider()
        settings = get_settings()

        sanitized_user_content = _sanitize_user_content(user_content)
        tool_definition = {
            "type": "function",
            "function": {
                "name": tool_name,
                "description": tool_description,
                "parameters": tool_parameters,
            },
        }
        request_body = {
            "model": model,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": sanitized_user_content},
            ],
            "tools": [tool_definition],
            "tool_choice": {"type": "function", "function": {"name": tool_name}},
        }
        cache_key = _cache_key(system, sanitized_user_content, tool_definition, model, temperature)
        request_id = uuid.uuid4().hex[:12]

        logger.info(
            "llm_call_tool_request",
            extra={
                "request_id": request_id,
                "provider": settings.LLM_PROVIDER,
                "model": model,
                "tool_name": tool_name,
                "tool_description": tool_description,
                "tool_parameters_schema": tool_parameters,
                "tool_choice": request_body["tool_choice"],
                "available_tools": [tool_name],
                "temperature": temperature,
                "max_tokens": max_tokens,
                "cache_key": cache_key,
                "system_prompt": system,
                "user_prompt": sanitized_user_content,
                "request_body": request_body,
            },
        )

        return await provider.call_tool(
            model=model,
            system=system,
            user_content=user_content,
            tool_name=tool_name,
            tool_description=tool_description,
            tool_parameters=tool_parameters,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    def build_vision_user_content(
        self,
        *,
        text_preamble: str,
        extracted_text: str | None,
        images_b64: list[str],
    ) -> list[dict]:
        provider = self._get_provider()
        return provider.build_vision_user_content(
            text_preamble=text_preamble,
            extracted_text=extracted_text,
            images_b64=images_b64,
        )


# Module-level singleton
_llm_service: LLMService = LLMService()


def get_llm_service() -> LLMService:
    return _llm_service


# Module-level function aliases so existing agent imports keep working.
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
    return await _llm_service.call_tool(
        model=model,
        system=system,
        user_content=user_content,
        tool_name=tool_name,
        tool_description=tool_description,
        tool_parameters=tool_parameters,
        temperature=temperature,
        max_tokens=max_tokens,
    )


def build_vision_user_content(
    *,
    text_preamble: str,
    extracted_text: str | None,
    images_b64: list[str],
) -> list[dict]:
    return _llm_service.build_vision_user_content(
        text_preamble=text_preamble,
        extracted_text=extracted_text,
        images_b64=images_b64,
    )


def _sanitize_user_content(user_content: list[dict] | str) -> str | list[dict]:
    if isinstance(user_content, str):
        return user_content
    summarized: list[dict] = []
    for part in user_content:
        if isinstance(part, dict) and part.get("type") in {"image_url", "image", "input_image"}:
            image_url = part.get("image_url")
            url = image_url.get("url") if isinstance(image_url, dict) else None
            size_hint = len(url) if isinstance(url, str) else None
            summarized.append({
                "type": part.get("type"),
                "omitted": "image_payload",
                "payload_bytes": size_hint,
            })
        else:
            summarized.append(part)
    return summarized


def _cache_key(
    system: str,
    user_content: str | list[dict],
    tool_definition: dict,
    model: str,
    temperature: float,
) -> str:
    import json as _json
    payload = _json.dumps(
        {
            "model": model,
            "temperature": temperature,
            "system": system,
            "user": user_content,
            "tool": tool_definition,
        },
        sort_keys=True,
        ensure_ascii=False,
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
