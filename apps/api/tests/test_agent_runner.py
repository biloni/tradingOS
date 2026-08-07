"""Agent runner guardrail tests (Revision Prompt 6) — cost ceiling,
timeout, and fallback behavior, all against a fake `LLMProvider` (no
network call, no real Anthropic spend, per this project's established
test policy — see `test_anthropic_llm.py`)."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from pydantic import BaseModel

from tradingos_api.providers.llm import LLMProviderNotConfigured, LLMResponse, LLMToolCall
from tradingos_api.services.agent_runner import run_agent_role


class _SimpleOutput(BaseModel):
    verdict: str


def _valid_args() -> dict[str, Any]:
    return {"verdict": "bullish"}


class _SucceedingLLM:
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
        return LLMResponse(
            prompt_version=prompt_version,
            model="claude-sonnet-5",
            stop_reason="tool_use",
            text=None,
            tool_calls=[
                LLMToolCall(
                    tool_use_id="t1", tool_name="submit_agent_output", arguments=_valid_args()
                )
            ],
            raw_content=[],
            input_tokens=500,
            output_tokens=100,
        )


class _NotConfiguredLLM:
    def complete(self, *args: Any, **kwargs: Any) -> LLMResponse:
        raise LLMProviderNotConfigured("ANTHROPIC_API_KEY is not set.")


class _ExplodingLLM:
    def complete(self, *args: Any, **kwargs: Any) -> LLMResponse:
        raise RuntimeError("connection reset by peer")


class _NoToolCallLLM:
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
        return LLMResponse(
            prompt_version=prompt_version,
            model="claude-sonnet-5",
            stop_reason="end_turn",
            text="I'd rather just say it in plain text.",
            tool_calls=[],
            raw_content=[],
            input_tokens=400,
            output_tokens=50,
        )


class _MalformedArgsLLM:
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
        return LLMResponse(
            prompt_version=prompt_version,
            model="claude-sonnet-5",
            stop_reason="tool_use",
            text=None,
            tool_calls=[
                LLMToolCall(tool_use_id="t1", tool_name="submit_agent_output", arguments={})
            ],
            raw_content=[],
            input_tokens=400,
            output_tokens=50,
        )


class _WrappedPayloadLLM:
    """Simulates a real, live-observed Claude quirk: nesting the entire
    payload one level deeper than requested instead of putting the
    fields at the top level of the tool call arguments."""

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
        return LLMResponse(
            prompt_version=prompt_version,
            model="claude-sonnet-5",
            stop_reason="tool_use",
            text=None,
            tool_calls=[
                LLMToolCall(
                    tool_use_id="t1",
                    tool_name="submit_agent_output",
                    arguments={"agent_output": _valid_args()},
                )
            ],
            raw_content=[],
            input_tokens=400,
            output_tokens=100,
        )


class TestSingleKeyWrappedPayloadIsUnwrapped:
    def test_wrapped_payload_is_recovered_not_rejected(self) -> None:
        """Discovered via live verification against the real Anthropic
        API: with a large forced-tool schema, the model occasionally
        wraps the whole payload under an extra key (e.g.
        `{"agent_output": {...}}`). This is corrected, not treated as a
        validation failure, since every required field is present one
        level too deep."""
        outcome = run_agent_role(
            prompt_version="v1",
            system_prompt="be a good analyst",
            user_content="analyze this",
            output_schema=_SimpleOutput,
            llm=_WrappedPayloadLLM(),
            cost_ceiling_usd=Decimal("1.00"),
            spent_so_far_usd=Decimal("0"),
            timeout_seconds=30,
        )
        assert outcome.status == "SUCCEEDED"
        assert isinstance(outcome.output, _SimpleOutput)
        assert outcome.output.verdict == "bullish"

    def test_a_dict_valued_field_that_is_not_a_wrapper_is_left_alone(self) -> None:
        """A single top-level key whose value doesn't contain any of the
        schema's required fields is not a wrapper — it's just a
        single-field schema, and must not be unwrapped."""

        class _SingleDictFieldOutput(BaseModel):
            payload: dict[str, Any]

        class _SingleFieldLLM:
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
                return LLMResponse(
                    prompt_version=prompt_version,
                    model="claude-sonnet-5",
                    stop_reason="tool_use",
                    text=None,
                    tool_calls=[
                        LLMToolCall(
                            tool_use_id="t1",
                            tool_name="submit_agent_output",
                            arguments={"payload": {"nested": "value"}},
                        )
                    ],
                    raw_content=[],
                    input_tokens=100,
                    output_tokens=20,
                )

        outcome = run_agent_role(
            prompt_version="v1",
            system_prompt="be a good analyst",
            user_content="analyze this",
            output_schema=_SingleDictFieldOutput,
            llm=_SingleFieldLLM(),
            cost_ceiling_usd=Decimal("1.00"),
            spent_so_far_usd=Decimal("0"),
            timeout_seconds=30,
        )
        assert outcome.status == "SUCCEEDED"
        assert isinstance(outcome.output, _SingleDictFieldOutput)
        assert outcome.output.payload == {"nested": "value"}


class TestRunMetadataIsExcludedFromTheModelFacingSchema:
    def test_tool_schema_does_not_ask_the_model_to_supply_run_metadata(self) -> None:
        """`run_metadata` (model, tokens, latency, cost) is filled in by
        this module from the real `LLMResponse` after the call — asking
        the model to invent these for its own not-yet-finished response
        is nonsensical and, per live verification, made calls more
        likely to fail. It must never appear in the tool schema sent to
        the model."""
        from tradingos_api.schemas.agent_contract import AgentContractOutput
        from tradingos_api.services.agent_runner import _output_tool

        tool = _output_tool(AgentContractOutput)
        schema = tool["input_schema"]
        assert isinstance(schema, dict)
        assert "run_metadata" not in schema.get("properties", {})
        assert "run_metadata" not in schema.get("required", [])


class TestSuccessPath:
    def test_valid_response_is_parsed_and_succeeds(self) -> None:
        outcome = run_agent_role(
            prompt_version="v1",
            system_prompt="be a good analyst",
            user_content="analyze this",
            output_schema=_SimpleOutput,
            llm=_SucceedingLLM(),
            cost_ceiling_usd=Decimal("1.00"),
            spent_so_far_usd=Decimal("0"),
            timeout_seconds=30,
        )
        assert outcome.status == "SUCCEEDED"
        assert isinstance(outcome.output, _SimpleOutput)
        assert outcome.output.verdict == "bullish"
        assert outcome.cost_usd > 0


class TestCostCeiling:
    def test_role_is_not_called_once_the_ceiling_is_already_reached(self) -> None:
        outcome = run_agent_role(
            prompt_version="v1",
            system_prompt="be a good analyst",
            user_content="analyze this",
            output_schema=_SimpleOutput,
            llm=_SucceedingLLM(),
            cost_ceiling_usd=Decimal("1.00"),
            spent_so_far_usd=Decimal("1.00"),  # already at the ceiling
            timeout_seconds=30,
        )
        assert outcome.status == "DEGRADED"
        assert outcome.output is None
        assert "cost ceiling" in (outcome.error_detail or "")
        assert outcome.cost_usd == Decimal(0)

    def test_role_is_not_called_once_the_ceiling_is_exceeded(self) -> None:
        outcome = run_agent_role(
            prompt_version="v1",
            system_prompt="be a good analyst",
            user_content="analyze this",
            output_schema=_SimpleOutput,
            llm=_SucceedingLLM(),
            cost_ceiling_usd=Decimal("1.00"),
            spent_so_far_usd=Decimal("1.50"),
            timeout_seconds=30,
        )
        assert outcome.status == "DEGRADED"

    def test_role_runs_normally_when_under_the_ceiling(self) -> None:
        outcome = run_agent_role(
            prompt_version="v1",
            system_prompt="be a good analyst",
            user_content="analyze this",
            output_schema=_SimpleOutput,
            llm=_SucceedingLLM(),
            cost_ceiling_usd=Decimal("1.00"),
            spent_so_far_usd=Decimal("0.50"),
            timeout_seconds=30,
        )
        assert outcome.status == "SUCCEEDED"


class TestFallbackBehavior:
    def test_provider_not_configured_degrades_rather_than_crashes(self) -> None:
        outcome = run_agent_role(
            prompt_version="v1",
            system_prompt="be a good analyst",
            user_content="analyze this",
            output_schema=_SimpleOutput,
            llm=_NotConfiguredLLM(),
            cost_ceiling_usd=Decimal("1.00"),
            spent_so_far_usd=Decimal("0"),
            timeout_seconds=30,
        )
        assert outcome.status == "DEGRADED"
        assert "not configured" in (outcome.error_detail or "")

    def test_any_provider_exception_fails_this_role_without_raising(self) -> None:
        """A timeout, connection error, or rate-limit exception from any
        concrete `LLMProvider` (Anthropic-specific exception types are
        never imported here — this is provider-neutral) must degrade to
        a `FAILED` outcome for this one role, never propagate and crash
        the rest of the committee."""
        outcome = run_agent_role(
            prompt_version="v1",
            system_prompt="be a good analyst",
            user_content="analyze this",
            output_schema=_SimpleOutput,
            llm=_ExplodingLLM(),
            cost_ceiling_usd=Decimal("1.00"),
            spent_so_far_usd=Decimal("0"),
            timeout_seconds=30,
        )
        assert outcome.status == "FAILED"
        assert "RuntimeError" in (outcome.error_detail or "")

    def test_missing_tool_call_is_a_failed_outcome_not_a_crash(self) -> None:
        outcome = run_agent_role(
            prompt_version="v1",
            system_prompt="be a good analyst",
            user_content="analyze this",
            output_schema=_SimpleOutput,
            llm=_NoToolCallLLM(),
            cost_ceiling_usd=Decimal("1.00"),
            spent_so_far_usd=Decimal("0"),
            timeout_seconds=30,
        )
        assert outcome.status == "FAILED"
        assert "did not call" in (outcome.error_detail or "")
        # Metadata is still captured even on a structural failure, since a
        # real Anthropic call still happened and cost real money.
        assert outcome.model == "claude-sonnet-5"
        assert outcome.cost_usd > 0

    def test_malformed_tool_arguments_fail_schema_validation_not_a_crash(self) -> None:
        outcome = run_agent_role(
            prompt_version="v1",
            system_prompt="be a good analyst",
            user_content="analyze this",
            output_schema=_SimpleOutput,
            llm=_MalformedArgsLLM(),
            cost_ceiling_usd=Decimal("1.00"),
            spent_so_far_usd=Decimal("0"),
            timeout_seconds=30,
        )
        assert outcome.status == "FAILED"
        assert "schema validation failed" in (outcome.error_detail or "")


class TestTimeoutIsPassedThroughToTheProvider:
    def test_timeout_seconds_reaches_the_provider_call(self) -> None:
        received: dict[str, Any] = {}

        class _RecordingLLM:
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
                received["timeout_seconds"] = timeout_seconds
                received["tool_choice"] = tool_choice
                return LLMResponse(
                    prompt_version=prompt_version,
                    model="claude-sonnet-5",
                    stop_reason="tool_use",
                    text=None,
                    tool_calls=[
                        LLMToolCall(
                            tool_use_id="t1",
                            tool_name="submit_agent_output",
                            arguments=_valid_args(),
                        )
                    ],
                    raw_content=[],
                    input_tokens=100,
                    output_tokens=20,
                )

        run_agent_role(
            prompt_version="v1",
            system_prompt="be a good analyst",
            user_content="analyze this",
            output_schema=_SimpleOutput,
            llm=_RecordingLLM(),
            cost_ceiling_usd=Decimal("1.00"),
            spent_so_far_usd=Decimal("0"),
            timeout_seconds=12.5,
        )
        assert received["timeout_seconds"] == 12.5
        assert received["tool_choice"] == {
            "type": "tool",
            "name": "submit_agent_output",
            "disable_parallel_tool_use": True,
        }
