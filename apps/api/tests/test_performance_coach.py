"""AI performance coach tests (Revision Prompt 12) — the sample-size
guardrail is the entire point of this feature, so the primary thing
under test is that the LLM is structurally never invoked below the
threshold, not just that its output looks reasonable above it. Uses the
same fake-`LLMProvider` pattern as `test_agent_runner.py` (no network
call, no real Anthropic spend)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

import pytest

from tradingos_api.providers.llm import LLMProviderNotConfigured, LLMResponse, LLMToolCall
from tradingos_api.services.performance_coach import (
    MIN_SAMPLE_SIZE_FOR_SUMMARY,
    get_coach_summary,
)
from tradingos_api.services.performance_metrics import DrawdownResult, TradeStatsResult
from tradingos_api.services.performance_portfolio import PortfolioPerformanceResult


def _trade_stats(num_trades: int) -> TradeStatsResult:
    return TradeStatsResult(
        num_trades=num_trades,
        num_wins=num_trades,
        num_losses=0,
        num_breakeven=0,
        win_rate_pct=Decimal(100) if num_trades else None,
        avg_win=Decimal("10") if num_trades else None,
        avg_loss=None,
        payoff_ratio=None,
        profit_factor=None,
        expectancy=Decimal("10") if num_trades else None,
    )


def _performance(num_trades: int) -> PortfolioPerformanceResult:
    return PortfolioPerformanceResult(
        as_of=date(2026, 8, 9),
        equity=Decimal("10000"),
        cash=Decimal("10000"),
        market_value=Decimal(0),
        daily_return_pct=None,
        weekly_return_pct=None,
        monthly_return_pct=None,
        ytd_return_pct=None,
        inception_return_pct=Decimal("0.05"),
        time_weighted_return_pct=Decimal("0.05"),
        money_weighted_return_pct=Decimal("0.05"),
        realized_pnl=Decimal("100"),
        unrealized_pnl=Decimal(0),
        trade_stats=_trade_stats(num_trades),
        annualized_volatility_pct=Decimal("12"),
        sharpe_ratio=Decimal("1.2"),
        sortino_ratio=Decimal("1.5"),
        drawdown=DrawdownResult(
            max_drawdown_pct=Decimal("-2.5"),
            peak_index=0,
            trough_index=1,
            recovery_index=2,
            recovery_periods=1,
        ),
        beta_vs_spy=Decimal("0.8"),
        alpha_vs_spy_pct=Decimal("1.1"),
        gross_exposure_pct=Decimal("40"),
        concentration_hhi=Decimal("0.3"),
        turnover_pct_30d=Decimal("15"),
        cash_history=[],
        sample_size_days=90,
    )


def _valid_coach_args() -> dict[str, Any]:
    return {
        "summary_text": "Based on 12 trades, win rate is high but the sample is still small.",
        "key_observations": ["Win rate 100%", "Small sample size limits confidence"],
    }


class _NeverCalledLLM:
    """Asserts the coach never reaches the LLM at all below threshold —
    the guardrail is a code gate, not a prompt instruction, so calling
    this at all is a test failure regardless of what it would return."""

    def complete(self, *args: Any, **kwargs: Any) -> LLMResponse:
        raise AssertionError("LLM must not be called when the sample is inadequate")


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
                    tool_use_id="t1",
                    tool_name="submit_agent_output",
                    arguments=_valid_coach_args(),
                )
            ],
            raw_content=[],
            input_tokens=500,
            output_tokens=120,
        )


class _NotConfiguredLLM:
    def complete(self, *args: Any, **kwargs: Any) -> LLMResponse:
        raise LLMProviderNotConfigured("ANTHROPIC_API_KEY is not set.")


class TestSampleSizeGuardrail:
    def test_zero_trades_never_calls_llm(self) -> None:
        result = get_coach_summary(performance=_performance(0), llm=_NeverCalledLLM())
        assert result.is_sample_adequate is False
        assert result.sample_size == 0
        assert result.narrative is None
        assert result.insufficient_sample_message is not None

    def test_one_below_threshold_never_calls_llm(self) -> None:
        result = get_coach_summary(
            performance=_performance(MIN_SAMPLE_SIZE_FOR_SUMMARY - 1), llm=_NeverCalledLLM()
        )
        assert result.is_sample_adequate is False
        assert result.narrative is None

    def test_exactly_at_threshold_is_adequate(self) -> None:
        result = get_coach_summary(
            performance=_performance(MIN_SAMPLE_SIZE_FOR_SUMMARY), llm=_SucceedingLLM()
        )
        assert result.is_sample_adequate is True
        assert result.sample_size == MIN_SAMPLE_SIZE_FOR_SUMMARY
        assert result.narrative is not None

    def test_inadequate_sample_llm_argument_is_optional(self) -> None:
        """The router passes `llm=None` outright when it already knows
        the sample is inadequate — this must not raise."""
        result = get_coach_summary(performance=_performance(0), llm=None)
        assert result.is_sample_adequate is False
        assert result.narrative is None

    def test_adequate_sample_requires_llm(self) -> None:
        with pytest.raises(ValueError, match="llm must be provided"):
            get_coach_summary(performance=_performance(MIN_SAMPLE_SIZE_FOR_SUMMARY), llm=None)


class TestAdequateSampleNarrative:
    def test_narrative_reports_real_sample_size_independent_of_model(self) -> None:
        result = get_coach_summary(
            performance=_performance(MIN_SAMPLE_SIZE_FOR_SUMMARY + 5), llm=_SucceedingLLM()
        )
        assert result.sample_size == MIN_SAMPLE_SIZE_FOR_SUMMARY + 5
        assert result.narrative is not None
        assert result.narrative.run_metadata.model == "claude-sonnet-5"
        assert result.narrative.run_metadata.input_tokens == 500
        assert result.narrative.run_metadata.output_tokens == 120

    def test_provider_not_configured_degrades_without_crash(self) -> None:
        result = get_coach_summary(
            performance=_performance(MIN_SAMPLE_SIZE_FOR_SUMMARY), llm=_NotConfiguredLLM()
        )
        assert result.is_sample_adequate is True
        assert result.narrative is None
        assert result.insufficient_sample_message is not None
        assert "could not be generated" in result.insufficient_sample_message
