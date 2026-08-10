"""Active-position monitoring screens (Revision Prompt 11): active-
position cards and the per-instrument event timeline. The other two
required screens are served by endpoints that already existed before
this revision — the alert center is `GET /api/v1/alerts`
(`routers/alerts.py`, extended this revision with `alert_type`/
`expires_at`/`dedup_key`/evidence fields) and the confirmation checklist
is `GET /api/v1/feature-diagnostics/post-earnings/{earnings_event_id}/latest`
(`routers/feature_diagnostics.py`, Revision Prompt 5) — this revision's
own contribution to that screen is `services/post_earnings_workflow.py`
actually persisting a `PostEarningsConfirmationSnapshot` for it to read,
not a new route. `get_post_earnings_workflow_status` below adds the
workflow's own run status alongside that gate-level detail.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from tradingos_api.core.dependencies import get_market_quote_provider
from tradingos_api.db.session import get_db
from tradingos_api.models.enums import AlertStatus
from tradingos_api.models.execution import Position
from tradingos_api.models.market_evidence import (
    EarningsActual,
    EarningsEvent,
    EarningsGuidanceItem,
)
from tradingos_api.models.monitoring import PostEarningsWorkflowRun
from tradingos_api.models.operations import Alert
from tradingos_api.models.security_master import Instrument
from tradingos_api.providers.quotes_bars import MarketQuoteProvider
from tradingos_api.schemas.alerts import AlertResponse
from tradingos_api.schemas.instruments import InstrumentResponse
from tradingos_api.schemas.monitoring import (
    ActivePositionCardResponse,
    PostEarningsWorkflowStatusResponse,
    TimelineEntryResponse,
)
from tradingos_api.services.alerts_engine import expire_stale_alerts
from tradingos_api.services.holding_guidance import (
    get_investment_holding_guidance,
    get_tactical_holding_guidance,
)
from tradingos_api.services.portfolio_accounting import get_open_lots

router = APIRouter(prefix="/api/v1/monitoring", tags=["monitoring"])


def _next_earnings_event(db: Session, *, instrument_id: uuid.UUID) -> EarningsEvent | None:
    today = datetime.now(UTC).date()
    return db.scalar(
        select(EarningsEvent)
        .where(EarningsEvent.instrument_id == instrument_id, EarningsEvent.report_date >= today)
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


@router.get("/positions", response_model=list[ActivePositionCardResponse])
def list_active_position_cards(
    account_id: uuid.UUID,
    db: Session = Depends(get_db),
    quote_provider: MarketQuoteProvider = Depends(get_market_quote_provider),
) -> list[ActivePositionCardResponse]:
    """Lazily expires stale alerts before building cards — the same
    "never surface a past-expiry alert as still open" discipline
    `routers/alerts.py::list_alerts()` applies to the alert list."""
    expire_stale_alerts(db, now=datetime.now(UTC))
    db.commit()

    positions = db.scalars(
        select(Position).where(Position.account_id == account_id, Position.quantity != 0)
    ).all()

    cards: list[ActivePositionCardResponse] = []
    for position in positions:
        instrument = db.get(Instrument, position.instrument_id)
        if instrument is None:
            continue

        quote = quote_provider.get_latest_quote(instrument.ticker)
        current_price = Decimal(quote.price) if quote is not None else None
        quote_observed_at = quote.observed_at if quote is not None else None

        unrealized_pnl = None
        unrealized_pnl_pct = None
        if current_price is not None and position.avg_cost > 0:
            unrealized_pnl = (current_price - position.avg_cost) * position.quantity
            unrealized_pnl_pct = (current_price - position.avg_cost) / position.avg_cost * 100

        lots = get_open_lots(db, account_id=account_id, instrument_id=position.instrument_id)
        lanes = sorted({lot.lane.value for lot in lots})
        stop_price = None
        target_prices: list[Decimal] = []
        today = datetime.now(UTC).date()
        for lot in lots:
            if lot.lane.value == "TACTICAL":
                guidance = get_tactical_holding_guidance(db, lot=lot, as_of=today)
                if stop_price is None:
                    stop_price = guidance.stop_price
                target_prices.extend(guidance.target_prices)
            elif lot.lane.value == "INVESTMENT":
                # Investment lots have no stop/target concept in this
                # model — the call still runs so a caller who only cares
                # about `lanes` sees INVESTMENT represented, but nothing
                # from it feeds stop/target.
                get_investment_holding_guidance(db, lot=lot, as_of=today)

        next_earnings = _next_earnings_event(db, instrument_id=position.instrument_id)
        open_alerts = _open_alerts(db, instrument_id=position.instrument_id)

        cards.append(
            ActivePositionCardResponse(
                instrument=InstrumentResponse.model_validate(instrument),
                quantity=position.quantity,
                avg_cost=position.avg_cost,
                current_price=current_price,
                quote_observed_at=quote_observed_at,
                unrealized_pnl=unrealized_pnl,
                unrealized_pnl_pct=unrealized_pnl_pct,
                stop_price=stop_price,
                target_prices=target_prices,
                upcoming_earnings_date=next_earnings.report_date if next_earnings else None,
                lanes=lanes,
                open_alerts=[AlertResponse.model_validate(a) for a in open_alerts],
            )
        )
    return cards


@router.get(
    "/positions/{instrument_id}/timeline",
    response_model=list[TimelineEntryResponse],
)
def get_position_timeline(
    instrument_id: uuid.UUID, db: Session = Depends(get_db)
) -> list[TimelineEntryResponse]:
    """Merges earnings-calendar, actuals, guidance, and alert history for
    one instrument into a single chronological feed — read-only, no new
    business logic (the same "composing view over already-existing data"
    discipline `services/holding_guidance.py` documents for itself)."""
    if db.get(Instrument, instrument_id) is None:
        raise HTTPException(status_code=404, detail="Instrument not found.")

    entries: list[TimelineEntryResponse] = []

    events = db.scalars(
        select(EarningsEvent).where(EarningsEvent.instrument_id == instrument_id)
    ).all()
    event_ids = [e.id for e in events]
    for event in events:
        entries.append(
            TimelineEntryResponse(
                occurred_at=datetime.combine(event.report_date, datetime.min.time(), tzinfo=UTC),
                kind="EARNINGS_EVENT",
                title=f"Earnings event scheduled ({event.fiscal_period or 'unknown period'})",
                detail=f"timing_category={event.timing_category.value}",
            )
        )

    if event_ids:
        actuals = db.scalars(
            select(EarningsActual).where(EarningsActual.earnings_event_id.in_(event_ids))
        ).all()
        for actual in actuals:
            entries.append(
                TimelineEntryResponse(
                    occurred_at=actual.reported_at,
                    kind="EARNINGS_ACTUAL",
                    title=f"{actual.metric.upper()} reported: {actual.actual_value}",
                    detail=f"source={actual.source}",
                )
            )

        guidance_items = db.scalars(
            select(EarningsGuidanceItem).where(
                EarningsGuidanceItem.earnings_event_id.in_(event_ids)
            )
        ).all()
        for item in guidance_items:
            entries.append(
                TimelineEntryResponse(
                    occurred_at=item.issued_at,
                    kind="GUIDANCE_ISSUED",
                    title=f"Guidance issued for {item.metric} ({item.period or 'unknown period'})",
                    detail=(
                        f"midpoint={item.guidance_midpoint}" if item.guidance_midpoint else None
                    ),
                )
            )

    alerts = db.scalars(select(Alert).where(Alert.instrument_id == instrument_id)).all()
    for alert in alerts:
        entries.append(
            TimelineEntryResponse(
                occurred_at=alert.triggered_at,
                kind=f"ALERT:{alert.alert_type.value}",
                title=alert.title,
                detail=alert.detail,
            )
        )

    entries.sort(key=lambda e: e.occurred_at)
    return entries


@router.get(
    "/positions/{instrument_id}/confirmation-status",
    response_model=PostEarningsWorkflowStatusResponse,
)
def get_post_earnings_workflow_status(
    instrument_id: uuid.UUID, account_id: uuid.UUID, db: Session = Depends(get_db)
) -> PostEarningsWorkflowStatusResponse:
    """The workflow's own run status, alongside the gate-level detail
    already served by `GET /api/v1/feature-diagnostics/post-earnings/
    {earnings_event_id}/latest` — together, the confirmation checklist
    screen's two data sources."""
    run = db.scalar(
        select(PostEarningsWorkflowRun)
        .where(
            PostEarningsWorkflowRun.instrument_id == instrument_id,
            PostEarningsWorkflowRun.account_id == account_id,
        )
        .order_by(PostEarningsWorkflowRun.created_at.desc())
    )
    if run is None:
        raise HTTPException(
            status_code=404, detail="No post-earnings confirmation workflow run for this position."
        )
    return PostEarningsWorkflowStatusResponse(
        id=run.id,
        earnings_event_id=run.earnings_event_id,
        instrument_id=run.instrument_id,
        account_id=run.account_id,
        status=run.status.value,
        reversal_detected=run.reversal_detected,
        results_ingested_at=run.results_ingested_at,
        confirmation_window_ends_at=run.confirmation_window_ends_at,
        pre_event_recommendation_id=run.pre_event_recommendation_id,
        post_event_recommendation_id=run.post_event_recommendation_id,
        detail=run.detail,
    )
