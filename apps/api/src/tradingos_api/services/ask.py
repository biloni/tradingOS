"""Tool-use orchestration loop for `POST /api/v1/ask` (ADR-019),
rebuilt against the current schema during end-to-end platform testing
— the original MVP router (Phase 4) was deleted in the Phase 8
domain-model migration and never replaced until now.

The model is never the source of numeric truth (principles 6/7): every
figure it cites must come from a tool result executed against the
current SQLAlchemy models by `services/ask_tools.py`'s schema-validated
dispatcher. This module owns the request/response cycle — call the
model, execute any tools it asks for, feed results back, repeat
(capped at `MAX_ITERATIONS` to bound cost and blast radius) — and logs
every single Anthropic call to `ModelCallRecord` (the same audit table
the committee path uses), no exceptions.
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import ValidationError
from sqlalchemy.orm import Session

from tradingos_api.models.operations import ModelCallRecord
from tradingos_api.providers.llm import LLMProvider
from tradingos_api.schemas.ask import AskResponse, RecommendationSummary
from tradingos_api.services.ask_tools import TOOL_SCHEMAS, UnknownToolError, execute_tool
from tradingos_api.services.llm_cost import estimate_cost_usd

PROMPT_VERSION = "ask-v1"
MAX_ITERATIONS = 5

SYSTEM_PROMPT = """You are the "Ask TradingOS" assistant inside a personal, \
paper-trading-only swing-trade decision-support tool.

Hard rules, no exceptions:
- You never place, modify, or cancel any order. This tool has no live \
trading capability and you must never imply otherwise.
- Every number you state (a score, a confidence level, an earnings date, an \
EPS estimate) must come from a tool call you made in this conversation. \
Never estimate, recall from training data, or guess a figure — call a tool.
- You never generate a new recommendation yourself. get_recommendations only \
reads recommendations a real Investment Committee or Tactical Trading Desk \
run already produced; if none exist for what's asked, say so rather than \
inventing one.
- If a tool returns an error or no data, say so plainly rather than filling \
the gap with a plausible-sounding answer.
- This is decision support, not investment advice. When asked for an \
opinion, ground it in the tool data and note that a human must decide.
- Keep answers concise and specific; cite the ticker and as-of date for any \
figure you mention."""


def _log_call(
    db: Session,
    model: str,
    input_tokens: int,
    output_tokens: int,
    stop_reason: str,
    response_excerpt: str | None,
) -> ModelCallRecord:
    record = ModelCallRecord(
        agent_run_id=None,
        prompt_version_label=PROMPT_VERSION,
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=estimate_cost_usd(model, input_tokens, output_tokens),
        stop_reason=stop_reason,
        response_excerpt=(response_excerpt[:500] if response_excerpt else None),
    )
    db.add(record)
    db.flush()
    return record


def answer_question(db: Session, llm: LLMProvider, question: str) -> AskResponse:
    """Run the tool-use loop for one `/api/v1/ask` request. Stateless
    across requests (ADR-019): no conversation history is persisted — a
    caller that wants multi-turn context resends prior turns itself."""
    messages: list[dict[str, Any]] = [{"role": "user", "content": question}]
    model_call_record_ids: list[Any] = []
    recommendations: list[RecommendationSummary] = []
    seen_recommendation_ids: set[Any] = set()

    for iteration in range(1, MAX_ITERATIONS + 1):
        response = llm.complete(
            prompt_version=PROMPT_VERSION,
            system_prompt=SYSTEM_PROMPT,
            messages=messages,
            tools=TOOL_SCHEMAS,
        )

        record = _log_call(
            db,
            model=response.model,
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
            stop_reason=response.stop_reason,
            response_excerpt=response.text,
        )
        model_call_record_ids.append(record.id)

        messages.append({"role": "assistant", "content": response.raw_content})

        if response.stop_reason != "tool_use" or not response.tool_calls:
            db.commit()
            return AskResponse(
                answer=response.text or "",
                recommendations=recommendations,
                model_call_record_ids=model_call_record_ids,
                iterations=iteration,
            )

        tool_result_blocks: list[dict[str, Any]] = []
        for tool_call in response.tool_calls:
            try:
                result = execute_tool(db, tool_call.tool_name, tool_call.arguments)
                tool_result_blocks.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": tool_call.tool_use_id,
                        "content": json.dumps(result.output),
                    }
                )
                for summary in result.recommendation_summaries:
                    if summary.recommendation_id not in seen_recommendation_ids:
                        seen_recommendation_ids.add(summary.recommendation_id)
                        recommendations.append(summary)
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

    db.commit()
    return AskResponse(
        answer=(
            "I wasn't able to finish gathering data within this request's tool-call "
            "budget. Please try asking a more specific question."
        ),
        recommendations=recommendations,
        model_call_record_ids=model_call_record_ids,
        iterations=MAX_ITERATIONS,
    )
