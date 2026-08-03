from typing import Any

from anthropic import Anthropic
from anthropic.types import MessageParam, TextBlock, ToolUseBlock

from tradingos_api.core.config import Settings
from tradingos_api.providers.llm import LLMProviderNotConfigured, LLMResponse, LLMToolCall

# claude-sonnet-5 (verified via the claude-api skill, 2026-08-03) — matches
# PROJECT_INSTRUCTIONS.md's "claude-sonnet-4-5 or newer". Sampling params
# (temperature/top_p/top_k) are rejected on non-default values for this
# model, so this provider never sets them. `thinking` is left unset
# (adaptive by default) rather than explicitly disabled — the raw_content
# round-trip (see providers/llm.py) preserves whatever blocks the model
# returns, so there's no need to special-case thinking blocks.
MODEL = "claude-sonnet-5"
MAX_TOKENS = 4096


class AnthropicLLMProvider:
    """Concrete `LLMProvider` (providers/llm.py) backed by the official
    `anthropic` Python SDK. Synthesis/explanation only — this class never
    computes a score or portfolio number itself (principles 6/7)."""

    def __init__(self, settings: Settings) -> None:
        if not settings.anthropic_api_key:
            raise LLMProviderNotConfigured(
                "ANTHROPIC_API_KEY is not set. The NL query feature requires "
                "an Anthropic account — see README.md."
            )
        self._client = Anthropic(api_key=settings.anthropic_api_key)

    def complete(
        self,
        prompt_version: str,
        system_prompt: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> LLMResponse:
        message_params: list[MessageParam] = [m for m in messages]  # type: ignore[misc]
        response = self._client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=system_prompt,
            messages=message_params,
            tools=tools or [],  # type: ignore[arg-type]
        )

        text_parts = [block.text for block in response.content if isinstance(block, TextBlock)]
        text = "\n".join(text_parts) if text_parts else None

        tool_calls = [
            LLMToolCall(tool_use_id=block.id, tool_name=block.name, arguments=block.input)
            for block in response.content
            if isinstance(block, ToolUseBlock)
        ]

        raw_content = [block.model_dump(mode="json") for block in response.content]

        return LLMResponse(
            prompt_version=prompt_version,
            model=response.model,
            stop_reason=response.stop_reason or "unknown",
            text=text,
            tool_calls=tool_calls,
            raw_content=raw_content,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
        )
