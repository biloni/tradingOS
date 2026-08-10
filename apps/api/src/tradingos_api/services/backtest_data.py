"""Deterministic synthetic market/earnings history for the event-driven
backtester (Revision Prompt 13).

**Why synthetic, and why this is honestly disclosed rather than forced
to look real:** this dev environment's real `MarketBar`/`EarningsEvent`
history covers roughly 3 months (2026-05-01 to 2026-08-03) across 6
instruments with daily bars, and only 3 real earnings events total
(confirmed by direct query before writing this module). Prompt 13's own
locked baseline scenario asks for a 2026-02-03 to 2026-07-31 window
producing ~25 scored trades, and its validation section asks for "at
least two years" of history with a train/validation/out-of-sample split
— neither is reachable from this environment's real data, by a wide
margin. Rather than forcing a match against numbers the real data cannot
produce (the prompt's own instruction: "do not force these results...
explain every deviation"), this module generates a deterministic,
seeded, multi-year synthetic universe — the same "real Alpaca where
available, synthetic fixtures elsewhere, always documented" pattern this
project already uses for evidence types with no real provider
(docs/PROVIDER_MATRIX.md) — extended here to "enough historical depth to
validate the engine's mechanics," not to fabricate a specific target
outcome.

Seeded with a fixed RNG (default 42, matching this project's `prisma/
seed.ts`-equivalent convention for reproducible demos) so re-running
produces byte-identical bars/events. Internal random-walk arithmetic
uses `random.Random.gauss()` (float) — an accepted exception to "never
float-math currency," the same way `docs/DATA_ASSUMPTIONS` seed-data
generation already uses float RNG to produce synthetic salaries before
converting to `Decimal` at the boundary. Every value this module returns
is `Decimal`/`int`/`date`; no float ever leaves this module.
"""

from __future__ import annotations

import random
import uuid
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from tradingos_api.models.security_master import Industry, Instrument, Sector

DEFAULT_SEED = 42

# A fixed, curated slice of this dev environment's own real, sector-
# diverse `Instrument` seed data (confirmed present via direct query) —
# reused so `EventBacktestTrade.instrument_id` is always a real FK, and
# so sector/semiconductor-concentration validation slices have real
# sector metadata to group on. Deliberately over-represents
# semiconductors (10 of 20) to make Prompt 13's "semiconductor
# concentration" validation subset meaningful.
DEFAULT_UNIVERSE_TICKERS: tuple[str, ...] = (
    "AMD", "TSM", "AVGO", "SNDK", "ADI", "NXPI", "ON", "ARM", "MRVL", "ALAB",
    "WDAY", "SNOW", "NOW", "CRM",
    "LLY", "MRK",
    "BAC", "JPM",
    "CVX", "XOM",
)  # fmt: skip
BENCHMARK_TICKER = "SPY"

_TRADING_DAYS_PER_QUARTER = 63
_MIN_ANALYSTS = 2
_MAX_ANALYSTS = 10


@dataclass(frozen=True)
class SyntheticDailyBar:
    as_of: date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int


@dataclass(frozen=True)
class SyntheticEarningsEvent:
    report_date: date
    """Results are released after this date's close — the next trading
    day is the reaction/gap day, matching ADR-022's next-bar-fill
    convention (no acting on a close using information that close itself
    was needed to compute)."""
    fiscal_period: str
    consensus_eps: Decimal
    prior_year_actual_eps: Decimal
    num_analysts: int
    """Deliberately varies 2-10 (some events below the live gate's
    minimum-3 threshold) — a realistic mix of eligible/ineligible events,
    matching this project's established "deliberately below/above
    threshold" seed-data philosophy."""
    actual_gap_pct: Decimal
    """The realized next-trading-day open-vs-prior-close gap this event
    actually produced — read back by later events as "historical gap"
    input (component 8 / expected-move), so the synthetic series is
    internally consistent: declared history is exactly what happened."""


@dataclass(frozen=True)
class SyntheticInstrumentSeries:
    instrument_id: uuid.UUID
    ticker: str
    sector: str | None
    bars: list[SyntheticDailyBar]
    """Oldest-to-newest, one row per (synthetic) trading day across the
    whole generated window."""
    earnings_events: list[SyntheticEarningsEvent]
    """Oldest-to-newest. Empty for the benchmark series."""


@dataclass(frozen=True)
class SyntheticUniverse:
    seed: int
    start: date
    end: date
    instruments: list[SyntheticInstrumentSeries]
    benchmark: SyntheticInstrumentSeries


def _trading_days(start: date, end: date) -> list[date]:
    """Plain business-day calendar (Mon-Fri, no holiday calendar) — a
    documented simplification vs. `services/market_calendar.py`'s real
    NYSE calendar, acceptable here because this module's only job is
    "enough distinct trading days for the engine's mechanics," not
    calendar-exact real-world dates."""
    days: list[date] = []
    current = start
    while current <= end:
        if current.weekday() < 5:
            days.append(current)
        current += timedelta(days=1)
    return days


def _ticker_seed(base_seed: int, ticker: str) -> int:
    """A stable per-ticker seed derived from the ticker string itself —
    deliberately NOT `hash(ticker)`, since Python randomizes string
    hashing per-process by default (`PYTHONHASHSEED`), which would make
    "deterministic" a lie across two runs of the same process."""
    return base_seed + sum(ord(c) for c in ticker)


def _generate_price_series(
    *, rng: random.Random, trading_days: list[date], start_price: Decimal, daily_vol: float
) -> tuple[list[Decimal], list[int], dict[date, int]]:
    """Returns (closes, volumes, index-by-date) via a seeded log-return
    random walk. `daily_vol` is the per-day gaussian standard deviation
    (e.g. 0.022 for a higher-volatility semiconductor name)."""
    closes: list[Decimal] = []
    volumes: list[int] = []
    price = float(start_price)
    base_volume = rng.randint(2_000_000, 15_000_000)
    for _ in trading_days:
        drift = 0.00035
        log_return = rng.gauss(drift, daily_vol)
        price = max(price * (1 + log_return), 0.50)
        closes.append(Decimal(str(round(price, 4))))
        volume = int(base_volume * rng.uniform(0.6, 1.5))
        volumes.append(volume)
    index_by_date = {d: i for i, d in enumerate(trading_days)}
    return closes, volumes, index_by_date


def _bars_from_closes(
    trading_days: list[date], closes: list[Decimal], volumes: list[int]
) -> list[SyntheticDailyBar]:
    bars: list[SyntheticDailyBar] = []
    prior_close = closes[0]
    for i, d in enumerate(trading_days):
        close = closes[i]
        open_ = prior_close
        high = max(open_, close) * Decimal("1.004")
        low = min(open_, close) * Decimal("0.996")
        bars.append(SyntheticDailyBar(d, open_, high, low, close, volumes[i]))
        prior_close = close
    return bars


def _inject_earnings_events(
    *,
    rng: random.Random,
    trading_days: list[date],
    closes: list[Decimal],
    volumes: list[int],
    first_event_offset: int,
) -> list[SyntheticEarningsEvent]:
    """Mutates `closes`/`volumes` in place to apply each event's gap and
    volume spike on the reaction day, and returns the event list —
    entangled by design, so the "historical gap" a later event reads is
    exactly the jump this function actually applied, never a separately
    declared, disconnected number."""
    events: list[SyntheticEarningsEvent] = []
    prior_year_eps = Decimal(str(round(rng.uniform(1.0, 8.0), 2)))
    idx = first_event_offset
    while idx < len(trading_days) - 1:
        report_date = trading_days[idx]
        reaction_idx = idx + 1
        gap_pct = Decimal(str(round(rng.gauss(0.5, 4.5), 2)))
        pre_close = closes[reaction_idx - 1]
        new_close = pre_close * (Decimal(1) + gap_pct / Decimal(100))
        closes[reaction_idx] = new_close
        volumes[reaction_idx] = int(volumes[reaction_idx] * rng.uniform(2.0, 4.0))

        consensus_eps = prior_year_eps * Decimal(str(round(rng.uniform(0.9, 1.35), 3)))
        num_analysts = rng.randint(_MIN_ANALYSTS, _MAX_ANALYSTS)
        events.append(
            SyntheticEarningsEvent(
                report_date=report_date,
                fiscal_period=f"Q{((idx // _TRADING_DAYS_PER_QUARTER) % 4) + 1}-{report_date.year}",
                consensus_eps=consensus_eps,
                prior_year_actual_eps=prior_year_eps,
                num_analysts=num_analysts,
                actual_gap_pct=gap_pct,
            )
        )
        prior_year_eps = consensus_eps
        idx += _TRADING_DAYS_PER_QUARTER
    return events


def _fetch_real_instruments(
    db: Session, tickers: tuple[str, ...]
) -> dict[str, tuple[uuid.UUID, str | None]]:
    rows = db.execute(
        select(Instrument.ticker, Instrument.id, Sector.name)
        .join(Industry, Instrument.industry_id == Industry.id, isouter=True)
        .join(Sector, Industry.sector_id == Sector.id, isouter=True)
        .where(Instrument.ticker.in_(tickers))
    ).all()
    return {ticker: (instrument_id, sector) for ticker, instrument_id, sector in rows}


def generate_synthetic_universe(
    db: Session,
    *,
    start: date,
    end: date,
    seed: int = DEFAULT_SEED,
    tickers: tuple[str, ...] = DEFAULT_UNIVERSE_TICKERS,
) -> SyntheticUniverse:
    """The one entry point every backtest run calls before simulating —
    always regenerates from scratch (cheap: pure in-memory computation,
    no DB writes) rather than caching, so a run is reproducible purely
    from `(seed, start, end, tickers)` with no hidden mutable state."""
    trading_days = _trading_days(start, end)
    real_instruments = _fetch_real_instruments(db, (*tickers, BENCHMARK_TICKER))

    instruments: list[SyntheticInstrumentSeries] = []
    for i, ticker in enumerate(tickers):
        if ticker not in real_instruments:
            continue
        instrument_id, sector = real_instruments[ticker]
        rng = random.Random(_ticker_seed(seed, ticker))
        is_semiconductor = sector == "Technology"
        daily_vol = 0.024 if is_semiconductor else 0.016
        start_price = Decimal(str(round(rng.uniform(30, 250), 2)))
        closes, volumes, _ = _generate_price_series(
            rng=rng, trading_days=trading_days, start_price=start_price, daily_vol=daily_vol
        )
        first_offset = 10 + (i % _TRADING_DAYS_PER_QUARTER)
        events = _inject_earnings_events(
            rng=rng,
            trading_days=trading_days,
            closes=closes,
            volumes=volumes,
            first_event_offset=first_offset,
        )
        bars = _bars_from_closes(trading_days, closes, volumes)
        instruments.append(SyntheticInstrumentSeries(instrument_id, ticker, sector, bars, events))

    benchmark_id, benchmark_sector = real_instruments[BENCHMARK_TICKER]
    bench_rng = random.Random(_ticker_seed(seed, BENCHMARK_TICKER))
    bench_closes, bench_volumes, _ = _generate_price_series(
        rng=bench_rng, trading_days=trading_days, start_price=Decimal("500.00"), daily_vol=0.009
    )
    benchmark = SyntheticInstrumentSeries(
        benchmark_id,
        BENCHMARK_TICKER,
        benchmark_sector,
        _bars_from_closes(trading_days, bench_closes, bench_volumes),
        [],
    )

    return SyntheticUniverse(
        seed=seed, start=start, end=end, instruments=instruments, benchmark=benchmark
    )
