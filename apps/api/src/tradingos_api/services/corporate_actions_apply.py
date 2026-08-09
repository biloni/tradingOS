"""Applying corporate actions to a portfolio (Revision Prompt 8). The
`CorporateAction` row itself (Revision Prompt 4) is an evidence-layer
*fact* — a split ratio or dividend amount reported by a provider; this
module is where that fact gets *applied* to one account's actual lots
and cash, idempotently (`CorporateActionApplication.idempotency_key`
prevents ever double-adjusting the same account for the same action).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from tradingos_api.models.enums import CashLedgerEntryType, CorporateActionType
from tradingos_api.models.execution import CashLedgerEntry
from tradingos_api.models.market_evidence import CorporateAction
from tradingos_api.models.portfolio_ext import CorporateActionApplication
from tradingos_api.services.portfolio_accounting import get_open_lots, recompute_position_aggregate

CALCULATION_VERSION = "v1"


def _idempotency_key(corporate_action_id: uuid.UUID, account_id: uuid.UUID) -> str:
    return f"{corporate_action_id}:{account_id}"


def _already_applied(
    db: Session, *, corporate_action_id: uuid.UUID, account_id: uuid.UUID
) -> CorporateActionApplication | None:
    return db.scalar(
        select(CorporateActionApplication).where(
            CorporateActionApplication.idempotency_key
            == _idempotency_key(corporate_action_id, account_id)
        )
    )


def apply_split(
    db: Session, *, corporate_action: CorporateAction, account_id: uuid.UUID, applied_at: datetime
) -> CorporateActionApplication:
    """Every open lot's `quantity_remaining`/`quantity_opened` is
    multiplied by the split ratio and `cost_basis_price` divided by it
    — total cost basis per lot is preserved exactly (`quantity * price`
    unchanged), matching how a real broker adjusts existing lots on a
    split's ex-date rather than creating new ones."""
    existing = _already_applied(db, corporate_action_id=corporate_action.id, account_id=account_id)
    if existing is not None:
        return existing
    if corporate_action.action_type != CorporateActionType.SPLIT or corporate_action.ratio is None:
        raise ValueError("apply_split requires a SPLIT corporate action with a ratio")

    ratio = corporate_action.ratio
    lots = get_open_lots(db, account_id=account_id, instrument_id=corporate_action.instrument_id)
    quantity_before = sum((lot.quantity_remaining for lot in lots), Decimal(0))
    for lot in lots:
        lot.quantity_opened *= ratio
        lot.quantity_remaining *= ratio
        lot.cost_basis_price /= ratio
    recompute_position_aggregate(
        db, account_id=account_id, instrument_id=corporate_action.instrument_id
    )
    quantity_after = quantity_before * ratio

    application = CorporateActionApplication(
        corporate_action_id=corporate_action.id,
        account_id=account_id,
        instrument_id=corporate_action.instrument_id,
        applied_at=applied_at,
        quantity_before=quantity_before,
        quantity_after=quantity_after,
        idempotency_key=_idempotency_key(corporate_action.id, account_id),
    )
    db.add(application)
    db.flush()
    return application


def apply_dividend(
    db: Session, *, corporate_action: CorporateAction, account_id: uuid.UUID, applied_at: datetime
) -> CorporateActionApplication:
    """Cash credit = `amount` (per-share) x shares held across every
    open lot at application time, regardless of lane — a dividend is
    paid on the combined position, a broker has no concept of lanes."""
    existing = _already_applied(db, corporate_action_id=corporate_action.id, account_id=account_id)
    if existing is not None:
        return existing
    if (
        corporate_action.action_type != CorporateActionType.DIVIDEND
        or corporate_action.amount is None
    ):
        raise ValueError("apply_dividend requires a DIVIDEND corporate action with an amount")

    lots = get_open_lots(db, account_id=account_id, instrument_id=corporate_action.instrument_id)
    shares_held = sum((lot.quantity_remaining for lot in lots), Decimal(0))
    cash_credit = shares_held * corporate_action.amount

    cash_entry = CashLedgerEntry(
        account_id=account_id,
        entry_type=CashLedgerEntryType.DIVIDEND,
        amount=cash_credit,
        occurred_at=applied_at,
    )
    db.add(cash_entry)
    db.flush()

    application = CorporateActionApplication(
        corporate_action_id=corporate_action.id,
        account_id=account_id,
        instrument_id=corporate_action.instrument_id,
        applied_at=applied_at,
        cash_credit_amount=cash_credit,
        cash_ledger_entry_id=cash_entry.id,
        idempotency_key=_idempotency_key(corporate_action.id, account_id),
    )
    db.add(application)
    db.flush()
    return application


def apply_unsupported_action(
    db: Session, *, corporate_action: CorporateAction, account_id: uuid.UUID, applied_at: datetime
) -> CorporateActionApplication:
    """A spinoff or merger has no numeric ratio/amount this schema
    models yet — recorded honestly as a no-numeric-effect application
    with a human-readable `detail`, not silently skipped or forced
    through the split/dividend math."""
    existing = _already_applied(db, corporate_action_id=corporate_action.id, account_id=account_id)
    if existing is not None:
        return existing
    application = CorporateActionApplication(
        corporate_action_id=corporate_action.id,
        account_id=account_id,
        instrument_id=corporate_action.instrument_id,
        applied_at=applied_at,
        detail=(
            f"{corporate_action.action_type.value} recorded — no automated lot/cash "
            "adjustment exists for this action type; review manually."
        ),
        idempotency_key=_idempotency_key(corporate_action.id, account_id),
    )
    db.add(application)
    db.flush()
    return application


def apply_corporate_action(
    db: Session, *, corporate_action: CorporateAction, account_id: uuid.UUID, applied_at: datetime
) -> CorporateActionApplication:
    if corporate_action.action_type == CorporateActionType.SPLIT:
        return apply_split(
            db, corporate_action=corporate_action, account_id=account_id, applied_at=applied_at
        )
    if corporate_action.action_type == CorporateActionType.DIVIDEND:
        return apply_dividend(
            db, corporate_action=corporate_action, account_id=account_id, applied_at=applied_at
        )
    return apply_unsupported_action(
        db, corporate_action=corporate_action, account_id=account_id, applied_at=applied_at
    )
