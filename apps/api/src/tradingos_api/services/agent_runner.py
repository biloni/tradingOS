"""The one generic agent-execution path both committees share (Revision
Prompt 6). A single function, `run_agent_role()`, drives every one of
the 17 analyst/CIO roles through the same provider-neutral `LLMProvider`
adapter (`providers/llm.py`) — no role gets its own call path, and no
role can bypass the guardrails below.

Guardrails, all enforced here rather than left to each role's prompt:
- **Cost ceiling.** The caller tracks cumulative spend for the run and
  passes it in; a role whose turn arrives after the ceiling is already
  reached never calls the LLM at all (`DEGRADED`, not `FAILED` — a cost
  ceiling is an operator-chosen budget being respected, not an error).
- **Timeout.** Passed straight through to the provider's per-call
  `timeout_seconds`; a timeout is treated as one role's `FAILED` run,
  never a crash of the whole committee session.
- **Fallback.** `LLMProviderNotConfigured` (no API key) or any other
  provider-level exception degrades that one role to a structured
  failure state the orchestrator can act on (skip the role, still run
  the rest, and refuse to let the CIO treat a missing analyst opinion as
  a silent "no news is good news").
- **Structured output, forced.** The role's pydantic output schema
  becomes a single named tool with `tool_choice` forcing exactly that
  tool — never free text the caller would have to parse or coerce.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ValidationError

from tradingos_api.providers.llm import LLMProvider, LLMProviderNotConfigured
from tradingos_api.services.llm_cost import estimate_cost_usd

_OUTPUT_TOOL_NAME = "submit_agent_output"

AgentRunStatus = Literal["SUCCEEDED", "FAILED", "DEGRADED"]


@dataclass(frozen=True)
class AgentRunOutcome:
    status: AgentRunStatus
    output: BaseModel | None
    error_detail: str | None
    model: str | None
    input_tokens: int
    output_tokens: int
    latency_ms: int
    cost_usd: Decimal


def _model_facing_schema(output_schema: type[BaseModel]) -> dict[str, Any]:
    """Strips `run_metadata` out of the tool's `input_schema` — that
    field (model name, token counts, latency, cost) is filled in by this
    module itself from the real `LLMResponse` after the call completes;
    asking the model to invent plausible-looking values for its own
    not-yet-finished response is nonsensical, and in practice made
    real calls far more likely to fail schema validation or skip the
    tool call entirely (discovered via live verification — see
    docs/TEST_EVIDENCE.md)."""
    schema = output_schema.model_json_schema()
    schema["properties"] = {
        key: value for key, value in schema.get("properties", {}).items() if key != "run_metadata"
    }
    schema["required"] = [field for field in schema.get("required", []) if field != "run_metadata"]
    return schema


def _unwrap_single_key_payload(
    arguments: dict[str, Any], output_schema: type[BaseModel]
) -> dict[str, Any]:
    """Discovered via live verification: with a large, single forced-tool
    schema, Claude occasionally nests the entire payload one level deeper
    than requested (e.g. `{"agent_output": {...all the real fields...}}`)
    instead of putting the fields at the top level of the tool call. This
    is a parsing-robustness issue, not a content-quality one — the model
    produced every required field correctly, just one level too deep —
    so it's corrected here rather than treated as a validation failure.
    Only unwraps when doing so is unambiguous: exactly one top-level key,
    whose value is itself a dict containing at least one of the schema's
    required fields."""
    if len(arguments) != 1:
        return arguments
    (only_key, only_value) = next(iter(arguments.items()))
    if not isinstance(only_value, dict):
        return arguments
    required_fields = set(output_schema.model_json_schema().get("required", []))
    if required_fields & only_value.keys():
        return only_value
    return arguments


def _coerce_string_list_fields(
    arguments: dict[str, Any], output_schema: type[BaseModel]
) -> dict[str, Any]:
    """Discovered via live verification: under the same large forced-tool
    schema, Claude sometimes answers a `list[str]` field (e.g. `risks`)
    with a single string instead of a JSON array, while every other field
    in the same call is shaped correctly. Wrapping a non-empty string in
    a single-element list is a lossless, unambiguous correction — the
    alternative is discarding an otherwise well-formed answer over one
    field's container shape. Only applies to fields the schema declares
    as an array of strings; anything else is left untouched and falls
    through to normal validation."""
    properties = output_schema.model_json_schema().get("properties", {})
    coerced = dict(arguments)
    for field_name, field_schema in properties.items():
        if field_schema.get("type") != "array":
            continue
        if field_schema.get("items", {}).get("type") != "string":
            continue
        value = coerced.get(field_name)
        if isinstance(value, str) and value:
            coerced[field_name] = [value]
    return coerced


def _output_tool(output_schema: type[BaseModel]) -> dict[str, object]:
    return {
        "name": _OUTPUT_TOOL_NAME,
        "description": (
            "Submit your complete structured analysis. Call this tool exactly "
            "once with your full analysis — never respond with plain text "
            "instead of calling it."
        ),
        "input_schema": _model_facing_schema(output_schema),
    }


def run_agent_role(
    *,
    prompt_version: str,
    system_prompt: str,
    user_content: str,
    output_schema: type[BaseModel],
    llm: LLMProvider,
    cost_ceiling_usd: Decimal,
    spent_so_far_usd: Decimal,
    timeout_seconds: float,
) -> AgentRunOutcome:
    """`user_content` is the pre-serialized evidence bundle + deterministic
    feature summary for this role — plain text/JSON the caller built;
    this function never fetches evidence itself, keeping it independently
    testable with a fake `LLMProvider` and no database."""
    if spent_so_far_usd >= cost_ceiling_usd:
        return AgentRunOutcome(
            status="DEGRADED",
            output=None,
            error_detail=(
                f"cost ceiling ${cost_ceiling_usd} reached (${spent_so_far_usd} already "
                "spent this run) — this role was not called"
            ),
            model=None,
            input_tokens=0,
            output_tokens=0,
            latency_ms=0,
            cost_usd=Decimal(0),
        )

    started = time.monotonic()
    try:
        response = llm.complete(
            prompt_version=prompt_version,
            system_prompt=system_prompt,
            messages=[{"role": "user", "content": user_content}],
            tools=[_output_tool(output_schema)],
            tool_choice={
                "type": "tool",
                "name": _OUTPUT_TOOL_NAME,
                "disable_parallel_tool_use": True,
            },
            timeout_seconds=timeout_seconds,
        )
    except LLMProviderNotConfigured as exc:
        return AgentRunOutcome(
            status="DEGRADED",
            output=None,
            error_detail=f"LLM provider not configured: {exc}",
            model=None,
            input_tokens=0,
            output_tokens=0,
            latency_ms=int((time.monotonic() - started) * 1000),
            cost_usd=Decimal(0),
        )
    except Exception as exc:  # noqa: BLE001 - any provider failure degrades this one role, never crashes the committee
        return AgentRunOutcome(
            status="FAILED",
            output=None,
            error_detail=f"{type(exc).__name__}: {exc}",
            model=None,
            input_tokens=0,
            output_tokens=0,
            latency_ms=int((time.monotonic() - started) * 1000),
            cost_usd=Decimal(0),
        )

    latency_ms = int((time.monotonic() - started) * 1000)
    cost_usd = estimate_cost_usd(response.model, response.input_tokens, response.output_tokens)

    if not response.tool_calls:
        return AgentRunOutcome(
            status="FAILED",
            output=None,
            error_detail="model did not call the required output tool",
            model=response.model,
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
            latency_ms=latency_ms,
            cost_usd=cost_usd,
        )

    raw_arguments = _unwrap_single_key_payload(
        dict(response.tool_calls[0].arguments), output_schema
    )
    raw_arguments = _coerce_string_list_fields(raw_arguments, output_schema)
    raw_arguments["run_metadata"] = {
        "model": response.model,
        "input_tokens": response.input_tokens,
        "output_tokens": response.output_tokens,
        "latency_ms": latency_ms,
        "cost_usd": str(cost_usd),
    }
    try:
        output = output_schema.model_validate(raw_arguments)
    except ValidationError as exc:
        return AgentRunOutcome(
            status="FAILED",
            output=None,
            error_detail=f"schema validation failed: {exc}",
            model=response.model,
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
            latency_ms=latency_ms,
            cost_usd=cost_usd,
        )

    return AgentRunOutcome(
        status="SUCCEEDED",
        output=output,
        error_detail=None,
        model=response.model,
        input_tokens=response.input_tokens,
        output_tokens=response.output_tokens,
        latency_ms=latency_ms,
        cost_usd=cost_usd,
    )
