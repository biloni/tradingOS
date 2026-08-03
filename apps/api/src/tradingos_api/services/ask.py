"""Tool-use orchestration loop for `POST /api/v1/ask` (ADR-019).

The model is never the source of numeric truth (principles 6/7): every
figure it cites must come from a tool result executed against the
SQLAlchemy models by `services/llm_tools.py`'s schema-validated dispatcher.
This module owns the request/response cycle — call the model, execute any
tools it asks for, feed results back, repeat (capped at `MAX_ITERATIONS` to
bound cost and blast radius) — and logs every single Anthropic call to
`LLMCallLog` (principle 8/9), no exceptions.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import Session

from tradingos_api.models.llm_call_log import LLMCallLog
from tradingos_api.providers.llm import LLMProvider
from tradingos_api.services.llm_cost import estimate_cost_usd
from tradingos_api.services.llm_tools import (
    TOOL_SCHEMAS,
    RecommendationDraft,
    UnknownToolError,
    execute_tool,
)

PROMPT_VERSION = "ask-v1"
MAX_ITERATIONS = 5

SYSTEM_PROMPT = """You are the "Ask TradingOS" assistant inside a personal, \
paper-trading-only swing-trade decision-support tool.

Hard rules, no exceptions:
- You never place, modify, or cancel any order. This tool has no live \
trading capability and you must never imply otherwise.
- Every number you state (a price, an indicator value, a score, a \
recommendation) must come from a tool call you made in this conversation. \
Never estimate, recall from training data, or guess a figure — call a tool.
- If a tool returns an error or no data, say so plainly rather than \
filling the gap with a plausible-sounding number.
- Confidence bands (LOW/MEDIUM/HIGH) come from the `compute_recommendation` \
tool, computed deterministically from signal agreement. Never state your \
own confidence level or a calibrated probability — you do not have one.
- This is decision support, not investment advice. When asked for an \
opinion, ground it in the tool data and note that a human must decide.
- Keep answers concise and specific; cite the ticker and as-of date for any \
figure you mention."""


class AskResponse(BaseModel):
    answer: str
    recommendations: list[RecommendationDraft]
    llm_call_log_ids: list[int]
    iterations: int


def _log_call(
    session: Session,
    request_payload: dict[str, Any],
    response_payload: dict[str, Any],
    model: str,
    input_tokens: int,
    output_tokens: int,
) -> LLMCallLog:
    log = LLMCallLog(
        prompt_version=PROMPT_VERSION,
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=estimate_cost_usd(input_tokens, output_tokens),
        request_payload=request_payload,
        response_payload=response_payload,
        created_at=datetime.now(UTC),
    )
    session.add(log)
    session.commit()
    session.refresh(log)
    return log


def answer_question(session: Session, llm: LLMProvider, question: str) -> AskResponse:
    """Run the tool-use loop for one `/api/v1/ask` request. Stateless across
    requests (ADR-019): no conversation history is persisted — a caller that
    wants multi-turn context resends prior turns itself."""
    messages: list[dict[str, Any]] = [{"role": "user", "content": question}]
    llm_call_log_ids: list[int] = []
    recommendations: list[RecommendationDraft] = []

    for iteration in range(1, MAX_ITERATIONS + 1):
        response = llm.complete(
            prompt_version=PROMPT_VERSION,
            system_prompt=SYSTEM_PROMPT,
            messages=messages,
            tools=TOOL_SCHEMAS,
        )

        log = _log_call(
            session,
            request_payload={
                "messages": messages,
                "tools": [tool["name"] for tool in TOOL_SCHEMAS],
            },
            response_payload={
                "stop_reason": response.stop_reason,
                "raw_content": response.raw_content,
                "text": response.text,
            },
            model=response.model,
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
        )
        llm_call_log_ids.append(log.id)

        messages.append({"role": "assistant", "content": response.raw_content})

        if response.stop_reason != "tool_use" or not response.tool_calls:
            return AskResponse(
                answer=response.text or "",
                recommendations=recommendations,
                llm_call_log_ids=llm_call_log_ids,
                iterations=iteration,
            )

        tool_result_blocks: list[dict[str, Any]] = []
        for tool_call in response.tool_calls:
            try:
                result = execute_tool(session, tool_call.tool_name, tool_call.arguments)
                tool_result_blocks.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": tool_call.tool_use_id,
                        "content": json.dumps(result.output),
                    }
                )
                if result.recommendation_draft is not None:
                    recommendations.append(result.recommendation_draft)
            except (UnknownToolError, ValidationError) as exc:
                tool_result_blocks.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": tool_call.tool_use_id,
                        "content": f"Tool error: {exc}",
                        "is_error": True,
                    }
                )

        messages.append({"role": "user", "content": tool_result_blocks})

    return AskResponse(
        answer=(
            "I wasn't able to finish gathering data within this request's tool-call "
            "budget. Please try asking a more specific question."
        ),
        recommendations=recommendations,
        llm_call_log_ids=llm_call_log_ids,
        iterations=MAX_ITERATIONS,
    )
