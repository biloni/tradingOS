"""Historical replay engine (principle 14: no look-ahead bias, no
survivorship bias, no unrealistic fills — see ADR-022..025).

This module is split the same way services/indicators.py and
services/scoring.py are: a pure simulation core with no DB/ORM dependency
(unit-tested with hand-authored fixtures, see tests/test_backtest_simulation.py),
and a thin DB-facing wrapper (`run_backtest`, below the pure core) that
loads real `PriceBar`/`Indicator` history and persists a `BacktestRun`.

Fill-timing convention (ADR-022): a day's score is computed from that same
day's own close, so it can't be acted on until the day is already over —
every entry/exit decision fills at the *next* bar in that symbol's own
series (never same-day, never calendar-day arithmetic, since a symbol can
have data gaps). A decision made on a symbol's last loaded bar has no next
bar to fill against and is dropped, not executed.

Every day is processed in two passes, in ticker order (ADR-022): first,
fire any fills queued from a prior day's decision (exits before entries,
so entries can use cash exits just freed); second, evaluate *today's*
data for fresh exit/entry decisions, which queue a *future* fill. Equity
used for position-sizing is computed once per day from cash plus each
open position's last known close *before* today's close is folded in
(today's close isn't knowable at the moment of a same-day fill against
today's open) — using today's own close for that would itself be a subtle
form of look-ahead.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from tradingos_api.models.backtest_run import BacktestRun
from tradingos_api.models.strategy_version import StrategyVersion
from tradingos_api.models.symbol import Symbol
from tradingos_api.services.audit import record_audit_event
from tradingos_api.services.indicators import get_indicator_series_for_symbol
from tradingos_api.services.price_bars import get_latest_price_bars
from tradingos_api.services.scoring import compute_score
from tradingos_api.services.strategy import get_or_create_default_strategy_version

ExitReason = Literal["SIGNAL_EXIT", "MAX_HOLDING_DAYS", "END_OF_BACKTEST"]


@dataclass(frozen=True)
class SymbolBar:
    as_of: date
    open: Decimal
    close: Decimal


@dataclass(frozen=True)
class SymbolSeries:
    """One symbol's price history plus its indicator series for the
    backtest window. `bars` must be sorted ascending by `as_of` — fills
    resolve to the *next* entry in this list, not calendar-day arithmetic
    (ADR-022), so a gap in this symbol's own history is handled correctly
    without any special-casing."""

    ticker: str
    symbol_id: int
    bars: list[SymbolBar]
    indicators_by_date: dict[date, dict[str, Decimal]] = field(default_factory=dict)


@dataclass(frozen=True)
class BacktestParams:
    entry_score_threshold: Decimal = Decimal("65")
    exit_score_threshold: Decimal = Decimal("40")
    max_holding_days: int = 10
    position_size_pct: Decimal = Decimal("0.10")
    starting_cash: Decimal = Decimal("10000.00")


@dataclass(frozen=True)
class Trade:
    ticker: str
    entry_date: date
    entry_price: Decimal
    exit_date: date
    exit_price: Decimal
    quantity: int
    pnl_usd: Decimal
    pnl_pct: Decimal
    exit_reason: ExitReason


@dataclass(frozen=True)
class EquityPoint:
    as_of: date
    equity: Decimal


@dataclass(frozen=True)
class BacktestSimulationResult:
    equity_curve: list[EquityPoint]
    trades: list[Trade]
    ending_equity: Decimal
    total_return_pct: Decimal
    max_drawdown_pct: Decimal
    win_rate_pct: Decimal
    num_trades: int
    avg_win_pct: Decimal
    avg_loss_pct: Decimal


@dataclass
class _OpenPosition:
    entry_date: date
    entry_price: Decimal
    quantity: int


def _max_drawdown_pct(equity_curve: list[EquityPoint]) -> Decimal:
    if not equity_curve:
        return Decimal(0)
    peak = equity_curve[0].equity
    max_dd = Decimal(0)
    for point in equity_curve:
        peak = max(peak, point.equity)
        if peak > 0:
            drawdown = (peak - point.equity) / peak * 100
            max_dd = max(max_dd, drawdown)
    return max_dd


def _trade_metrics(
    trades: list[Trade],
) -> tuple[Decimal, Decimal, Decimal]:
    """(win_rate_pct, avg_win_pct, avg_loss_pct). A trade with `pnl_usd > 0`
    is a win; `pnl_usd <= 0` (including exact breakeven) is a loss."""
    if not trades:
        return Decimal(0), Decimal(0), Decimal(0)

    wins = [t for t in trades if t.pnl_usd > 0]
    losses = [t for t in trades if t.pnl_usd <= 0]

    win_rate_pct = Decimal(len(wins)) / Decimal(len(trades)) * 100
    avg_win_pct = sum((t.pnl_pct for t in wins), Decimal(0)) / len(wins) if wins else Decimal(0)
    avg_loss_pct = (
        sum((t.pnl_pct for t in losses), Decimal(0)) / len(losses) if losses else Decimal(0)
    )
    return win_rate_pct, avg_win_pct, avg_loss_pct


def compute_buy_and_hold_return_pct(first_close: Decimal, last_close: Decimal) -> Decimal:
    """Pure helper for a benchmark's simple buy-and-hold return over a
    window — same formula as any trade's `pnl_pct`, just over the whole
    range instead of one position."""
    if first_close == 0:
        return Decimal(0)
    return (last_close - first_close) / first_close * 100


def run_backtest_simulation(
    trading_calendar: list[date],
    symbol_series: dict[str, SymbolSeries],
    strategy_config: dict[str, Any],
    params: BacktestParams,
) -> BacktestSimulationResult:
    """Pure simulation core — no DB/ORM. `trading_calendar` is the sorted,
    deduped union of every symbol's `as_of` dates within the requested
    window (built by the caller from real `PriceBar` data). Processes
    symbols in a fixed alphabetical-ticker order every day so results are
    reproducible given the same inputs (ADR-022)."""
    if not trading_calendar:
        return BacktestSimulationResult(
            equity_curve=[],
            trades=[],
            ending_equity=params.starting_cash,
            total_return_pct=Decimal(0),
            max_drawdown_pct=Decimal(0),
            win_rate_pct=Decimal(0),
            num_trades=0,
            avg_win_pct=Decimal(0),
            avg_loss_pct=Decimal(0),
        )

    tickers = sorted(symbol_series.keys())
    calendar_index = {day: i for i, day in enumerate(trading_calendar)}
    bar_index_by_ticker: dict[str, dict[date, int]] = {
        ticker: {bar.as_of: i for i, bar in enumerate(series.bars)}
        for ticker, series in symbol_series.items()
    }

    cash = params.starting_cash
    open_positions: dict[str, _OpenPosition] = {}
    pending_exit_reason: dict[str, ExitReason] = {}
    pending_exits: dict[date, list[str]] = defaultdict(list)
    pending_entries: dict[date, list[str]] = defaultdict(list)
    last_known_close: dict[str, Decimal] = {}
    trades: list[Trade] = []
    equity_curve: list[EquityPoint] = []

    for day in trading_calendar:
        # 1. Fire exits queued from an earlier day's decision, at today's open.
        for ticker in sorted(pending_exits.get(day, [])):
            idx = bar_index_by_ticker[ticker].get(day)
            pos = open_positions.pop(ticker, None)
            if idx is None or pos is None:
                continue
            fill_price = symbol_series[ticker].bars[idx].open
            pnl_usd = (fill_price - pos.entry_price) * pos.quantity
            pnl_pct = (
                (fill_price - pos.entry_price) / pos.entry_price * 100
                if pos.entry_price != 0
                else Decimal(0)
            )
            cash += fill_price * pos.quantity
            trades.append(
                Trade(
                    ticker=ticker,
                    entry_date=pos.entry_date,
                    entry_price=pos.entry_price,
                    exit_date=day,
                    exit_price=fill_price,
                    quantity=pos.quantity,
                    pnl_usd=pnl_usd,
                    pnl_pct=pnl_pct,
                    exit_reason=pending_exit_reason.pop(ticker, "SIGNAL_EXIT"),
                )
            )

        # 2. Fire entries queued from an earlier day's decision, at today's
        # open. Equity for sizing is snapshotted once here (post-exit cash,
        # pre-today closes) — cash itself still updates per fill so a later
        # entry the same day can't overdraw what an earlier one just spent.
        equity_for_sizing = cash + sum(
            (
                last_known_close.get(t, p.entry_price) * p.quantity
                for t, p in open_positions.items()
            ),
            Decimal(0),
        )
        for ticker in sorted(pending_entries.get(day, [])):
            if ticker in open_positions:
                continue
            idx = bar_index_by_ticker[ticker].get(day)
            if idx is None:
                continue
            fill_price = symbol_series[ticker].bars[idx].open
            if fill_price <= 0:
                continue
            budget = min(cash, equity_for_sizing * params.position_size_pct)
            quantity = int(budget // fill_price)
            if quantity < 1:
                continue
            cost = fill_price * quantity
            cash -= cost
            open_positions[ticker] = _OpenPosition(
                entry_date=day, entry_price=fill_price, quantity=quantity
            )

        pending_exits.pop(day, None)
        pending_entries.pop(day, None)
        pending_tickers = {t for tickers_ in pending_exits.values() for t in tickers_} | {
            t for tickers_ in pending_entries.values() for t in tickers_
        }

        # 3. Evaluate today's own data for fresh decisions — these queue a
        # FUTURE fill, never today's (the day is only "over," and thus
        # actionable, once its own close exists).
        for ticker in tickers:
            idx = bar_index_by_ticker[ticker].get(day)
            if idx is None:
                continue
            series = symbol_series[ticker]
            bar = series.bars[idx]
            indicators_today = series.indicators_by_date.get(day, {})
            score_result = compute_score(bar.close, indicators_today, strategy_config)

            if ticker in open_positions and ticker not in pending_tickers:
                pos = open_positions[ticker]
                holding_days = calendar_index[day] - calendar_index[pos.entry_date]
                reason: ExitReason | None = None
                if score_result.score <= params.exit_score_threshold:
                    reason = "SIGNAL_EXIT"
                elif holding_days >= params.max_holding_days:
                    reason = "MAX_HOLDING_DAYS"
                if reason is not None and idx + 1 < len(series.bars):
                    fill_date = series.bars[idx + 1].as_of
                    pending_exits[fill_date].append(ticker)
                    pending_exit_reason[ticker] = reason
            elif ticker not in open_positions and ticker not in pending_tickers:
                if score_result.score >= params.entry_score_threshold and idx + 1 < len(
                    series.bars
                ):
                    fill_date = series.bars[idx + 1].as_of
                    pending_entries[fill_date].append(ticker)

            last_known_close[ticker] = bar.close

        equity = cash + sum(
            (
                last_known_close.get(t, p.entry_price) * p.quantity
                for t, p in open_positions.items()
            ),
            Decimal(0),
        )
        equity_curve.append(EquityPoint(as_of=day, equity=equity))

    # End of window: force-close anything still open at its last known
    # close (not a real signal — ADR-022).
    final_day = trading_calendar[-1]
    for ticker in sorted(open_positions.keys()):
        pos = open_positions[ticker]
        fill_price = last_known_close.get(ticker, pos.entry_price)
        pnl_usd = (fill_price - pos.entry_price) * pos.quantity
        pnl_pct = (
            (fill_price - pos.entry_price) / pos.entry_price * 100
            if pos.entry_price != 0
            else Decimal(0)
        )
        cash += fill_price * pos.quantity
        trades.append(
            Trade(
                ticker=ticker,
                entry_date=pos.entry_date,
                entry_price=pos.entry_price,
                exit_date=final_day,
                exit_price=fill_price,
                quantity=pos.quantity,
                pnl_usd=pnl_usd,
                pnl_pct=pnl_pct,
                exit_reason="END_OF_BACKTEST",
            )
        )
    open_positions.clear()

    ending_equity = cash
    total_return_pct = (
        (ending_equity - params.starting_cash) / params.starting_cash * 100
        if params.starting_cash != 0
        else Decimal(0)
    )
    win_rate_pct, avg_win_pct, avg_loss_pct = _trade_metrics(trades)

    return BacktestSimulationResult(
        equity_curve=equity_curve,
        trades=trades,
        ending_equity=ending_equity,
        total_return_pct=total_return_pct,
        max_drawdown_pct=_max_drawdown_pct(equity_curve),
        win_rate_pct=win_rate_pct,
        num_trades=len(trades),
        avg_win_pct=avg_win_pct,
        avg_loss_pct=avg_loss_pct,
    )


def _load_symbol_series(
    session: Session, symbol: Symbol, start: date, end: date
) -> SymbolSeries | None:
    bars = get_latest_price_bars(session, symbol.id, start, end)
    if not bars:
        return None
    indicators = get_indicator_series_for_symbol(session, symbol.id, start, end)
    return SymbolSeries(
        ticker=symbol.ticker,
        symbol_id=symbol.id,
        bars=[SymbolBar(as_of=b.as_of, open=b.open, close=b.close) for b in bars],
        indicators_by_date=indicators,
    )


def _benchmark_return_pct(
    session: Session,
    symbol_series: dict[str, SymbolSeries],
    ticker: str,
    start: date,
    end: date,
) -> Decimal | None:
    """Always attempted, never a hard requirement (ADR — benchmark is a
    nullable bonus in the report, not a togglable feature): `None` if the
    ticker isn't tracked at all or has no bars in range."""
    series = symbol_series.get(ticker.upper())
    if series is None:
        symbol = session.execute(
            select(Symbol).where(Symbol.ticker == ticker.upper())
        ).scalar_one_or_none()
        if symbol is None:
            return None
        loaded = _load_symbol_series(session, symbol, start, end)
        if loaded is None:
            return None
        series = loaded
    if not series.bars:
        return None
    return compute_buy_and_hold_return_pct(series.bars[0].close, series.bars[-1].close)


def run_backtest(
    session: Session,
    date_range_start: date,
    date_range_end: date,
    strategy_version_id: int | None = None,
    entry_score_threshold: Decimal = Decimal("65"),
    exit_score_threshold: Decimal = Decimal("40"),
    max_holding_days: int = 10,
    position_size_pct: Decimal = Decimal("0.10"),
    starting_cash: Decimal = Decimal("10000.00"),
    benchmark_ticker: str | None = "SPY",
) -> BacktestRun:
    """DB-facing wrapper: loads real history for **every** known `Symbol`
    (never filtered by `active` — ADR-025's survivorship-bias mitigation),
    runs the pure simulation, and persists a `BacktestRun` + one
    `AuditEvent` (consistent with every other analytical artifact getting
    an audit trail). `strategy_version_id` accepts an explicit id (not just
    "the active one") so Phase 6 can backtest a not-yet-approved candidate
    version without a schema change."""
    if date_range_end < date_range_start:
        raise ValueError("date_range_end must not be before date_range_start.")

    if strategy_version_id is not None:
        strategy = session.get(StrategyVersion, strategy_version_id)
        if strategy is None:
            raise ValueError(f"Unknown strategy_version_id: {strategy_version_id}")
    else:
        strategy = get_or_create_default_strategy_version(session)

    symbols = session.execute(select(Symbol)).scalars().all()
    symbol_series: dict[str, SymbolSeries] = {}
    for symbol in symbols:
        series = _load_symbol_series(session, symbol, date_range_start, date_range_end)
        if series is not None:
            symbol_series[symbol.ticker] = series

    trading_calendar = sorted(
        {bar.as_of for series in symbol_series.values() for bar in series.bars}
    )
    if not trading_calendar:
        raise ValueError("No price history found for any symbol in the requested date range.")

    params = BacktestParams(
        entry_score_threshold=entry_score_threshold,
        exit_score_threshold=exit_score_threshold,
        max_holding_days=max_holding_days,
        position_size_pct=position_size_pct,
        starting_cash=starting_cash,
    )
    sim_result = run_backtest_simulation(trading_calendar, symbol_series, strategy.config, params)

    benchmark_return_pct = (
        _benchmark_return_pct(
            session, symbol_series, benchmark_ticker, date_range_start, date_range_end
        )
        if benchmark_ticker
        else None
    )

    parameters: dict[str, Any] = {
        "entry_score_threshold": str(params.entry_score_threshold),
        "exit_score_threshold": str(params.exit_score_threshold),
        "max_holding_days": params.max_holding_days,
        "position_size_pct": str(params.position_size_pct),
        "starting_cash": str(params.starting_cash),
        "benchmark_ticker": benchmark_ticker,
    }
    results_summary: dict[str, Any] = {
        "ending_equity": str(sim_result.ending_equity),
        "total_return_pct": str(sim_result.total_return_pct),
        "max_drawdown_pct": str(sim_result.max_drawdown_pct),
        "win_rate_pct": str(sim_result.win_rate_pct),
        "num_trades": sim_result.num_trades,
        "avg_win_pct": str(sim_result.avg_win_pct),
        "avg_loss_pct": str(sim_result.avg_loss_pct),
        "benchmark_return_pct": (
            str(benchmark_return_pct) if benchmark_return_pct is not None else None
        ),
        "equity_curve": [
            {"as_of": p.as_of.isoformat(), "equity": str(p.equity)} for p in sim_result.equity_curve
        ],
        "trades": [
            {
                "ticker": t.ticker,
                "entry_date": t.entry_date.isoformat(),
                "entry_price": str(t.entry_price),
                "exit_date": t.exit_date.isoformat(),
                "exit_price": str(t.exit_price),
                "quantity": t.quantity,
                "pnl_usd": str(t.pnl_usd),
                "pnl_pct": str(t.pnl_pct),
                "exit_reason": t.exit_reason,
            }
            for t in sim_result.trades
        ],
    }

    run = BacktestRun(
        strategy_version_id=strategy.id,
        date_range_start=date_range_start,
        date_range_end=date_range_end,
        parameters=parameters,
        results_summary=results_summary,
        created_at=datetime.now(UTC),
    )
    session.add(run)
    session.flush()
    record_audit_event(
        session, record_type="BACKTEST_RUN_CREATED", ref_id=run.id, snapshot=parameters
    )
    session.commit()
    session.refresh(run)
    return run
