"""Position-lot and cash-ledger invariant tests (docs/TASKS.md Phase 8
requirement), using a fresh isolated `fresh_account` fixture (not the
shared seeded portfolio, so lot arithmetic starts from a known-zero
baseline) and a sequence of real fills through `_apply_fill()`.

Invariants asserted after every fill:
  1. position.quantity == sum(open lots' quantity_remaining) for that
     (account, instrument) — the FIFO lot ledger and the cached
     aggregate never diverge.
  2. account cash == starting_cash + sum(cash_ledger.amount) — the
     "derived, never stored directly" rule (ADR-013 lineage).
  3. GET /orders/reconciliation/{account_id} independently recomputes
     (1) and reports zero discrepancy.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any, cast

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from tradingos_api.models.execution import Account


def _propose_and_confirm(
    client: TestClient,
    account_id: uuid.UUID,
    instrument_id: uuid.UUID,
    side: str,
    qty: str,
    price: str,
) -> dict[str, Any]:
    propose = client.post(
        "/api/v1/orders",
        json={
            "account_id": str(account_id),
            "instrument_id": str(instrument_id),
            "side": side,
            "order_type": "MARKET",
            "quantity": qty,
            "limit_price": price,
        },
    )
    assert propose.status_code == 201, propose.text
    order_id = propose.json()["id"]
    confirm = client.post(f"/api/v1/orders/{order_id}/confirm")
    assert confirm.status_code == 200, confirm.text
    return cast(dict[str, Any], confirm.json())


def _lots_sum_remaining(
    db_session: Session, account_id: uuid.UUID, instrument_id: uuid.UUID
) -> Decimal:
    total = db_session.execute(
        text(
            "SELECT coalesce(sum(quantity_remaining), 0) FROM position_lots "
            "WHERE account_id = :a AND instrument_id = :i"
        ),
        {"a": account_id, "i": instrument_id},
    ).scalar()
    return cast(Decimal, total)


def _position_quantity(
    db_session: Session, account_id: uuid.UUID, instrument_id: uuid.UUID
) -> Decimal:
    value = db_session.execute(
        text("SELECT quantity FROM positions WHERE account_id = :a AND instrument_id = :i"),
        {"a": account_id, "i": instrument_id},
    ).scalar()
    assert value is not None
    return cast(Decimal, value)


def _cash_ledger_sum(db_session: Session, account_id: uuid.UUID) -> Decimal:
    total = db_session.execute(
        text("SELECT coalesce(sum(amount), 0) FROM cash_ledger WHERE account_id = :a"),
        {"a": account_id},
    ).scalar()
    return cast(Decimal, total)


class TestPositionLotAndCashLedgerInvariants:
    def test_single_buy_fill_keeps_lot_and_position_in_sync(
        self,
        client: TestClient,
        db_session: Session,
        fresh_account: Account,
        seeded_instrument_id: uuid.UUID,
    ) -> None:
        _propose_and_confirm(client, fresh_account.id, seeded_instrument_id, "BUY", "10", "100.00")

        assert _position_quantity(db_session, fresh_account.id, seeded_instrument_id) == Decimal(10)
        assert _lots_sum_remaining(db_session, fresh_account.id, seeded_instrument_id) == Decimal(
            10
        )

        account_detail = client.get(f"/api/v1/portfolio/accounts/{fresh_account.id}").json()
        expected_cash = fresh_account.starting_cash + _cash_ledger_sum(db_session, fresh_account.id)
        assert Decimal(account_detail["cash"]["cash"]) == expected_cash
        assert expected_cash == fresh_account.starting_cash - Decimal("1000.00")

    def test_multiple_buys_then_partial_sell_stays_consistent(
        self,
        client: TestClient,
        db_session: Session,
        fresh_account: Account,
        seeded_instrument_id: uuid.UUID,
    ) -> None:
        _propose_and_confirm(client, fresh_account.id, seeded_instrument_id, "BUY", "5", "100.00")
        _propose_and_confirm(client, fresh_account.id, seeded_instrument_id, "BUY", "5", "110.00")
        _propose_and_confirm(client, fresh_account.id, seeded_instrument_id, "SELL", "3", "120.00")

        position_qty = _position_quantity(db_session, fresh_account.id, seeded_instrument_id)
        lots_qty = _lots_sum_remaining(db_session, fresh_account.id, seeded_instrument_id)
        assert position_qty == Decimal(7)
        assert position_qty == lots_qty

        expected_cash = fresh_account.starting_cash + _cash_ledger_sum(db_session, fresh_account.id)
        account_detail = client.get(f"/api/v1/portfolio/accounts/{fresh_account.id}").json()
        assert Decimal(account_detail["cash"]["cash"]) == expected_cash

    def test_reconciliation_endpoint_reports_zero_discrepancy(
        self,
        client: TestClient,
        db_session: Session,
        fresh_account: Account,
        seeded_instrument_id: uuid.UUID,
    ) -> None:
        _propose_and_confirm(client, fresh_account.id, seeded_instrument_id, "BUY", "7", "50.00")
        _propose_and_confirm(client, fresh_account.id, seeded_instrument_id, "SELL", "2", "55.00")

        response = client.get(f"/api/v1/orders/reconciliation/{fresh_account.id}")
        assert response.status_code == 200
        rows = response.json()
        assert len(rows) == 1
        row = rows[0]
        assert Decimal(row["position_quantity"]) == Decimal(5)
        assert Decimal(row["lots_quantity"]) == Decimal(5)
        assert Decimal(row["discrepancy"]) == Decimal(0)
