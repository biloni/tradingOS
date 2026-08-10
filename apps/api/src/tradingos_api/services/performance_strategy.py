"""Strategy-level performance breakdowns (Revision Prompt 12) — every
grouping reuses `services/performance_metrics.py::compute_trade_stats()`
on a differently-partitioned slice of the same underlying closed-`Trade`
population, rather than each breakdown re-deriving win-rate/profit-
factor math on its own. `RecommendationAttribution` (Revision Prompt R3)
is the join key between a closed `Trade` and the `RecommendationVersion`
that produced it — the one place "which score/expected-move/lane_action
led to this trade" is answerable at all, since `Trade` itself carries no
strategy metadata beyond `lane`.

Every breakdown here operates on whatever real trade population exists
today — this dev environment's real trade count is small, so most
groupings will report a handful of trades or none at all. That is the
honest result, not a defect: `compute_trade_stats()` already reports
`None` for undefined ratios on a sparse sample rather than fabricating
one, and every result below carries its own `sample_size` so a caller
never mistakes "0 trades, no signal" for "a computed 0%.\""""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from tradingos_api.models.enums import LotLane, TradeStatus
from tradingos_api.models.execution import Trade
from tradingos_api.models.order_authority import (
    OrderPolicyEvaluation,
    OrderProposal,
    OrderProposalVersion,
)
from tradingos_api.models.recommendations import RecommendationAttribution, RecommendationVersion
from tradingos_api.models.security_master import Industry, Instrument, Sector
from tradingos_api.services.performance_metrics import TradeStatsResult, compute_trade_stats

CALCULATION_VERSION = "v1"

_SCORE_BANDS: list[tuple[str, Decimal, Decimal]] = [
    ("0-3", Decimal(0), Decimal(3)),
    ("4-5", Decimal(4), Decimal(5)),
    ("6-7", Decimal(6), Decimal(7)),
    ("8", Decimal(8), Decimal(8)),
]


@dataclass(frozen=True)
class GroupedTradeStats:
    group_key: str
    stats: TradeStatsResult


def _closed_trades(db: Session, *, account_id: uuid.UUID) -> list[Trade]:
    return list(
        db.scalars(
            select(Trade).where(
                Trade.account_id == account_id,
                Trade.status == TradeStatus.CLOSED,
                Trade.realized_pnl.is_not(None),
            )
        ).all()
    )


def _group_by(
    trades: list[Trade], key_fn: Callable[[Trade], str | None]
) -> list[GroupedTradeStats]:
    buckets: dict[str, list[Decimal]] = {}
    for trade in trades:
        key = key_fn(trade)
        if key is None:
            continue
        assert trade.realized_pnl is not None
        buckets.setdefault(key, []).append(trade.realized_pnl)
    return [
        GroupedTradeStats(group_key=key, stats=compute_trade_stats(pnls))
        for key, pnls in sorted(buckets.items())
    ]


def get_lane_contribution(db: Session, *, account_id: uuid.UUID) -> list[GroupedTradeStats]:
    """Investment vs. Tactical contribution — the one breakdown that
    needs no join at all, since `Trade.lane` is a direct column."""
    trades = _closed_trades(db, account_id=account_id)
    return _group_by(trades, lambda t: t.lane.value)


def _attribution_lane_action_by_trade(
    db: Session, *, trade_ids: list[uuid.UUID]
) -> dict[uuid.UUID, str | None]:
    if not trade_ids:
        return {}
    rows = db.execute(
        select(RecommendationAttribution.trade_id, RecommendationVersion.lane_action)
        .join(
            RecommendationVersion,
            RecommendationAttribution.recommendation_version_id == RecommendationVersion.id,
        )
        .where(RecommendationAttribution.trade_id.in_(trade_ids))
    ).all()
    return {trade_id: lane_action for trade_id, lane_action in rows}


def get_pre_event_vs_post_confirmation_contribution(
    db: Session, *, account_id: uuid.UUID
) -> list[GroupedTradeStats]:
    """Splits TACTICAL trades by whether the recommendation that
    produced them was a pre-event entry (`TRADE_ENTER`) or a post-
    confirmation add (`TRADE_ADD_CONFIRMED`) — the two stages of the
    hybrid earnings strategy, tracked as genuinely separate
    contributions per ADR-046/059 rather than blended into one
    "TACTICAL" number."""
    trades = [t for t in _closed_trades(db, account_id=account_id) if t.lane == LotLane.TACTICAL]
    lane_action_by_trade = _attribution_lane_action_by_trade(db, trade_ids=[t.id for t in trades])

    def _key(trade: Trade) -> str | None:
        action = lane_action_by_trade.get(trade.id)
        if action == "TRADE_ENTER":
            return "PRE_EVENT_ENTRY"
        if action == "TRADE_ADD_CONFIRMED":
            return "POST_CONFIRMATION_ADD"
        return "UNATTRIBUTED" if action is None else action

    return _group_by(trades, _key)


def _score_by_trade(db: Session, *, trade_ids: list[uuid.UUID]) -> dict[uuid.UUID, Decimal | None]:
    if not trade_ids:
        return {}
    rows = db.execute(
        select(RecommendationAttribution.trade_id, RecommendationVersion.score)
        .join(
            RecommendationVersion,
            RecommendationAttribution.recommendation_version_id == RecommendationVersion.id,
        )
        .where(RecommendationAttribution.trade_id.in_(trade_ids))
    ).all()
    return {trade_id: score for trade_id, score in rows}


def _score_band(score: Decimal | None) -> str | None:
    if score is None:
        return None
    for label, low, high in _SCORE_BANDS:
        if low <= score <= high:
            return label
    return None


def get_results_by_score_band(db: Session, *, account_id: uuid.UUID) -> list[GroupedTradeStats]:
    trades = _closed_trades(db, account_id=account_id)
    score_by_trade = _score_by_trade(db, trade_ids=[t.id for t in trades])
    return _group_by(trades, lambda t: _score_band(score_by_trade.get(t.id)))


def get_score_threshold_sensitivity(
    db: Session, *, account_id: uuid.UUID, thresholds: list[int]
) -> list[GroupedTradeStats]:
    """Cumulative results for "would only trades scoring at least this
    threshold have been taken" — the VALIDATION requirement to "test
    score thresholds 4 through 7" — distinct from
    `get_results_by_score_band()`'s discrete, non-overlapping bands."""
    trades = _closed_trades(db, account_id=account_id)
    score_by_trade = _score_by_trade(db, trade_ids=[t.id for t in trades])
    results: list[GroupedTradeStats] = []
    for threshold in sorted(thresholds):
        pnls = [
            trade.realized_pnl
            for trade in trades
            if (score := score_by_trade.get(trade.id)) is not None
            and score >= Decimal(threshold)
            and trade.realized_pnl is not None
        ]
        results.append(GroupedTradeStats(f">={threshold}", compute_trade_stats(pnls)))
    return results


def get_results_by_sector(db: Session, *, account_id: uuid.UUID) -> list[GroupedTradeStats]:
    trades = _closed_trades(db, account_id=account_id)
    instrument_ids = list({t.instrument_id for t in trades})
    if not instrument_ids:
        return []
    rows = db.execute(
        select(Instrument.id, Sector.name)
        .join(Industry, Instrument.industry_id == Industry.id, isouter=True)
        .join(Sector, Industry.sector_id == Sector.id, isouter=True)
        .where(Instrument.id.in_(instrument_ids))
    ).all()
    sector_by_instrument = {instrument_id: sector_name for instrument_id, sector_name in rows}
    return _group_by(trades, lambda t: sector_by_instrument.get(t.instrument_id))


@dataclass(frozen=True)
class PolicyVetoOutcomes:
    total_evaluations: int
    authorized: int
    denied: int
    denial_reasons: dict[str, int]


def get_policy_veto_outcomes(db: Session, *, account_id: uuid.UUID) -> PolicyVetoOutcomes:
    """Tallies every recorded `OrderPolicyEvaluation` for proposals on
    this account's orders — "policy veto outcomes" from Prompt 12's own
    requirement list. Counts every requested mode, not only paper
    submissions, since a denied `LIVE_CONFIRM_EACH_ORDER` attempt (fail-
    closed, OA-6) is exactly as much a policy outcome worth reporting as
    a paper denial."""
    rows = db.scalars(
        select(OrderPolicyEvaluation)
        .join(
            OrderProposalVersion,
            OrderPolicyEvaluation.order_proposal_version_id == OrderProposalVersion.id,
        )
        .join(OrderProposal, OrderProposalVersion.order_proposal_id == OrderProposal.id)
        .where(OrderProposal.account_id == account_id)
    ).all()
    denial_reasons: dict[str, int] = {}
    authorized = 0
    for row in rows:
        if row.authorized:
            authorized += 1
        else:
            reason = row.denial_reason or "unspecified"
            denial_reasons[reason] = denial_reasons.get(reason, 0) + 1
    return PolicyVetoOutcomes(
        total_evaluations=len(rows),
        authorized=authorized,
        denied=len(rows) - authorized,
        denial_reasons=denial_reasons,
    )
