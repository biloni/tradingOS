"""Recommendation-versus-reality tracking (Revision Prompt 12) — every
issued recommendation, whatever the user did about it (or didn't), with
its real or simulated outcome. `RecommendationOutcome`/
`HypotheticalTradeOutcome` (both schema fixtures since Revision Prompt
R3/ADR-041, previously unpopulated except by the seed script — confirmed
by grep before writing this module) are what this module actually
computes into.

Three explicitly separate outcome kinds, never blended into one number
(Prompt 12's own "clear separation of actual, paper, and hypothetical
performance"):
  - **actual** — a `FOLLOWED` recommendation's real, closed `Trade.realized_pnl`.
  - **paper** — an open position's current unrealized P&L (still real,
    still paper-account money, just not closed yet).
  - **hypothetical** — what `compute_hypothetical_outcome()` below
    estimates would have happened to an `IGNORED`/`EXPIRED`/`VETOED`
    recommendation had its entry/stop/target actually been taken,
    walked forward day-by-day over real `MarketBar` history using the
    same next-bar, no-look-ahead discipline the retired backtest
    engine established (ADR-022) — a *simulation*, and every returned
    field is labeled as such, never presented as a real fill.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from tradingos_api.models.enums import RecommendationLevelKind, RecommendationStatus, Timeframe
from tradingos_api.models.learning import HypotheticalTradeOutcome, RecommendationOutcome
from tradingos_api.models.market_evidence import MarketBar
from tradingos_api.models.recommendations import (
    Recommendation,
    RecommendationLevel,
    RecommendationVersion,
)

CALCULATION_VERSION = "v1"
DEFAULT_MAX_HOLDING_DAYS = 10
"""Matches the product's own stated 2-10 day tactical swing horizon
(docs/PRODUCT_REQUIREMENTS.md) — the same default the retired backtest
engine used (ADR-023) for the identical reason: a concrete bound is
needed to know when a still-open hypothetical position is force-closed,
and this project's one stated holding-period convention is it."""


@dataclass(frozen=True)
class HypotheticalOutcomeResult:
    entry_reachable: bool
    simulated_entry_price: Decimal | None
    simulated_entry_date: date | None
    simulated_exit_price: Decimal | None
    simulated_exit_date: date | None
    simulated_exit_reason: str | None
    simulated_pnl_pct: Decimal | None


def compute_hypothetical_outcome(
    *,
    entry_price: Decimal,
    stop_price: Decimal | None,
    target_prices: list[Decimal],
    opened_at: date,
    bars: list[tuple[date, Decimal, Decimal, Decimal]],
    max_holding_days: int = DEFAULT_MAX_HOLDING_DAYS,
    entry_window_days: int = 3,
) -> HypotheticalOutcomeResult:
    """`bars` must be `(date, low, high, close)` tuples for the
    instrument, already sorted ascending and starting at/after
    `opened_at` — the caller's responsibility to fetch (this function is
    a pure simulation over whatever history it's handed, exactly like
    `services/post_earnings_confirmation.py`'s own caller-gathers-inputs
    boundary).

    Long-only, matching this project's one modeled trade direction
    (`services/position_monitor.py`'s own documented scope note applies
    here identically). "Entry reachable" requires the low to trade
    *at or below* the entry price within `entry_window_days` trading
    days of the recommendation — a stale, never-actionable entry zone is
    its own explicit, honestly-reported outcome, not silently assumed
    filled at the recommended price."""
    entry_candidates = [b for b in bars if (b[0] - opened_at).days <= entry_window_days]
    entry_bar = next((b for b in entry_candidates if b[1] <= entry_price), None)
    if entry_bar is None:
        return HypotheticalOutcomeResult(
            entry_reachable=False,
            simulated_entry_price=None,
            simulated_entry_date=None,
            simulated_exit_price=None,
            simulated_exit_date=None,
            simulated_exit_reason="ENTRY_NEVER_REACHED",
            simulated_pnl_pct=None,
        )

    entry_date = entry_bar[0]
    remaining_bars = [b for b in bars if b[0] > entry_date]
    deadline = entry_date + timedelta(days=max_holding_days * 2)  # calendar-day slack for weekends

    exit_price: Decimal | None = None
    exit_date: date | None = None
    exit_reason: str | None = None
    trading_days_elapsed = 0

    for bar_date, low, high, close in remaining_bars:
        if bar_date > deadline:
            break
        trading_days_elapsed += 1
        if stop_price is not None and low <= stop_price:
            exit_price, exit_date, exit_reason = stop_price, bar_date, "STOP"
            break
        target_hit = next((t for t in sorted(target_prices) if high >= t), None)
        if target_hit is not None:
            exit_price, exit_date, exit_reason = target_hit, bar_date, "TARGET"
            break
        if trading_days_elapsed >= max_holding_days:
            exit_price, exit_date, exit_reason = close, bar_date, "TIME_EXIT"
            break

    if exit_price is None and remaining_bars:
        # Ran out of history before hitting stop/target/time-exit —
        # mark-to-last-known-close, not silently dropped.
        last = remaining_bars[-1]
        exit_price, exit_date, exit_reason = last[3], last[0], "END_OF_HISTORY"

    pnl_pct = None
    if exit_price is not None:
        pnl_pct = (exit_price - entry_price) / entry_price * Decimal(100)
        # Note: P&L is measured off the *recommended* entry_price (what
        # the recommendation actually proposed), not the bar's low that
        # merely proved the zone was touched — a limit order fills at
        # its limit price, not at whatever the intrabar low happened to be.

    return HypotheticalOutcomeResult(
        entry_reachable=True,
        simulated_entry_price=entry_price,
        simulated_entry_date=entry_date,
        simulated_exit_price=exit_price,
        simulated_exit_date=exit_date,
        simulated_exit_reason=exit_reason,
        simulated_pnl_pct=pnl_pct,
    )


def _bars_for_instrument(
    db: Session, *, instrument_id: uuid.UUID, since: date
) -> list[tuple[date, Decimal, Decimal, Decimal]]:
    rows = db.execute(
        select(MarketBar.as_of, MarketBar.low, MarketBar.high, MarketBar.close)
        .where(
            MarketBar.instrument_id == instrument_id,
            MarketBar.timeframe == Timeframe.DAILY,
            MarketBar.as_of >= since,
        )
        .order_by(MarketBar.as_of.asc())
    ).all()
    return [(r[0], r[1], r[2], r[3]) for r in rows]


def _entry_stop_targets(
    db: Session, *, recommendation_version_id: uuid.UUID
) -> tuple[Decimal | None, Decimal | None, list[Decimal]]:
    levels = db.scalars(
        select(RecommendationLevel).where(
            RecommendationLevel.recommendation_version_id == recommendation_version_id
        )
    ).all()
    entry = next((lvl.price for lvl in levels if lvl.kind == RecommendationLevelKind.ENTRY), None)
    stop = next((lvl.price for lvl in levels if lvl.kind == RecommendationLevelKind.STOP), None)
    targets = [lvl.price for lvl in levels if lvl.kind == RecommendationLevelKind.TARGET]
    return entry, stop, targets


def compute_and_persist_hypothetical_outcome(
    db: Session, *, recommendation: Recommendation, recommendation_version_id: uuid.UUID
) -> HypotheticalTradeOutcome | None:
    """Only meaningful for a recommendation that was never (fully)
    acted on — the caller is responsible for only calling this for
    `IGNORED`/`EXPIRED`/`VETOED` dispositions; a `FOLLOWED` recommendation
    has a *real* `Trade` and belongs in `RecommendationOutcome` instead,
    never both. Idempotent: re-running against the same version appends
    a fresh row (this table has no unique constraint, by design — see
    its own docstring — since a later re-run with more market history
    available is a legitimately different, more complete answer, not a
    duplicate)."""
    entry, stop, targets = _entry_stop_targets(
        db, recommendation_version_id=recommendation_version_id
    )
    if entry is None:
        return None
    opened_at = recommendation.opened_at.date()
    bars = _bars_for_instrument(db, instrument_id=recommendation.instrument_id, since=opened_at)
    result = compute_hypothetical_outcome(
        entry_price=entry, stop_price=stop, target_prices=targets, opened_at=opened_at, bars=bars
    )
    outcome = HypotheticalTradeOutcome(
        recommendation_id=recommendation.id,
        simulated_entry_price=result.simulated_entry_price or entry,
        simulated_exit_price=result.simulated_exit_price,
        simulated_exit_reason=result.simulated_exit_reason,
        simulated_pnl_pct=result.simulated_pnl_pct,
        computed_at=datetime.now(UTC),
    )
    db.add(outcome)
    db.flush()
    return outcome


@dataclass(frozen=True)
class RecommendationRealityRow:
    recommendation_id: uuid.UUID
    mode: str
    status: str
    disposition: str
    """One of `FOLLOWED`/`IGNORED`/`MODIFIED`/`EXPIRED`/`VETOED`/
    `PENDING` (no outcome computed yet)."""
    actual_pnl: Decimal | None
    """Real, closed P&L — only ever set for a `FOLLOWED` disposition."""
    hypothetical_pnl_pct: Decimal | None
    """Simulated P&L percentage — only ever set for `IGNORED`/`EXPIRED`/
    `VETOED`."""
    r_multiple: Decimal | None
    committee_session_id: uuid.UUID | None


def _disposition_for(recommendation: Recommendation, outcome: RecommendationOutcome | None) -> str:
    if outcome is not None:
        return outcome.classification.value
    if recommendation.status == RecommendationStatus.SUPERSEDED:
        return "EXPIRED"
    return "PENDING"


def get_recommendation_reality_rows(
    db: Session, *, account_id: uuid.UUID | None = None
) -> list[RecommendationRealityRow]:
    """Every issued recommendation with whatever reality-tracking data
    exists for it today — `actual_pnl`/`hypothetical_pnl_pct` are `None`
    (not zero) until `compute_and_persist_hypothetical_outcome()`/
    `services/trade_journal.compute_recommendation_outcome()` has
    actually run for that recommendation, matching this module's own
    "never fabricate a value for a disposition that hasn't been computed
    yet" rule."""
    recommendations = db.scalars(select(Recommendation)).all()
    rows: list[RecommendationRealityRow] = []
    for rec in recommendations:
        outcome = db.scalar(
            select(RecommendationOutcome).where(RecommendationOutcome.recommendation_id == rec.id)
        )
        hypothetical = db.scalar(
            select(HypotheticalTradeOutcome)
            .where(HypotheticalTradeOutcome.recommendation_id == rec.id)
            .order_by(HypotheticalTradeOutcome.computed_at.desc())
        )
        latest_version = db.scalar(
            select(RecommendationVersion)
            .where(RecommendationVersion.recommendation_id == rec.id)
            .order_by(RecommendationVersion.version_number.desc())
        )
        rows.append(
            RecommendationRealityRow(
                recommendation_id=rec.id,
                mode=rec.mode.value,
                status=rec.status.value,
                disposition=_disposition_for(rec, outcome),
                actual_pnl=outcome.realized_pnl if outcome else None,
                hypothetical_pnl_pct=hypothetical.simulated_pnl_pct if hypothetical else None,
                r_multiple=outcome.r_multiple if outcome else None,
                committee_session_id=(
                    latest_version.committee_session_id if latest_version else None
                ),
            )
        )
    return rows
