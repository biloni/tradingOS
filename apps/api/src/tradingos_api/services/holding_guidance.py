"""Per-lot holding guidance (Revision Prompt 8) — the read model behind
the position-detail screen. A composing view over already-existing data
(Revision Prompt 6's committee output, R3's `RecommendationLevel`/
`InvestmentThesis`, Revision Prompt 4's `EarningsEvent`, `Alert`), not
new business logic — this module answers "what should the position
detail screen show for this lot," it doesn't compute anything a
deterministic engine hasn't already produced.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from tradingos_api.models.enums import AlertStatus, LotLane, RecommendationLevelKind, ThesisStatus
from tradingos_api.models.execution import PositionLot
from tradingos_api.models.investment_thesis import InvestmentThesis, InvestmentThesisVersion
from tradingos_api.models.market_evidence import EarningsEvent
from tradingos_api.models.operations import Alert
from tradingos_api.models.order_authority import OrderProposal
from tradingos_api.models.recommendations import (
    Recommendation,
    RecommendationInvalidationCondition,
    RecommendationLevel,
    RecommendationVersion,
)

CALCULATION_VERSION = "v1"


def _snapshot_str(snapshot: dict[str, object], key: str) -> str | None:
    value = snapshot.get(key)
    return value if isinstance(value, str) else None


def _next_earnings_event(
    db: Session, *, instrument_id: uuid.UUID, as_of: date
) -> EarningsEvent | None:
    return db.scalar(
        select(EarningsEvent)
        .where(EarningsEvent.instrument_id == instrument_id, EarningsEvent.report_date >= as_of)
        .order_by(EarningsEvent.report_date.asc())
    )


def _open_alerts(db: Session, *, instrument_id: uuid.UUID) -> list[Alert]:
    return list(
        db.scalars(
            select(Alert).where(
                Alert.instrument_id == instrument_id, Alert.status == AlertStatus.OPEN
            )
        ).all()
    )


@dataclass(frozen=True)
class InvestmentHoldingGuidance:
    lot_id: uuid.UUID
    current_action: str | None
    thesis_health: ThesisStatus | None
    valuation_context: str | None
    accumulation_zone: str | None
    next_review_date: date | None
    upcoming_earnings_date: date | None
    portfolio_role: str | None
    portfolio_weight_pct: Decimal | None


@dataclass(frozen=True)
class TacticalHoldingGuidance:
    lot_id: uuid.UUID
    current_action: str | None
    setup_and_event_phase: str | None
    entry_price: Decimal | None
    stop_price: Decimal | None
    target_prices: list[Decimal]
    time_exit_review_date: date | None
    invalidation_conditions: list[str]
    upcoming_event_date: date | None
    open_alert_titles: list[str]
    linked_order_proposal_status: str | None


def get_investment_holding_guidance(
    db: Session,
    *,
    lot: PositionLot,
    as_of: date,
    account_equity: Decimal | None = None,
    current_price: Decimal | None = None,
) -> InvestmentHoldingGuidance:
    version: RecommendationVersion | None = None
    if lot.source_recommendation_version_id is not None:
        version = db.get(RecommendationVersion, lot.source_recommendation_version_id)

    thesis: InvestmentThesis | None = None
    thesis_version: InvestmentThesisVersion | None = None
    if version is not None:
        recommendation = db.get(Recommendation, version.recommendation_id)
        if recommendation is not None:
            thesis = db.scalar(
                select(InvestmentThesis).where(
                    InvestmentThesis.recommendation_id == recommendation.id
                )
            )
        if thesis is not None:
            thesis_version = db.scalar(
                select(InvestmentThesisVersion)
                .where(InvestmentThesisVersion.investment_thesis_id == thesis.id)
                .order_by(InvestmentThesisVersion.version_number.desc())
            )

    snapshot: dict[str, object] = version.deterministic_inputs_snapshot if version else {}
    next_earnings = _next_earnings_event(db, instrument_id=lot.instrument_id, as_of=as_of)

    weight_pct = None
    if account_equity is not None and account_equity > 0 and current_price is not None:
        weight_pct = (lot.quantity_remaining * current_price / account_equity) * Decimal(100)

    return InvestmentHoldingGuidance(
        lot_id=lot.id,
        current_action=version.lane_action if version else None,
        thesis_health=thesis.status if thesis else None,
        valuation_context=_snapshot_str(snapshot, "valuation_context"),
        accumulation_zone=_snapshot_str(snapshot, "preferred_accumulation_zone"),
        next_review_date=thesis_version.review_date if thesis_version else None,
        upcoming_earnings_date=next_earnings.report_date if next_earnings else None,
        portfolio_role=_snapshot_str(snapshot, "portfolio_role"),
        portfolio_weight_pct=weight_pct,
    )


def get_tactical_holding_guidance(
    db: Session, *, lot: PositionLot, as_of: date
) -> TacticalHoldingGuidance:
    version: RecommendationVersion | None = None
    if lot.source_recommendation_version_id is not None:
        version = db.get(RecommendationVersion, lot.source_recommendation_version_id)

    snapshot: dict[str, object] = version.deterministic_inputs_snapshot if version else {}

    entry_price = stop_price = None
    target_prices: list[Decimal] = []
    invalidation_conditions: list[str] = []
    order_proposal_status: str | None = None

    if version is not None:
        levels = db.scalars(
            select(RecommendationLevel).where(
                RecommendationLevel.recommendation_version_id == version.id
            )
        ).all()
        for level in levels:
            if level.kind == RecommendationLevelKind.ENTRY:
                entry_price = level.price
            elif level.kind == RecommendationLevelKind.STOP:
                stop_price = level.price
            elif level.kind == RecommendationLevelKind.TARGET:
                target_prices.append(level.price)

        conditions = db.scalars(
            select(RecommendationInvalidationCondition).where(
                RecommendationInvalidationCondition.recommendation_version_id == version.id
            )
        ).all()
        invalidation_conditions = [c.condition_text for c in conditions]

        proposal = db.scalar(
            select(OrderProposal).where(OrderProposal.recommendation_version_id == version.id)
        )
        if proposal is not None:
            order_proposal_status = proposal.status.value

    next_earnings = _next_earnings_event(db, instrument_id=lot.instrument_id, as_of=as_of)
    open_alerts = _open_alerts(db, instrument_id=lot.instrument_id)

    return TacticalHoldingGuidance(
        lot_id=lot.id,
        current_action=version.lane_action if version else None,
        setup_and_event_phase=_snapshot_str(snapshot, "setup_and_event_phase"),
        entry_price=entry_price,
        stop_price=stop_price,
        target_prices=target_prices,
        time_exit_review_date=version.review_date if version else None,
        invalidation_conditions=invalidation_conditions,
        upcoming_event_date=next_earnings.report_date if next_earnings else None,
        open_alert_titles=[a.title for a in open_alerts],
        linked_order_proposal_status=order_proposal_status,
    )


def get_holding_guidance_for_lot(
    db: Session,
    *,
    lot: PositionLot,
    as_of: date,
    account_equity: Decimal | None = None,
    current_price: Decimal | None = None,
) -> InvestmentHoldingGuidance | TacticalHoldingGuidance | None:
    if lot.lane == LotLane.INVESTMENT:
        return get_investment_holding_guidance(
            db, lot=lot, as_of=as_of, account_equity=account_equity, current_price=current_price
        )
    if lot.lane == LotLane.TACTICAL:
        return get_tactical_holding_guidance(db, lot=lot, as_of=as_of)
    return None
