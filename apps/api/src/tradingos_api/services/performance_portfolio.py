"""Live-portfolio performance computation (Revision Prompt 12) — the
DB-aware layer that gathers real `CashLedgerEntry`/`Execution`/
`MarketBar`/`Trade` facts and feeds them into
`services/performance_metrics.py`'s pure statistics functions. Nothing
here computes a formula itself (no re-implemented Sharpe/drawdown math)
— this module's only job is "derive the correct inputs from the real
schema," matching this project's derived-never-stored philosophy
(ADR-013) extended to performance reporting: there is no persisted
daily equity-curve table to fall out of sync with the ledger it's
supposed to summarize.

`DEPOSIT`/`WITHDRAWAL` are the only two `CashLedgerEntryType` values
that represent a genuine *external* flow for time-weighted-return
purposes — `TRADE_DEBIT`/`TRADE_CREDIT`/`FEE`/`DIVIDEND`/`INTEREST` are
internal (cash converting to/from position value, or P&L already
reflected in market value) and must never be treated as an external
flow boundary. An account with no deposit/withdrawal activity (the
common case in this dev environment) degenerates correctly to a single
TWR sub-period and a simple two-flow IRR — not a special case, just the
general formula applied to a smaller cash-flow list.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from tradingos_api.models.enums import CashLedgerEntryType, OrderSide, Timeframe, TradeStatus
from tradingos_api.models.execution import (
    Account,
    CashLedgerEntry,
    Execution,
    Order,
    Position,
    Trade,
)
from tradingos_api.models.market_evidence import MarketBar
from tradingos_api.models.security_master import Instrument
from tradingos_api.services.market_calendar import resolve_trading_day
from tradingos_api.services.performance_metrics import (
    CashFlow,
    DrawdownResult,
    TradeStatsResult,
    annualized_volatility,
    beta_alpha,
    compute_trade_stats,
    concentration_hhi,
    daily_returns_from_equity_curve,
    max_drawdown,
    money_weighted_return_irr,
    sharpe_ratio,
    sortino_ratio,
    time_weighted_return,
    turnover_pct,
)

CALCULATION_VERSION = "v1"
_SPY_TICKER = "SPY"


@dataclass(frozen=True)
class EquityPoint:
    as_of: date
    cash: Decimal
    market_value: Decimal
    equity: Decimal


def _instrument_daily_quantity(
    db: Session, *, account_id: uuid.UUID
) -> dict[uuid.UUID, list[tuple[date, Decimal]]]:
    """Cumulative held quantity per instrument, one point per calendar
    date an execution changed it — a step function the caller
    interpolates forward from (quantity is flat between fills)."""
    rows = db.execute(
        select(Execution.executed_at, Execution.quantity, Order.instrument_id, Order.side)
        .join(Order, Execution.order_id == Order.id)
        .where(Order.account_id == account_id)
        .order_by(Execution.executed_at.asc())
    ).all()

    running: dict[uuid.UUID, Decimal] = {}
    series: dict[uuid.UUID, list[tuple[date, Decimal]]] = {}
    for executed_at, quantity, instrument_id, side in rows:
        signed = quantity if side == OrderSide.BUY else -quantity
        running[instrument_id] = running.get(instrument_id, Decimal(0)) + signed
        series.setdefault(instrument_id, []).append((executed_at.date(), running[instrument_id]))
    return series


def _quantity_as_of(points: list[tuple[date, Decimal]], as_of: date) -> Decimal:
    quantity = Decimal(0)
    for point_date, cumulative in points:
        if point_date <= as_of:
            quantity = cumulative
        else:
            break
    return quantity


def _latest_close_as_of(db: Session, *, instrument_id: uuid.UUID, as_of: date) -> Decimal | None:
    row = db.scalar(
        select(MarketBar.close)
        .where(
            MarketBar.instrument_id == instrument_id,
            MarketBar.timeframe == Timeframe.DAILY,
            MarketBar.as_of <= as_of,
        )
        .order_by(MarketBar.as_of.desc())
        .limit(1)
    )
    return row


def get_equity_curve(db: Session, *, account: Account, start: date, end: date) -> list[EquityPoint]:
    """One point per real trading day in `[start, end]` — cash from the
    ledger, market value from the last known close at/before that day
    for each instrument's quantity as of that day. A day with no
    `MarketBar` yet for a held instrument silently carries the position
    at its last known price rather than dropping it from market value —
    the same "last known close, never that day's own close" discipline
    ADR-022's retired backtest engine already established, reused here
    because the reasoning is identical (no look-ahead into a price that
    isn't knowable yet if this were being computed intraday)."""
    quantity_series = _instrument_daily_quantity(db, account_id=account.id)
    ledger_rows = db.execute(
        select(CashLedgerEntry.occurred_at, CashLedgerEntry.amount).where(
            CashLedgerEntry.account_id == account.id
        )
    ).all()

    points: list[EquityPoint] = []
    current = start
    while current <= end:
        resolution = resolve_trading_day(current)
        if resolution.is_trading_day:
            cash = account.starting_cash + sum(
                (amount for occurred_at, amount in ledger_rows if occurred_at.date() <= current),
                Decimal(0),
            )
            market_value = Decimal(0)
            for instrument_id, points_series in quantity_series.items():
                qty = _quantity_as_of(points_series, current)
                if qty == 0:
                    continue
                close = _latest_close_as_of(db, instrument_id=instrument_id, as_of=current)
                if close is not None:
                    market_value += qty * close
            points.append(
                EquityPoint(
                    as_of=current, cash=cash, market_value=market_value, equity=cash + market_value
                )
            )
        current += timedelta(days=1)
    return points


def _external_cash_flows(db: Session, *, account: Account) -> list[tuple[datetime, Decimal]]:
    rows = db.scalars(
        select(CashLedgerEntry).where(
            CashLedgerEntry.account_id == account.id,
            CashLedgerEntry.entry_type.in_(
                [CashLedgerEntryType.DEPOSIT, CashLedgerEntryType.WITHDRAWAL]
            ),
        )
    ).all()
    return [(r.occurred_at, r.amount) for r in rows]


def _twr_from_equity_curve_with_flows(
    curve: list[EquityPoint], flows: list[tuple[datetime, Decimal]]
) -> Decimal | None:
    """Splits the equity curve into sub-periods at each external
    flow's date and chains the sub-period returns — degenerates to a
    single whole-period return when `flows` is empty."""
    if len(curve) < 2:
        return None
    flow_dates = sorted({f[0].date() for f in flows})
    boundaries = [curve[0].as_of, *flow_dates, curve[-1].as_of]
    sub_returns: list[Decimal] = []
    for i in range(len(boundaries) - 1):
        start_d, end_d = boundaries[i], boundaries[i + 1]
        start_points = [p for p in curve if p.as_of >= start_d]
        end_points = [p for p in curve if p.as_of <= end_d]
        if not start_points or not end_points:
            continue
        start_equity = start_points[0].equity
        end_equity = end_points[-1].equity
        if start_equity == 0:
            continue
        sub_returns.append((end_equity - start_equity) / start_equity)
    if not sub_returns:
        return None
    return time_weighted_return(sub_returns)


def _mwr_irr(
    account: Account, curve: list[EquityPoint], flows: list[tuple[datetime, Decimal]]
) -> Decimal | None:
    if not curve:
        return None
    start_date = curve[0].as_of
    cash_flows = [CashFlow(0, -account.starting_cash)]
    for occurred_at, amount in flows:
        days = (occurred_at.date() - start_date).days
        # A deposit is money going IN to the account (a further
        # outlay, negative); a withdrawal is money coming OUT
        # (positive) — opposite sign from the ledger's own
        # credit/debit convention, which is why this isn't just
        # `amount` passed through unchanged.
        cash_flows.append(CashFlow(days, -amount if amount > 0 else abs(amount)))
    final_days = (curve[-1].as_of - start_date).days
    cash_flows.append(CashFlow(final_days, curve[-1].equity))
    return money_weighted_return_irr(cash_flows)


def _return_over_lookback(curve: list[EquityPoint], *, days: int) -> Decimal | None:
    if len(curve) < 2:
        return None
    end_point = curve[-1]
    cutoff = end_point.as_of - timedelta(days=days)
    candidates = [p for p in curve if p.as_of <= cutoff]
    start_point = candidates[-1] if candidates else curve[0]
    if start_point.equity == 0:
        return None
    return (end_point.equity - start_point.equity) / start_point.equity


def _ytd_return(curve: list[EquityPoint]) -> Decimal | None:
    if not curve:
        return None
    year_start = date(curve[-1].as_of.year, 1, 1)
    candidates = [p for p in curve if p.as_of < year_start]
    start_point = candidates[-1] if candidates else curve[0]
    if start_point.equity == 0:
        return None
    return (curve[-1].equity - start_point.equity) / start_point.equity


@dataclass(frozen=True)
class PortfolioPerformanceResult:
    as_of: date
    equity: Decimal | None
    cash: Decimal | None
    market_value: Decimal | None
    daily_return_pct: Decimal | None
    weekly_return_pct: Decimal | None
    monthly_return_pct: Decimal | None
    ytd_return_pct: Decimal | None
    inception_return_pct: Decimal | None
    time_weighted_return_pct: Decimal | None
    money_weighted_return_pct: Decimal | None
    realized_pnl: Decimal
    unrealized_pnl: Decimal
    trade_stats: TradeStatsResult
    annualized_volatility_pct: Decimal | None
    sharpe_ratio: Decimal | None
    sortino_ratio: Decimal | None
    drawdown: DrawdownResult
    beta_vs_spy: Decimal | None
    alpha_vs_spy_pct: Decimal | None
    gross_exposure_pct: Decimal | None
    concentration_hhi: Decimal
    turnover_pct_30d: Decimal | None
    cash_history: list[EquityPoint]
    sample_size_days: int
    calculation_version: str = CALCULATION_VERSION


def _closed_trade_pnls(db: Session, *, account_id: uuid.UUID) -> list[Decimal]:
    rows = db.scalars(
        select(Trade.realized_pnl).where(
            Trade.account_id == account_id,
            Trade.status == TradeStatus.CLOSED,
            Trade.realized_pnl.is_not(None),
        )
    ).all()
    return [pnl for pnl in rows if pnl is not None]


def _unrealized_pnl(db: Session, *, account_id: uuid.UUID, as_of: date) -> Decimal:
    positions = db.scalars(select(Position).where(Position.account_id == account_id)).all()
    total = Decimal(0)
    for position in positions:
        if position.quantity == 0:
            continue
        close = _latest_close_as_of(db, instrument_id=position.instrument_id, as_of=as_of)
        if close is None:
            continue
        total += (close - position.avg_cost) * position.quantity
    return total


def _spy_returns(db: Session, *, curve_dates: list[date]) -> list[tuple[date, Decimal]]:
    spy = db.scalar(select(Instrument).where(Instrument.ticker == _SPY_TICKER))
    if spy is None or len(curve_dates) < 2:
        return []
    bars = db.scalars(
        select(MarketBar)
        .where(
            MarketBar.instrument_id == spy.id,
            MarketBar.timeframe == Timeframe.DAILY,
            MarketBar.as_of >= curve_dates[0],
            MarketBar.as_of <= curve_dates[-1],
        )
        .order_by(MarketBar.as_of.asc())
    ).all()
    closes_by_date = {b.as_of: b.close for b in bars}
    ordered_dates = sorted(closes_by_date.keys())
    returns: list[tuple[date, Decimal]] = []
    for i in range(1, len(ordered_dates)):
        prev, cur = ordered_dates[i - 1], ordered_dates[i]
        prev_close, cur_close = closes_by_date[prev], closes_by_date[cur]
        if prev_close == 0:
            continue
        returns.append((cur, (cur_close - prev_close) / prev_close))
    return returns


def get_portfolio_performance(
    db: Session, *, account: Account, as_of: date, lookback_days: int = 400
) -> PortfolioPerformanceResult:
    start = as_of - timedelta(days=lookback_days)
    curve = get_equity_curve(db, account=account, start=start, end=as_of)
    flows = _external_cash_flows(db, account=account)

    daily_returns = daily_returns_from_equity_curve([p.equity for p in curve])
    dated_returns = [(curve[i].as_of, r) for i, r in enumerate(daily_returns, start=1)]

    inception_return = None
    if curve and curve[0].equity != 0:
        inception_return = (curve[-1].equity - curve[0].equity) / curve[0].equity

    positions = db.scalars(select(Position).where(Position.account_id == account.id)).all()
    equity_now = curve[-1].equity if curve else None
    position_weights = []
    gross_exposure = Decimal(0)
    for position in positions:
        if position.quantity == 0 or equity_now in (None, Decimal(0)):
            continue
        close = _latest_close_as_of(db, instrument_id=position.instrument_id, as_of=as_of)
        if close is None:
            continue
        assert equity_now is not None
        notional = abs(position.quantity * close)
        gross_exposure += notional
        position_weights.append((notional / equity_now) * Decimal(100))

    gross_exposure_pct = (
        (gross_exposure / equity_now) * Decimal(100)
        if equity_now not in (None, Decimal(0))
        else None
    )

    spy_dated_returns = _spy_returns(db, curve_dates=[p.as_of for p in curve])
    spy_by_date = dict(spy_dated_returns)
    aligned_portfolio = [r for d, r in dated_returns if d in spy_by_date]
    aligned_spy = [spy_by_date[d] for d, r in dated_returns if d in spy_by_date]
    beta, alpha = beta_alpha(aligned_portfolio, aligned_spy) if aligned_portfolio else (None, None)

    turnover_start = as_of - timedelta(days=30)
    buy_notional = db.scalar(
        select(Execution.quantity * Execution.price)
        .join(Order, Execution.order_id == Order.id)
        .where(
            Order.account_id == account.id,
            Order.side == OrderSide.BUY,
            Execution.executed_at >= datetime.combine(turnover_start, datetime.min.time(), UTC),
        )
    )
    sell_notional = db.scalar(
        select(Execution.quantity * Execution.price)
        .join(Order, Execution.order_id == Order.id)
        .where(
            Order.account_id == account.id,
            Order.side == OrderSide.SELL,
            Execution.executed_at >= datetime.combine(turnover_start, datetime.min.time(), UTC),
        )
    )
    avg_equity_30d = _mean_equity(curve, since=turnover_start) if curve else None
    turnover = (
        turnover_pct(buy_notional or Decimal(0), sell_notional or Decimal(0), avg_equity_30d)
        if avg_equity_30d
        else None
    )

    return PortfolioPerformanceResult(
        as_of=as_of,
        equity=equity_now,
        cash=curve[-1].cash if curve else None,
        market_value=curve[-1].market_value if curve else None,
        daily_return_pct=_return_over_lookback(curve, days=1),
        weekly_return_pct=_return_over_lookback(curve, days=7),
        monthly_return_pct=_return_over_lookback(curve, days=30),
        ytd_return_pct=_ytd_return(curve),
        inception_return_pct=inception_return,
        time_weighted_return_pct=_twr_from_equity_curve_with_flows(curve, flows),
        money_weighted_return_pct=_mwr_irr(account, curve, flows),
        realized_pnl=sum(_closed_trade_pnls(db, account_id=account.id), Decimal(0)),
        unrealized_pnl=_unrealized_pnl(db, account_id=account.id, as_of=as_of),
        trade_stats=compute_trade_stats(_closed_trade_pnls(db, account_id=account.id)),
        annualized_volatility_pct=annualized_volatility(daily_returns),
        sharpe_ratio=sharpe_ratio(daily_returns),
        sortino_ratio=sortino_ratio(daily_returns),
        drawdown=max_drawdown([p.equity for p in curve]),
        beta_vs_spy=beta,
        alpha_vs_spy_pct=alpha,
        gross_exposure_pct=gross_exposure_pct,
        concentration_hhi=concentration_hhi(position_weights),
        turnover_pct_30d=turnover,
        cash_history=curve,
        sample_size_days=len(curve),
    )


def _mean_equity(curve: list[EquityPoint], *, since: date) -> Decimal | None:
    relevant = [p.equity for p in curve if p.as_of >= since]
    if not relevant:
        return None
    return sum(relevant, Decimal(0)) / Decimal(len(relevant))
