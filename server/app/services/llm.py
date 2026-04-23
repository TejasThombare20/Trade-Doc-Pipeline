"""LLM facade — every agent call goes through this module.

The actual backend (OpenAI / Azure / Gemini) is selected once at startup via
the ``LLM_PROVIDER`` env var.  Agent code keeps calling ``call_tool`` and
``build_vision_user_content`` exactly as before — the provider swap is
invisible to callers.
"""

from __future__ import annotations

from app.core.config import get_settings
from app.core.logging import get_logger
from app.services.llm_providers.base import (
    LLMProvider,
    ToolCallResult,
    ToolCallUsage,
)

logger = get_logger(__name__)

# Re-export so existing imports (`from app.services.llm import …`) keep working.
__all__ = ["call_tool", "build_vision_user_content", "ToolCallResult", "ToolCallUsage"]

_provider: LLMProvider | None = None


def _get_provider() -> LLMProvider:
    """Lazily instantiate the configured LLM provider (singleton)."""
    global _provider
    if _provider is not None:
        return _provider

    settings = get_settings()
    name = settings.LLM_PROVIDER

    if name == "openai":
        from app.services.llm_providers.openai_provider import OpenAIProvider
        _provider = OpenAIProvider()
    elif name == "azure":
        from app.services.llm_providers.azure_provider import AzureOpenAIProvider
        _provider = AzureOpenAIProvider()
    elif name == "gemini":
        from app.services.llm_providers.gemini_provider import GeminiProvider
        _provider = GeminiProvider()
    else:
        raise ValueError(
            f"Unknown LLM_PROVIDER '{name}'. "
            "Supported values: openai, azure, gemini"
        )

    logger.info("llm_provider_initialized", extra={"provider": name})
    return _provider


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
    """Force the model to emit exactly one tool call and return its arguments.

    Delegates to whichever provider is active.
    """
    provider = _get_provider()
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
    *,
    text_preamble: str,
    extracted_text: str | None,
    images_b64: list[str],
) -> list[dict]:
    """Construct the multipart user content array for a vision call.

    Format depends on the active provider (e.g. OpenAI uses ``image_url``
    blocks, Gemini uses ``inline_data``).
    """
    provider = _get_provider()
    return provider.build_vision_user_content(
        text_preamble=text_preamble,
        extracted_text=extracted_text,
        images_b64=images_b64,
    )
