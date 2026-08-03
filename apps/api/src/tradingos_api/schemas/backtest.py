from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_serializer


class BacktestCreateRequest(BaseModel):
    """Every field is optional — `date_range_start`/`date_range_end` default
    to the full ~2-year ingested history (see routers/backtest.py); the
    strategy/entry/exit/sizing params default per ADR-023."""

    date_range_start: date | None = None
    date_range_end: date | None = None
    strategy_version_id: int | None = None
    entry_score_threshold: Decimal = Decimal("65")
    exit_score_threshold: Decimal = Decimal("40")
    max_holding_days: int = Field(default=10, ge=1)
    position_size_pct: Decimal = Field(default=Decimal("0.10"), gt=0, le=1)
    starting_cash: Decimal = Field(default=Decimal("10000.00"), gt=0)
    benchmark_ticker: str | None = "SPY"


class TradeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    ticker: str
    entry_date: date
    entry_price: Decimal
    exit_date: date
    exit_price: Decimal
    quantity: int
    pnl_usd: Decimal
    pnl_pct: Decimal
    exit_reason: str

    @field_serializer("entry_price", "exit_price", "pnl_usd", "pnl_pct")
    def _serialize_decimal_as_str(self, value: Decimal) -> str:
        return str(value)


class EquityPointOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    as_of: date
    equity: Decimal

    @field_serializer("equity")
    def _serialize_decimal_as_str(self, value: Decimal) -> str:
        return str(value)


class ResultsSummaryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    ending_equity: Decimal
    total_return_pct: Decimal
    max_drawdown_pct: Decimal
    win_rate_pct: Decimal
    num_trades: int
    avg_win_pct: Decimal
    avg_loss_pct: Decimal
    benchmark_return_pct: Decimal | None
    equity_curve: list[EquityPointOut]
    trades: list[TradeOut]

    @field_serializer(
        "ending_equity",
        "total_return_pct",
        "max_drawdown_pct",
        "win_rate_pct",
        "avg_win_pct",
        "avg_loss_pct",
        "benchmark_return_pct",
    )
    def _serialize_decimal_as_str(self, value: Decimal | None) -> str | None:
        return str(value) if value is not None else None


class BacktestParametersOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    entry_score_threshold: Decimal
    exit_score_threshold: Decimal
    max_holding_days: int
    position_size_pct: Decimal
    starting_cash: Decimal
    benchmark_ticker: str | None

    @field_serializer(
        "entry_score_threshold", "exit_score_threshold", "position_size_pct", "starting_cash"
    )
    def _serialize_decimal_as_str(self, value: Decimal) -> str:
        return str(value)


class BacktestRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    strategy_version_id: int
    date_range_start: date
    date_range_end: date
    parameters: BacktestParametersOut
    results_summary: ResultsSummaryOut
    created_at: datetime
