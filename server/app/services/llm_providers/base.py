"""Abstract base for all LLM providers.

Every provider must implement `call_tool` — the single entry-point used by
every agent.  The shared dataclasses (`ToolCallResult`, `ToolCallUsage`) are
defined here so the rest of the codebase never imports a concrete provider.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass
from typing import Any


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


class LLMProvider(abc.ABC):
    """Contract every LLM backend must satisfy."""

    @abc.abstractmethod
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
        """Force the model to emit exactly one tool call and return its arguments."""
        ...

    # ------------------------------------------------------------------
    # Vision helpers — shared default; providers may override if needed.
    # ------------------------------------------------------------------
    def build_vision_user_content(
        self,
        *,
        text_preamble: str,
        extracted_text: str | None,
        images_b64: list[str],
    ) -> list[dict]:
        """Construct the multipart user-content array for a vision call.

        The default format follows the OpenAI chat-completion convention
        (``image_url`` blocks).  Providers whose API expects a different
        layout should override this method.
        """
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
