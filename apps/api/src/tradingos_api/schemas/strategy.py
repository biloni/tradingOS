from datetime import date, datetime
from decimal import Decimal
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, field_serializer, model_validator

from tradingos_api.models.strategy_version import StrategyVersionStatus
from tradingos_api.schemas.backtest import BacktestRunOut


class StrategyWeights(BaseModel):
    trend: Decimal = Decimal("1.0")
    momentum: Decimal = Decimal("1.0")
    macd: Decimal = Decimal("1.0")
    bollinger: Decimal = Decimal("1.0")


class StrategyConfigIn(BaseModel):
    """Matches services/strategy.py's DEFAULT_CONFIG shape exactly — the
    only shape services/scoring.py's compute_score() understands. Typed
    fields, not an open dict, so a malformed proposal 422s instead of
    silently producing a broken (always-neutral) score."""

    weights: StrategyWeights = Field(default_factory=StrategyWeights)
    rsi_bullish_low: Decimal = Decimal("50")
    rsi_bullish_high: Decimal = Decimal("70")
    rsi_oversold: Decimal = Decimal("30")

    @model_validator(mode="after")
    def _check_rsi_band_order(self) -> Self:
        if self.rsi_bullish_low >= self.rsi_bullish_high:
            raise ValueError("rsi_bullish_low must be less than rsi_bullish_high")
        return self


class StrategyVersionCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    config: StrategyConfigIn = Field(default_factory=StrategyConfigIn)


class StrategyBacktestParams(BaseModel):
    """The optional backtest-parameter overrides shared by /compare and
    /approve, applied identically to both the candidate and the currently
    active version for a fair comparison (ADR-028). Same fields as
    schemas/backtest.py's BacktestCreateRequest, minus
    strategy_version_id — the path param already picks the candidate."""

    date_range_start: date | None = None
    date_range_end: date | None = None
    entry_score_threshold: Decimal = Decimal("65")
    exit_score_threshold: Decimal = Decimal("40")
    max_holding_days: int = Field(default=10, ge=1)
    position_size_pct: Decimal = Field(default=Decimal("0.10"), gt=0, le=1)
    starting_cash: Decimal = Field(default=Decimal("10000.00"), gt=0)
    benchmark_ticker: str | None = "SPY"


class StrategyVersionApproveRequest(StrategyBacktestParams):
    comment: str | None = None


class StrategyVersionRejectRequest(BaseModel):
    comment: str | None = None


class ComparisonDelta(BaseModel):
    """candidate minus active, for each numeric summary metric. Never used
    to auto-decide anything (ADR-028) — surfaced for a human to read."""

    total_return_pct: Decimal
    max_drawdown_pct: Decimal
    win_rate_pct: Decimal
    avg_win_pct: Decimal
    avg_loss_pct: Decimal
    num_trades: int

    @field_serializer(
        "total_return_pct", "max_drawdown_pct", "win_rate_pct", "avg_win_pct", "avg_loss_pct"
    )
    def _serialize_decimal_as_str(self, value: Decimal) -> str:
        return str(value)


class StrategyComparisonOut(BaseModel):
    candidate_backtest: BacktestRunOut
    active_backtest: BacktestRunOut
    delta: ComparisonDelta


class StrategyVersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    config: dict[str, Any]
    status: StrategyVersionStatus
    decided_at: datetime | None
    decision_comment: str | None
    created_at: datetime
