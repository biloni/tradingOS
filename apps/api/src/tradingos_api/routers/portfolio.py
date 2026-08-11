"""Portfolio, positions, cash, and risk (docs/API_CONTRACTS.md area 5).

Cash is always derived from the append-only `cash_ledger`
(`starting_cash + sum(amount)`) — never stored directly, the same
"current state is a derived view" philosophy the shipped MVP already
used for `PriceBar`/`PaperPosition` (ADR-011/013), now backed by a real
ledger instead of a live recompute over order fills.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from tradingos_api.core.dependencies import get_broker_provider, get_current_user_id
from tradingos_api.db.session import get_db
from tradingos_api.models.enums import AccountType, OrderStatus, OrderType
from tradingos_api.models.execution import (
    Account,
    CashLedgerEntry,
    Execution,
    Order,
    Position,
    RiskSnapshot,
)
from tradingos_api.models.portfolio_ext import ReconciliationLine, ReconciliationRun
from tradingos_api.models.security_master import Instrument
from tradingos_api.providers.broker import PaperBrokerProvider
from tradingos_api.schemas.instruments import InstrumentResponse
from tradingos_api.schemas.portfolio import (
    AccountDetailResponse,
    AccountResponse,
    CashSummaryResponse,
    ImportBatchResponse,
    ImportRowResponse,
    InvestmentHoldingGuidanceResponse,
    LotWithGuidanceResponse,
    ManualFillRequest,
    ManualFillResponse,
    PositionDetailResponse,
    PositionLotResponse,
    PositionResponse,
    ReconciliationLineResponse,
    ReconciliationRequest,
    ReconciliationRunResponse,
    RiskSnapshotResponse,
    SubpositionResponse,
    TacticalHoldingGuidanceResponse,
)
from tradingos_api.services.csv_import import import_execution_csv
from tradingos_api.services.holding_guidance import (
    get_investment_holding_guidance,
    get_tactical_holding_guidance,
)
from tradingos_api.services.lane_attribution import get_combined_position_view
from tradingos_api.services.portfolio_accounting import apply_execution, get_open_lots
from tradingos_api.services.reconciliation import reconcile_from_broker, run_reconciliation

router = APIRouter(prefix="/api/v1/portfolio", tags=["portfolio"])


def _get_cash(db: Session, account: Account) -> CashSummaryResponse:
    ledger_sum = db.scalar(
        select(func.coalesce(func.sum(CashLedgerEntry.amount), 0)).where(
            CashLedgerEntry.account_id == account.id
        )
    ) or Decimal(0)
    return CashSummaryResponse(
        account_id=account.id,
        cash=account.starting_cash + ledger_sum,
        starting_cash=account.starting_cash,
    )


@router.get("/accounts", response_model=list[AccountResponse])
def list_accounts(
    db: Session = Depends(get_db), owner_user_id: uuid.UUID = Depends(get_current_user_id)
) -> list[AccountResponse]:
    rows = db.scalars(select(Account).where(Account.owner_user_id == owner_user_id)).all()
    return [AccountResponse.model_validate(r) for r in rows]


@router.get("/accounts/{account_id}", response_model=AccountDetailResponse)
def get_account_detail(
    account_id: uuid.UUID, db: Session = Depends(get_db)
) -> AccountDetailResponse:
    account = db.get(Account, account_id)
    if account is None:
        raise HTTPException(status_code=404, detail="Account not found.")

    positions = db.scalars(
        select(Position).where(Position.account_id == account_id, Position.quantity != 0)
    ).all()
    position_responses = []
    for pos in positions:
        inst = db.get(Instrument, pos.instrument_id)
        assert inst is not None
        position_responses.append(
            PositionResponse(
                instrument=InstrumentResponse.model_validate(inst),
                quantity=pos.quantity,
                avg_cost=pos.avg_cost,
                market_value=None,
            )
        )

    risk_snapshot = db.scalar(
        select(RiskSnapshot)
        .where(RiskSnapshot.account_id == account_id)
        .order_by(RiskSnapshot.as_of.desc())
    )
    risk_response = RiskSnapshotResponse.model_validate(risk_snapshot) if risk_snapshot else None

    return AccountDetailResponse(
        account=AccountResponse.model_validate(account),
        cash=_get_cash(db, account),
        positions=position_responses,
        latest_risk_snapshot=risk_response,
    )


@router.get(
    "/accounts/{account_id}/positions/{instrument_id}", response_model=PositionDetailResponse
)
def get_position_detail(
    account_id: uuid.UUID, instrument_id: uuid.UUID, db: Session = Depends(get_db)
) -> PositionDetailResponse:
    """ "Show combined broker position and separate analytical
    subpositions" plus per-lot holding guidance — the position-detail
    screen Revision Prompt 8 asks for."""
    instrument = db.get(Instrument, instrument_id)
    if instrument is None:
        raise HTTPException(status_code=404, detail="Instrument not found.")

    view = get_combined_position_view(db, account_id=account_id, instrument_id=instrument_id)
    lots = get_open_lots(db, account_id=account_id, instrument_id=instrument_id)

    today = datetime.now(UTC).date()
    lot_responses: list[LotWithGuidanceResponse] = []
    for lot in lots:
        investment_guidance = None
        tactical_guidance = None
        if lot.lane.value == "INVESTMENT":
            g = get_investment_holding_guidance(db, lot=lot, as_of=today)
            investment_guidance = InvestmentHoldingGuidanceResponse(**g.__dict__)
        elif lot.lane.value == "TACTICAL":
            t = get_tactical_holding_guidance(db, lot=lot, as_of=today)
            tactical_guidance = TacticalHoldingGuidanceResponse(**t.__dict__)
        lot_responses.append(
            LotWithGuidanceResponse(
                lot=PositionLotResponse.model_validate(lot),
                investment_guidance=investment_guidance,
                tactical_guidance=tactical_guidance,
            )
        )

    return PositionDetailResponse(
        instrument=InstrumentResponse.model_validate(instrument),
        combined_quantity=view.combined_quantity,
        combined_avg_cost=view.combined_avg_cost,
        subpositions=[
            SubpositionResponse(
                lane=s.lane, quantity=s.quantity, avg_cost=s.avg_cost, lot_count=s.lot_count
            )
            for s in view.subpositions.values()
        ],
        lots=lot_responses,
    )


@router.post(
    "/accounts/{account_id}/manual-fill", response_model=ManualFillResponse, status_code=201
)
def create_manual_fill(
    account_id: uuid.UUID, payload: ManualFillRequest, db: Session = Depends(get_db)
) -> ManualFillResponse:
    """Manual execution entry — the "manual entry" screen. Creates a
    real `Order`(`FILLED`)/`Execution` pair and applies it through the
    same accounting engine every other fill path uses; there is no
    separate "manual" code path in `services/portfolio_accounting.py`."""
    account = db.get(Account, account_id)
    if account is None:
        raise HTTPException(status_code=404, detail="Account not found.")
    instrument = db.scalar(select(Instrument).where(Instrument.ticker == payload.ticker.upper()))
    if instrument is None:
        raise HTTPException(status_code=422, detail=f"Unknown ticker: {payload.ticker}")

    order = Order(
        account_id=account_id,
        instrument_id=instrument.id,
        side=payload.side,
        order_type=OrderType.MARKET,
        quantity=payload.quantity,
        status=OrderStatus.FILLED,
    )
    db.add(order)
    db.flush()
    execution = Execution(
        order_id=order.id,
        quantity=payload.quantity,
        price=payload.price,
        executed_at=payload.executed_at,
    )
    db.add(execution)
    db.flush()

    result = apply_execution(
        db,
        execution=execution,
        account_id=account_id,
        instrument_id=instrument.id,
        side=payload.side,
        lane=payload.lane,
        source_recommendation_version_id=payload.source_recommendation_version_id,
    )
    db.commit()
    return ManualFillResponse(
        execution_id=execution.id,
        position_id=result.position_id,
        realized_pnl=result.realized_pnl,
        trade_id=result.trade_id,
        lane_selection_is_certain=result.lane_selection_is_certain,
    )


@router.post("/accounts/{account_id}/import-csv", response_model=ImportBatchResponse)
async def import_csv(
    account_id: uuid.UUID, file: UploadFile, db: Session = Depends(get_db)
) -> ImportBatchResponse:
    account = db.get(Account, account_id)
    if account is None:
        raise HTTPException(status_code=404, detail="Account not found.")
    file_bytes = await file.read()
    try:
        outcome = import_execution_csv(
            db,
            account_id=account_id,
            filename=file.filename or "upload.csv",
            file_bytes=file_bytes,
            imported_at=datetime.now(UTC),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    db.commit()
    return ImportBatchResponse(
        id=outcome.batch.id,
        source_filename=outcome.batch.source_filename,
        imported_at=outcome.batch.imported_at,
        row_count=outcome.batch.row_count,
        was_duplicate_batch=outcome.was_duplicate_batch,
        rows=[ImportRowResponse.model_validate(r) for r in outcome.rows],
    )


def _reconciliation_run_response(
    db: Session, run: ReconciliationRun, *, replayed: bool = False
) -> ReconciliationRunResponse:
    lines = db.scalars(
        select(ReconciliationLine).where(ReconciliationLine.reconciliation_run_id == run.id)
    ).all()
    line_responses = []
    for line in lines:
        inst = db.get(Instrument, line.instrument_id)
        assert inst is not None
        line_responses.append(
            ReconciliationLineResponse(
                instrument=InstrumentResponse.model_validate(inst),
                internal_quantity=line.internal_quantity,
                broker_reported_quantity=line.broker_reported_quantity,
                status=line.status,
                discrepancy_detail=line.discrepancy_detail,
            )
        )
    return ReconciliationRunResponse(
        id=run.id,
        as_of=run.as_of,
        overall_status=run.overall_status,
        lines=line_responses,
        replayed=replayed,
    )


@router.post("/accounts/{account_id}/reconcile", response_model=ReconciliationRunResponse)
def reconcile_account(
    account_id: uuid.UUID, payload: ReconciliationRequest, db: Session = Depends(get_db)
) -> ReconciliationRunResponse:
    account = db.get(Account, account_id)
    if account is None:
        raise HTTPException(status_code=404, detail="Account not found.")

    broker_positions: dict[uuid.UUID, Decimal] = {}
    for ticker, quantity in payload.broker_reported_positions.items():
        instrument = db.scalar(select(Instrument).where(Instrument.ticker == ticker.upper()))
        if instrument is None:
            raise HTTPException(status_code=422, detail=f"Unknown ticker: {ticker}")
        broker_positions[instrument.id] = quantity

    run, replayed = run_reconciliation(
        db,
        account_id=account_id,
        as_of=datetime.now(UTC),
        broker_reported_positions=broker_positions,
        idempotency_key=payload.idempotency_key,
    )
    db.commit()
    return _reconciliation_run_response(db, run, replayed=replayed)


@router.post("/accounts/{account_id}/reconcile-automatic", response_model=ReconciliationRunResponse)
def reconcile_account_automatic(
    account_id: uuid.UUID,
    idempotency_key: str | None = None,
    db: Session = Depends(get_db),
    broker: PaperBrokerProvider = Depends(get_broker_provider),
) -> ReconciliationRunResponse:
    """Revision Prompt 16 idempotency review — "scheduled reconciliation."
    No always-on scheduler exists in this deployment yet
    (`services/reconciliation_scheduler.py::decide_reconciliation_schedule()`
    is the same pure-decision-function pattern `morning_plan_scheduler.py`
    already established, ready for whatever eventually calls it on a
    real timer — see task: real always-on scheduler/worker process).
    What this endpoint closes today: reconciliation no longer *requires*
    a human to manually type broker-reported quantities — it calls
    `broker.get_paper_positions()` directly. Only meaningful for a
    `PAPER_ALPACA` account (a `MANUAL` account has no broker feed to
    fetch, same as the existing manual-entry endpoint's `MANUAL`
    handling)."""
    account = db.get(Account, account_id)
    if account is None:
        raise HTTPException(status_code=404, detail="Account not found.")
    if account.account_type != AccountType.PAPER_ALPACA:
        raise HTTPException(
            status_code=422,
            detail=(
                "Automatic reconciliation needs a broker feed — only PAPER_ALPACA accounts "
                "have one. Use POST .../reconcile with a manually-supplied broker report "
                "for a MANUAL account."
            ),
        )

    run, replayed = reconcile_from_broker(
        db,
        account_id=account_id,
        broker=broker,
        as_of=datetime.now(UTC),
        idempotency_key=idempotency_key,
    )
    db.commit()
    return _reconciliation_run_response(db, run, replayed=replayed)


@router.get(
    "/accounts/{account_id}/reconciliation-runs", response_model=list[ReconciliationRunResponse]
)
def list_reconciliation_runs(
    account_id: uuid.UUID, db: Session = Depends(get_db)
) -> list[ReconciliationRunResponse]:
    runs = db.scalars(
        select(ReconciliationRun)
        .where(ReconciliationRun.account_id == account_id)
        .order_by(ReconciliationRun.as_of.desc())
    ).all()
    return [_reconciliation_run_response(db, r) for r in runs]
