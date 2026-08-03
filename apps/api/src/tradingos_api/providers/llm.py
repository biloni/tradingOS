"""Provider-neutral LLM adapter interface.

Anthropic Claude is the Phase 4 implementation. Per project principles 6/7,
this interface is for synthesis, explanation, and scenario analysis only —
it never returns prices, indicators, or portfolio numbers as ground truth.
Every call must be logged (LLMCallLog, see docs/DATA_DICTIONARY.md) with
prompt version, tokens, and cost for principle 8/9 compliance.
"""

from typing import Protocol

from pydantic import BaseModel


class LLMToolCall(BaseModel):
    tool_name: str
    arguments: dict[str, object]


class LLMResponse(BaseModel):
    prompt_version: str
    model: str
    text: str | None
    tool_calls: list[LLMToolCall]
    input_tokens: int
    output_tokens: int


class LLMProvider(Protocol):
    def complete(
        self, prompt_version: str, system_prompt: str, messages: list[dict[str, str]]
    ) -> LLMResponse:
        """Run one structured, tool-use-capable completion. Callers validate
        any tool call arguments against a zod/pydantic schema before executing
        them — the model never executes anything directly (principle 7)."""
        ...
