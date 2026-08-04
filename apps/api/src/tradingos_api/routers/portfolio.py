"""Portfolio, positions, cash, and risk (docs/API_CONTRACTS.md area 5).

Cash is always derived from the append-only `cash_ledger`
(`starting_cash + sum(amount)`) — never stored directly, the same
"current state is a derived view" philosophy the shipped MVP already
used for `PriceBar`/`PaperPosition` (ADR-011/013), now backed by a real
ledger instead of a live recompute over order fills.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from tradingos_api.core.dependencies import get_current_user_id
from tradingos_api.db.session import get_db
from tradingos_api.models.execution import Account, CashLedgerEntry, Position, RiskSnapshot
from tradingos_api.models.security_master import Instrument
from tradingos_api.schemas.instruments import InstrumentResponse
from tradingos_api.schemas.portfolio import (
    AccountDetailResponse,
    AccountResponse,
    CashSummaryResponse,
    PositionResponse,
    RiskSnapshotResponse,
)

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
