"""AI performance coach (Revision Prompt 12) — "the AI coach may
summarize behavior only when the sample is adequate and must display
sample size and uncertainty." Both halves of that requirement are
enforced structurally, not by prompt instruction alone:

1. **Sample adequacy is a code gate, not a model judgment call.** Below
   `MIN_SAMPLE_SIZE_FOR_SUMMARY` closed trades, this module never calls
   the LLM at all — `get_coach_summary()` returns a fixed, deterministic
   "insufficient sample" result. A model cannot be prompted into
   fabricating a summary from data it never received, because it is
   never invoked in that case.
2. **`sample_size` and `is_sample_adequate` are always computed
   independently of the model's own output** (`services/performance_portfolio.py`'s
   real trade count, not a number the LLM reports about itself) and
   returned alongside whatever narrative the model produces — a caller
   never has to trust the model's self-reported confidence.

Reuses `services/agent_runner.py::run_agent_role()` — the same cost-
ceiling/timeout/fallback/forced-structured-output guardrails Revision
Prompt 6's committees already established, applied here to a single
role rather than reinventing a parallel LLM-call path.
"""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, Field

from tradingos_api.providers.llm import LLMProvider
from tradingos_api.schemas.agent_contract import RunMetadata
from tradingos_api.services.agent_runner import run_agent_role
from tradingos_api.services.performance_portfolio import PortfolioPerformanceResult

CALCULATION_VERSION = "v1"
PROMPT_VERSION = "performance-coach-v1"
MIN_SAMPLE_SIZE_FOR_SUMMARY = 10
"""Documented placeholder threshold (no statistically-derived minimum
sample size exists for this project's own trade population — there
isn't a real trade history large enough yet to derive one from). Chosen
as "enough closed trades that a single outlier can't dominate the
win rate," the same qualitative reasoning `docs/HYBRID_EARNINGS_STRATEGY.md`
already applies to its own minimum-analyst-coverage gate."""

DEFAULT_COST_CEILING_USD = Decimal("0.10")
DEFAULT_TIMEOUT_SECONDS = 30.0

_SYSTEM_PROMPT = """You are a trading-behavior coach. You will be given \
already-computed performance statistics for a paper trading account. \
Your job is to summarize *behavior* in plain language for a human trader \
to read.

Rules, no exceptions:
- Use ONLY the numbers given to you. Never estimate, guess, or infer a \
number that was not provided.
- Never give individual trade recommendations, price targets, or \
buy/sell advice — this is a behavioral summary, not a trading signal.
- Your summary MUST explicitly state the sample size (number of closed \
trades) it is based on, and MUST include a plain-language caveat about \
statistical uncertainty appropriate to that sample size (a small sample \
deserves a stronger caveat than a large one).
- If a statistic was not provided or is null, say it is unavailable — \
never fill it in with a plausible-sounding guess."""


class CoachSummaryOutput(BaseModel):
    summary_text: str = Field(
        description=(
            "2-4 sentence plain-language behavioral summary. Must state the "
            "sample size and a proportional uncertainty caveat."
        )
    )
    key_observations: list[str] = Field(
        description=(
            "1-4 short bullet-point observations, each grounded in a specific provided number."
        )
    )
    run_metadata: RunMetadata


class CoachSummaryResult(BaseModel):
    sample_size: int
    is_sample_adequate: bool
    min_sample_size_required: int = MIN_SAMPLE_SIZE_FOR_SUMMARY
    narrative: CoachSummaryOutput | None
    """`None` whenever `is_sample_adequate` is `False` — the guardrail's
    only enforcement point, checked before any LLM call is made."""
    insufficient_sample_message: str | None


def _stats_summary_text(performance: PortfolioPerformanceResult) -> str:
    stats = performance.trade_stats
    return (
        f"closed_trades={stats.num_trades}, wins={stats.num_wins}, "
        f"losses={stats.num_losses}, win_rate_pct={stats.win_rate_pct}, "
        f"profit_factor={stats.profit_factor}, expectancy={stats.expectancy}, "
        f"payoff_ratio={stats.payoff_ratio}, "
        f"sharpe_ratio={performance.sharpe_ratio}, "
        f"sortino_ratio={performance.sortino_ratio}, "
        f"max_drawdown_pct={performance.drawdown.max_drawdown_pct}, "
        f"inception_return_pct={performance.inception_return_pct}, "
        f"annualized_volatility_pct={performance.annualized_volatility_pct}"
    )


def get_coach_summary(
    *,
    performance: PortfolioPerformanceResult,
    llm: LLMProvider | None,
    cost_ceiling_usd: Decimal = DEFAULT_COST_CEILING_USD,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
) -> CoachSummaryResult:
    """`llm` is `None` whenever the caller already knows the sample is
    inadequate (e.g. the router skips resolving an `LLMProvider` at all
    in that case, so a missing `ANTHROPIC_API_KEY` never blocks the
    common inadequate-sample path). Passing an adequate sample with
    `llm=None` is a caller bug, not a runtime state this function
    degrades gracefully for — it raises immediately."""
    sample_size = performance.trade_stats.num_trades
    is_adequate = sample_size >= MIN_SAMPLE_SIZE_FOR_SUMMARY

    if not is_adequate:
        return CoachSummaryResult(
            sample_size=sample_size,
            is_sample_adequate=False,
            narrative=None,
            insufficient_sample_message=(
                f"Only {sample_size} closed trade(s) recorded — at least "
                f"{MIN_SAMPLE_SIZE_FOR_SUMMARY} are required before a behavioral "
                "summary is generated. No summary was requested from the model."
            ),
        )

    if llm is None:
        raise ValueError("llm must be provided when the sample is adequate")

    outcome = run_agent_role(
        prompt_version=PROMPT_VERSION,
        system_prompt=_SYSTEM_PROMPT,
        user_content=_stats_summary_text(performance),
        output_schema=CoachSummaryOutput,
        llm=llm,
        cost_ceiling_usd=cost_ceiling_usd,
        spent_so_far_usd=Decimal(0),
        timeout_seconds=timeout_seconds,
    )

    if outcome.status != "SUCCEEDED" or outcome.output is None:
        return CoachSummaryResult(
            sample_size=sample_size,
            is_sample_adequate=True,
            narrative=None,
            insufficient_sample_message=(
                f"Sample was adequate ({sample_size} trades) but the summary "
                f"could not be generated: {outcome.error_detail or outcome.status}"
            ),
        )

    assert isinstance(outcome.output, CoachSummaryOutput)
    return CoachSummaryResult(
        sample_size=sample_size,
        is_sample_adequate=True,
        narrative=outcome.output,
        insufficient_sample_message=None,
    )
