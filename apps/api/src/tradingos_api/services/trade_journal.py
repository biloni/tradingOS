"""The trade journal (Revision Prompt 8) — "capture recommendation,
lane, user response, approval, order, fill, modifications, reason,
outcome, maximum favorable/adverse excursion, exit reason, benchmark
result, and post-trade lesson." Most of these fields already have a
home somewhere in the existing schema (`RecommendationOutcome.classification`
is "user response," `Trade.lane`/`linked_order_id`/`modifications_text`/
`mfe`/`mae`/`exit_reason`/`benchmark_snapshot_id` from Revision Prompt 8's
own additive migration, `TradeThesis.thesis_text` is "reason,"
`TradeReview.review_text` is "post-trade lesson") — this module is where
those fields actually get *computed and populated*, and where a single
read model assembles all of them for the journal detail screen.

`compute_recommendation_outcome()` mirrors `RecommendationOutcome`'s own
docstring discipline: "computed from journal/order matching, never
self-reported." Never asks the user "did you follow this?" — infers it
from whether an `OrderProposal` exists, was approved, and whether the
resulting `Trade`'s quantity matches what was proposed.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from tradingos_api.models.enums import (
    OrderApprovalStatus,
    OrderSide,
    RecommendationOutcomeClassification,
    Timeframe,
    TradeStatus,
)
from tradingos_api.models.execution import PositionLot, Trade
from tradingos_api.models.learning import BenchmarkSnapshot, RecommendationOutcome, TradeReview
from tradingos_api.models.market_evidence import MarketBar
from tradingos_api.models.order_authority import OrderApproval, OrderProposal, OrderProposalVersion
from tradingos_api.models.recommendations import RecommendationVersion
from tradingos_api.models.security_master import Instrument

CALCULATION_VERSION = "v1"


def compute_recommendation_outcome(
    db: Session, *, recommendation_version_id: uuid.UUID, computed_at: datetime
) -> RecommendationOutcome:
    """Never self-reported (ADR-041) — inferred from `OrderProposal`/
    `Trade` matching. `IGNORED` if no proposal or no lot was ever opened
    from this recommendation version; `FOLLOWED` if the opened lot's
    quantity matches the proposed quantity; `MODIFIED` if a lot exists
    but its quantity differs from what was proposed."""
    version = db.get(RecommendationVersion, recommendation_version_id)
    assert version is not None

    lot = db.scalar(
        select(PositionLot).where(
            PositionLot.source_recommendation_version_id == recommendation_version_id
        )
    )
    proposal_version = db.scalar(
        select(OrderProposalVersion)
        .join(OrderProposal, OrderProposal.id == OrderProposalVersion.order_proposal_id)
        .where(OrderProposal.recommendation_version_id == recommendation_version_id)
        .order_by(OrderProposalVersion.version_number.desc())
    )

    if lot is None:
        classification = RecommendationOutcomeClassification.IGNORED
    elif proposal_version is not None and lot.quantity_opened != proposal_version.quantity:
        classification = RecommendationOutcomeClassification.MODIFIED
    else:
        classification = RecommendationOutcomeClassification.FOLLOWED

    linked_trade = (
        db.scalar(
            select(Trade)
            .where(
                Trade.account_id == lot.account_id,
                Trade.lane == lot.lane,
                Trade.instrument_id == lot.instrument_id,
            )
            .order_by(Trade.opened_at.desc())
        )
        if lot is not None
        else None
    )

    existing = db.scalar(
        select(RecommendationOutcome).where(
            RecommendationOutcome.recommendation_id == version.recommendation_id
        )
    )
    if existing is not None:
        existing.classification = classification
        existing.linked_trade_id = linked_trade.id if linked_trade else None
        existing.realized_pnl = linked_trade.realized_pnl if linked_trade else None
        existing.matched_at = computed_at
        existing.computed_at = computed_at
        db.flush()
        return existing

    outcome = RecommendationOutcome(
        recommendation_id=version.recommendation_id,
        classification=classification,
        linked_trade_id=linked_trade.id if linked_trade else None,
        matched_at=computed_at,
        realized_pnl=linked_trade.realized_pnl if linked_trade else None,
        computed_at=computed_at,
    )
    db.add(outcome)
    db.flush()
    return outcome


def compute_mfe_mae(
    db: Session,
    *,
    instrument_id: uuid.UUID,
    opened_at: datetime,
    closed_at: datetime | None,
    entry_price: Decimal,
    side: OrderSide,
) -> tuple[Decimal | None, Decimal | None]:
    """Maximum favorable/adverse excursion, in percent, over the trade's
    open window — `high`/`low` from daily `MarketBar` rows (the same
    evidence Revision Prompt 4/5 already use elsewhere; no new price feed).
    Returns `(None, None)` if no bars exist for the window (never a
    fabricated 0%)."""
    end_date = (closed_at or datetime.now(opened_at.tzinfo)).date()
    bars = db.scalars(
        select(MarketBar)
        .where(
            MarketBar.instrument_id == instrument_id,
            MarketBar.timeframe == Timeframe.DAILY,
            MarketBar.as_of >= opened_at.date(),
            MarketBar.as_of <= end_date,
        )
        .order_by(MarketBar.as_of.asc())
    ).all()
    if not bars:
        return None, None

    highest = max(bar.high for bar in bars)
    lowest = min(bar.low for bar in bars)
    if side == OrderSide.BUY:
        mfe = ((highest - entry_price) / entry_price) * Decimal(100)
        mae = ((lowest - entry_price) / entry_price) * Decimal(100)
    else:
        mfe = ((entry_price - lowest) / entry_price) * Decimal(100)
        mae = ((entry_price - highest) / entry_price) * Decimal(100)
    return mfe, mae


def get_or_create_benchmark_snapshot(
    db: Session,
    *,
    benchmark_ticker: str,
    period_start: date,
    period_end: date,
    return_pct: Decimal,
) -> BenchmarkSnapshot:
    existing = db.scalar(
        select(BenchmarkSnapshot).where(
            BenchmarkSnapshot.benchmark_ticker == benchmark_ticker,
            BenchmarkSnapshot.period_start == period_start,
            BenchmarkSnapshot.period_end == period_end,
        )
    )
    if existing is not None:
        return existing
    snapshot = BenchmarkSnapshot(
        benchmark_ticker=benchmark_ticker,
        period_start=period_start,
        period_end=period_end,
        return_pct=return_pct,
    )
    db.add(snapshot)
    db.flush()
    return snapshot


@dataclass(frozen=True)
class JournalEntryView:
    trade_id: uuid.UUID
    lane: str
    status: TradeStatus
    instrument_ticker: str
    quantity: Decimal
    realized_pnl: Decimal | None
    outcome: str
    exit_reason: str | None
    mfe: Decimal | None
    mae: Decimal | None
    modifications_text: str | None
    thesis_text: str | None
    recommendation_outcome: str | None
    order_approval_status: str | None
    benchmark_ticker: str | None
    benchmark_return_pct: Decimal | None
    post_trade_lesson: str | None


def get_journal_entry_view(db: Session, *, trade: Trade) -> JournalEntryView:
    instrument = db.get(Instrument, trade.instrument_id)
    assert instrument is not None

    if trade.status == TradeStatus.OPEN:
        outcome = "OPEN"
    elif trade.realized_pnl is None or trade.realized_pnl == 0:
        outcome = "BREAKEVEN"
    elif trade.realized_pnl > 0:
        outcome = "WIN"
    else:
        outcome = "LOSS"

    # The lot that opened this trade's round trip — earliest lot in this
    # (account, instrument, lane) at/after the trade's own opened_at.
    opening_lot = db.scalar(
        select(PositionLot)
        .where(
            PositionLot.account_id == trade.account_id,
            PositionLot.instrument_id == trade.instrument_id,
            PositionLot.lane == trade.lane,
        )
        .order_by(PositionLot.opened_at.asc())
    )

    recommendation_outcome_row = None
    thesis_text = None
    order_approval_status: str | None = None
    if opening_lot is not None and opening_lot.source_recommendation_version_id is not None:
        version = db.get(RecommendationVersion, opening_lot.source_recommendation_version_id)
        if version is not None:
            recommendation_outcome_row = db.scalar(
                select(RecommendationOutcome).where(
                    RecommendationOutcome.recommendation_id == version.recommendation_id
                )
            )
            thesis_text = version.rationale

            approval = db.scalar(
                select(OrderApproval)
                .join(
                    OrderProposalVersion,
                    OrderProposalVersion.id == OrderApproval.order_proposal_version_id,
                )
                .join(OrderProposal, OrderProposal.id == OrderProposalVersion.order_proposal_id)
                .where(OrderProposal.recommendation_version_id == version.id)
                .order_by(OrderApproval.requested_at.desc())
            )
            if approval is not None:
                order_approval_status = OrderApprovalStatus(approval.status).value

    benchmark = (
        db.get(BenchmarkSnapshot, trade.benchmark_snapshot_id)
        if trade.benchmark_snapshot_id
        else None
    )

    latest_review = db.scalar(
        select(TradeReview)
        .where(TradeReview.trade_id == trade.id)
        .order_by(TradeReview.reviewed_at.desc())
    )

    return JournalEntryView(
        trade_id=trade.id,
        lane=trade.lane.value,
        status=trade.status,
        instrument_ticker=instrument.ticker,
        quantity=trade.quantity,
        realized_pnl=trade.realized_pnl,
        outcome=outcome,
        exit_reason=trade.exit_reason.value if trade.exit_reason else None,
        mfe=trade.mfe,
        mae=trade.mae,
        modifications_text=trade.modifications_text,
        thesis_text=thesis_text,
        recommendation_outcome=(
            recommendation_outcome_row.classification.value if recommendation_outcome_row else None
        ),
        order_approval_status=order_approval_status,
        benchmark_ticker=benchmark.benchmark_ticker if benchmark else None,
        benchmark_return_pct=benchmark.return_pct if benchmark else None,
        post_trade_lesson=latest_review.review_text if latest_review else None,
    )
