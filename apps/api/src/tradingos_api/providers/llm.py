"""Provider-neutral LLM adapter interface.

Anthropic Claude is the Phase 4 implementation. Per project principles 6/7,
this interface is for synthesis, explanation, and scenario analysis only —
it never returns prices, indicators, or portfolio numbers as ground truth.
Every call must be logged (LLMCallLog, see docs/DATA_DICTIONARY.md) with
prompt version, tokens, and cost for principle 8/9 compliance.

ADR-020 (Phase 4) refined this interface from its Phase 1 shape to support
genuine tool-use: `messages` widened from `list[dict[str, str]]` to
`list[dict[str, Any]]` (Anthropic's tool-use messages carry nested content
blocks, not flat strings), `complete()` gained a `tools` parameter, and
`LLMResponse` gained `stop_reason` and `raw_content` — the exact content
blocks the model returned, serialized as plain dicts. Callers must echo
`raw_content` back verbatim on the next turn (not a reconstruction from
`text`/`tool_calls`) — this is what lets thinking blocks and tool_use blocks
round-trip correctly without the caller needing to understand their
internal shape.
"""

from typing import Any, Protocol

from pydantic import BaseModel


class LLMProviderNotConfigured(RuntimeError):
    """Raised when an LLMProvider is used without its required credentials
    set — same pattern as MarketDataProviderNotConfigured /BrokerProviderNotConfigured:
    missing config is shown explicitly, not papered over (principle 5)."""


class LLMToolCall(BaseModel):
    tool_use_id: str
    tool_name: str
    arguments: dict[str, object]


class LLMResponse(BaseModel):
    prompt_version: str
    model: str
    stop_reason: str
    text: str | None
    tool_calls: list[LLMToolCall]
    raw_content: list[dict[str, Any]]
    input_tokens: int
    output_tokens: int


class LLMProvider(Protocol):
    def complete(
        self,
        prompt_version: str,
        system_prompt: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        *,
        tool_choice: dict[str, Any] | None = None,
        timeout_seconds: float | None = None,
    ) -> LLMResponse:
        """Run one structured, tool-use-capable completion. Callers validate
        any tool call arguments against a zod/pydantic schema before executing
        them — the model never executes anything directly (principle 7).

        `tool_choice`/`timeout_seconds` (Revision Prompt 6) are additive,
        optional, backward-compatible widenings of this same interface —
        the same "one provider-neutral adapter" ADR-020 already refined
        once for genuine tool-use, refined again here so
        `services/agent_runner.py` can force a single named "submit your
        structured output" tool call (never free text) and bound each
        call's wall-clock time, without either committee needing its own
        adapter."""
        ...
