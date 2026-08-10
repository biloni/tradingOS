"""Calibration (Revision Prompt 14). Distinguishes three axes this
project's docs have long insisted must never collapse into one number
(docs/MODEL_GOVERNANCE.md's DQ-4, "confidence and magnitude are
different numbers"): `RecommendationVersion.score` (a deterministic
0-8 *ranking* score — Revision Prompt 5's tactical direction score,
never an LLM self-rating), `RecommendationVersion.confidence` (a
qualitative LOW/MEDIUM/HIGH *direction-confidence* band, also
deterministic — `_compute_confidence()`), and `selected_expected_move_pct`
(the *magnitude* estimate, Revision Prompt 5's `compute_expected_move()`).
This module reports calibration against each axis separately — never a
blended "confidence-and-magnitude" figure.

**Sparse-bin protection is structural, not a display convention.**
`_bin_from_outcomes()` always reports `sample_size`/`is_adequate`
honestly; every derived statistic (hit rate, confidence interval, Brier
score) is `None` below `MIN_SAMPLE_SIZE_FOR_CALIBRATION` — the same
"never fabricate a rate from an inadequate sample" guardrail
`services/performance_coach.py` already established for the AI coach,
applied here to every segmentation bin rather than to one LLM-call
decision.

**Actual and hypothetical outcomes are tracked separately, never
blended**, matching Revision Prompt 12's own "clear separation of
actual, paper, and hypothetical performance" — a `ClosedOutcome.pnl_source`
field says which one produced each row, and every caller decides
whether to compute calibration against the (usually much smaller) real-
trade sample alone or against the wider include-hypothetical sample,
never silently pooled without saying so.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from tradingos_api.models.execution import Trade
from tradingos_api.models.learning import HypotheticalTradeOutcome, RecommendationOutcome
from tradingos_api.models.market_evidence import (
    EarningsEvent,
    EventExpectedMoveSnapshot,
    MarketRegimeSnapshot,
)
from tradingos_api.models.monitoring import PostEarningsWorkflowRun
from tradingos_api.models.recommendations import (
    Recommendation,
    RecommendationAttribution,
    RecommendationVersion,
)
from tradingos_api.models.security_master import Industry, Instrument, Sector
from tradingos_api.services.performance_metrics import brier_score, wilson_confidence_interval

CALCULATION_VERSION = "v1"

MIN_SAMPLE_SIZE_FOR_CALIBRATION = 20
"""Documented placeholder threshold (no statistically-derived minimum
exists for this project's own recommendation population, the same
honest caveat `services/performance_coach.py::MIN_SAMPLE_SIZE_FOR_SUMMARY`
already carries) — chosen as "enough closed outcomes that a handful of
lucky/unlucky trades can't dominate an observed hit rate.\""""

MAX_TACTICAL_SCORE = Decimal(8)

_HOLDING_PERIOD_BANDS: list[tuple[str, int, int]] = [
    ("0-2D", 0, 2),
    ("3-5D", 3, 5),
    ("6-10D", 6, 10),
    ("11D+", 11, 10_000),
]
_SCORE_BANDS: list[tuple[str, Decimal, Decimal]] = [
    ("0-3", Decimal(0), Decimal(3)),
    ("4-5", Decimal(4), Decimal(5)),
    ("6-7", Decimal(6), Decimal(7)),
    ("8", Decimal(8), Decimal(8)),
]


def score_to_predicted_probability(score: Decimal | None) -> Decimal | None:
    """The one documented, versioned mapping from the deterministic
    ranking score to a `[0, 1]` forecast for Brier-scoring purposes —
    `score / 8`. Never an LLM's self-reported confidence (which this
    project's own governance policy forbids treating as a probability at
    all) — a plain linear rescaling of an already-deterministic, already-
    versioned score."""
    if score is None:
        return None
    return score / MAX_TACTICAL_SCORE


@dataclass(frozen=True)
class ClosedOutcome:
    recommendation_id: uuid.UUID
    recommendation_version_id: uuid.UUID
    mode: str
    score: Decimal | None
    confidence: str
    expected_move_pct: Decimal | None
    is_win: bool
    pnl_source: str
    """`"ACTUAL"` (a real, closed `Trade` via `RecommendationOutcome`) or
    `"HYPOTHETICAL"` (Revision Prompt 12's simulated fill for an ignored
    recommendation) — never blended without the caller choosing to."""
    sector: str | None
    regime: str | None
    event_timing_category: str | None
    holding_period_days: int | None


@dataclass(frozen=True)
class CalibrationBin:
    label: str
    sample_size: int
    is_adequate: bool
    observed_hit_rate_pct: Decimal | None
    ci_low_pct: Decimal | None
    ci_high_pct: Decimal | None
    brier_score: Decimal | None
    calculation_version: str = CALCULATION_VERSION


def _bin_from_outcomes(label: str, outcomes: list[ClosedOutcome]) -> CalibrationBin:
    n = len(outcomes)
    if n < MIN_SAMPLE_SIZE_FOR_CALIBRATION:
        return CalibrationBin(label, n, False, None, None, None, None)
    wins = sum(1 for o in outcomes if o.is_win)
    hit_rate = (Decimal(wins) / Decimal(n)) * Decimal(100)
    ci = wilson_confidence_interval(wins, n)
    ci_low = ci[0] * Decimal(100) if ci else None
    ci_high = ci[1] * Decimal(100) if ci else None
    predicted = [score_to_predicted_probability(o.score) for o in outcomes]
    brier = None
    if all(p is not None for p in predicted):
        clean_predicted: list[Decimal] = [p for p in predicted if p is not None]
        brier = brier_score(clean_predicted, [o.is_win for o in outcomes])
    return CalibrationBin(label, n, True, hit_rate, ci_low, ci_high, brier)


def _group_by(
    outcomes: list[ClosedOutcome], key_fn: Callable[[ClosedOutcome], str | None]
) -> list[CalibrationBin]:
    buckets: dict[str, list[ClosedOutcome]] = {}
    for outcome in outcomes:
        key = key_fn(outcome)
        if key is None:
            continue
        buckets.setdefault(key, []).append(outcome)
    return [_bin_from_outcomes(label, group) for label, group in sorted(buckets.items())]


def reliability_by_confidence_band(outcomes: list[ClosedOutcome]) -> list[CalibrationBin]:
    return _group_by(outcomes, lambda o: o.confidence)


def _score_band(score: Decimal | None) -> str | None:
    if score is None:
        return None
    for label, low, high in _SCORE_BANDS:
        if low <= score <= high:
            return label
    return None


def reliability_by_score_band(outcomes: list[ClosedOutcome]) -> list[CalibrationBin]:
    return _group_by(outcomes, lambda o: _score_band(o.score))


def calibration_by_strategy(outcomes: list[ClosedOutcome]) -> list[CalibrationBin]:
    return _group_by(outcomes, lambda o: o.mode)


def calibration_by_sector(outcomes: list[ClosedOutcome]) -> list[CalibrationBin]:
    return _group_by(outcomes, lambda o: o.sector)


def calibration_by_regime(outcomes: list[ClosedOutcome]) -> list[CalibrationBin]:
    return _group_by(outcomes, lambda o: o.regime)


def calibration_by_event_timing(outcomes: list[ClosedOutcome]) -> list[CalibrationBin]:
    return _group_by(outcomes, lambda o: o.event_timing_category)


def _holding_period_band(days: int | None) -> str | None:
    if days is None:
        return None
    for label, low, high in _HOLDING_PERIOD_BANDS:
        if low <= days <= high:
            return label
    return None


def calibration_by_holding_period(outcomes: list[ClosedOutcome]) -> list[CalibrationBin]:
    return _group_by(outcomes, lambda o: _holding_period_band(o.holding_period_days))


def _sector_by_instrument(
    db: Session, instrument_ids: list[uuid.UUID]
) -> dict[uuid.UUID, str | None]:
    if not instrument_ids:
        return {}
    rows = db.execute(
        select(Instrument.id, Sector.name)
        .join(Industry, Instrument.industry_id == Industry.id, isouter=True)
        .join(Sector, Industry.sector_id == Sector.id, isouter=True)
        .where(Instrument.id.in_(instrument_ids))
    ).all()
    return {instrument_id: sector_name for instrument_id, sector_name in rows}


def _regime_as_of(db: Session, as_of_dates: list[date]) -> dict[date, str]:
    """The most recent `MarketRegimeSnapshot` at or before each date, one
    query for the whole batch rather than one per outcome."""
    if not as_of_dates:
        return {}
    rows = db.scalars(
        select(MarketRegimeSnapshot).order_by(MarketRegimeSnapshot.as_of.asc())
    ).all()
    if not rows:
        return {}
    result: dict[date, str] = {}
    for target in as_of_dates:
        candidates = [r for r in rows if r.as_of <= target]
        if candidates:
            result[target] = candidates[-1].classification.value
    return result


@dataclass(frozen=True)
class _EarningsContext:
    timing_category: str
    expected_move_pct: Decimal | None


def _earnings_context_by_recommendation(
    db: Session, recommendation_ids: list[uuid.UUID]
) -> dict[uuid.UUID, _EarningsContext]:
    """Joins through `PostEarningsWorkflowRun` — the one place a
    `Recommendation` row (pre- or post-event leg) links back to the
    `EarningsEvent` that produced it. A recommendation reachable this way
    also gets its magnitude estimate (`selected_expected_move_pct`, most
    recent snapshot for that event) alongside the timing category, in the
    same batched query rather than a second round-trip. A recommendation
    with no matching workflow run (e.g. Investment-lane, or a Tactical
    call that never reached post-earnings confirmation) simply has no
    entry — honestly absent, never guessed."""
    if not recommendation_ids:
        return {}
    rows = db.execute(
        select(
            PostEarningsWorkflowRun.pre_event_recommendation_id,
            PostEarningsWorkflowRun.post_event_recommendation_id,
            EarningsEvent.timing_category,
            EarningsEvent.id,
        ).join(EarningsEvent, PostEarningsWorkflowRun.earnings_event_id == EarningsEvent.id)
    ).all()
    event_ids = list({event_id for _, _, _, event_id in rows})
    latest_move_by_event: dict[uuid.UUID, Decimal] = {}
    for snapshot in db.scalars(
        select(EventExpectedMoveSnapshot)
        .where(EventExpectedMoveSnapshot.earnings_event_id.in_(event_ids))
        .order_by(EventExpectedMoveSnapshot.as_of.asc())
    ).all():
        latest_move_by_event[snapshot.earnings_event_id] = snapshot.selected_expected_move_pct

    result: dict[uuid.UUID, _EarningsContext] = {}
    wanted = set(recommendation_ids)
    for pre_id, post_id, timing, event_id in rows:
        context = _EarningsContext(timing.value, latest_move_by_event.get(event_id))
        if pre_id in wanted:
            result[pre_id] = context
        if post_id in wanted:
            result[post_id] = context
    return result


def _holding_period_by_recommendation_version(
    db: Session, recommendation_version_ids: list[uuid.UUID]
) -> dict[uuid.UUID, int | None]:
    if not recommendation_version_ids:
        return {}
    rows = db.execute(
        select(
            RecommendationAttribution.recommendation_version_id, Trade.opened_at, Trade.closed_at
        )
        .join(Trade, RecommendationAttribution.trade_id == Trade.id)
        .where(RecommendationAttribution.recommendation_version_id.in_(recommendation_version_ids))
    ).all()
    result: dict[uuid.UUID, int | None] = {}
    for version_id, opened_at, closed_at in rows:
        if opened_at is not None and closed_at is not None:
            result[version_id] = (closed_at - opened_at).days
    return result


def get_closed_outcomes(db: Session, *, since: date | None = None) -> list[ClosedOutcome]:
    """Every recommendation with a *determined* outcome — real (via
    `RecommendationOutcome.realized_pnl`) or hypothetical (via
    `HypotheticalTradeOutcome.simulated_pnl_pct`) — using each
    recommendation's latest version. A recommendation with neither (still
    `PENDING`, Revision Prompt 12's own vocabulary) contributes nothing:
    calibration only makes sense against a *known* result, never a guess
    at what an open call will do."""
    latest_versions_subquery = (
        select(
            RecommendationVersion.recommendation_id,
            RecommendationVersion.id.label("version_id"),
        )
        .distinct(RecommendationVersion.recommendation_id)
        .order_by(
            RecommendationVersion.recommendation_id, RecommendationVersion.version_number.desc()
        )
        .subquery()
    )

    query = (
        select(Recommendation, RecommendationVersion)
        .join(
            latest_versions_subquery,
            Recommendation.id == latest_versions_subquery.c.recommendation_id,
        )
        .join(
            RecommendationVersion, RecommendationVersion.id == latest_versions_subquery.c.version_id
        )
    )
    if since is not None:
        query = query.where(RecommendationVersion.generated_at >= since)
    rows = db.execute(query).all()
    if not rows:
        return []

    recommendation_ids = [r.id for r, _ in rows]
    version_ids = [v.id for _, v in rows]
    instrument_ids = list({r.instrument_id for r, _ in rows})

    outcomes_by_rec = {
        o.recommendation_id: o
        for o in db.scalars(
            select(RecommendationOutcome).where(
                RecommendationOutcome.recommendation_id.in_(recommendation_ids)
            )
        ).all()
    }
    hypotheticals_by_rec: dict[uuid.UUID, HypotheticalTradeOutcome] = {}
    for h in db.scalars(
        select(HypotheticalTradeOutcome)
        .where(HypotheticalTradeOutcome.recommendation_id.in_(recommendation_ids))
        .order_by(HypotheticalTradeOutcome.computed_at.desc())
    ).all():
        hypotheticals_by_rec.setdefault(h.recommendation_id, h)

    sector_by_instrument = _sector_by_instrument(db, instrument_ids)
    regime_by_date = _regime_as_of(db, [v.generated_at.date() for _, v in rows])
    earnings_context_by_rec = _earnings_context_by_recommendation(db, recommendation_ids)
    holding_period_by_version = _holding_period_by_recommendation_version(db, version_ids)

    results: list[ClosedOutcome] = []
    for recommendation, version in rows:
        outcome = outcomes_by_rec.get(recommendation.id)
        is_win: bool | None = None
        pnl_source: str | None = None
        if outcome is not None and outcome.realized_pnl is not None:
            is_win = outcome.realized_pnl > 0
            pnl_source = "ACTUAL"
        else:
            hypothetical = hypotheticals_by_rec.get(recommendation.id)
            if hypothetical is not None and hypothetical.simulated_pnl_pct is not None:
                is_win = hypothetical.simulated_pnl_pct > 0
                pnl_source = "HYPOTHETICAL"
        if is_win is None or pnl_source is None:
            continue

        earnings_context = earnings_context_by_rec.get(recommendation.id)
        results.append(
            ClosedOutcome(
                recommendation_id=recommendation.id,
                recommendation_version_id=version.id,
                mode=recommendation.mode.value,
                score=version.score,
                confidence=version.confidence.value,
                expected_move_pct=earnings_context.expected_move_pct if earnings_context else None,
                is_win=is_win,
                pnl_source=pnl_source,
                sector=sector_by_instrument.get(recommendation.instrument_id),
                regime=regime_by_date.get(version.generated_at.date()),
                event_timing_category=(
                    earnings_context.timing_category if earnings_context else None
                ),
                holding_period_days=holding_period_by_version.get(version.id),
            )
        )
    return results
