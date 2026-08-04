"""Money/quantity precision tests (docs/TASKS.md Phase 8 requirement).

Two concerns: (1) the *database columns* are NUMERIC, never a binary
float type, and (2) a fractional-share order round-trips through the API
at full precision with exact Decimal arithmetic, not float drift.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import cast

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from tradingos_api.models.execution import Account


class TestColumnsAreNumericNeverFloat:
    def _column_type(self, db_session: Session, table: str, column: str) -> str:
        row = db_session.execute(
            text(
                "SELECT data_type FROM information_schema.columns "
                "WHERE table_name = :t AND column_name = :c"
            ),
            {"t": table, "c": column},
        ).first()
        assert row is not None, f"{table}.{column} not found"
        return cast(str, row[0])

    def test_order_quantity_and_prices_are_numeric(self, db_session: Session) -> None:
        for column in ("quantity", "limit_price", "stop_price"):
            data_type = self._column_type(db_session, "orders", column)
            assert data_type == "numeric", f"orders.{column} is {data_type}, expected numeric"

    def test_cash_ledger_amount_is_numeric(self, db_session: Session) -> None:
        data_type = self._column_type(db_session, "cash_ledger", "amount")
        assert data_type == "numeric"

    def test_position_lot_quantities_and_cost_are_numeric(self, db_session: Session) -> None:
        for column in ("quantity_opened", "quantity_remaining", "cost_basis_price"):
            data_type = self._column_type(db_session, "position_lots", column)
            assert data_type == "numeric"

    def test_market_bar_prices_are_numeric(self, db_session: Session) -> None:
        for column in ("open", "high", "low", "close"):
            data_type = self._column_type(db_session, "market_bars", column)
            assert data_type == "numeric"


class TestFractionalShareRoundTrip:
    """Fractional shares (project brief requirement) must round-trip
    through propose -> confirm -> fill -> position/cash-ledger without
    float error, using an amount that is *not* exactly representable in
    binary floating point (0.1 is the classic float-drift case)."""

    def test_fractional_quantity_and_cash_are_exact(
        self,
        client: TestClient,
        db_session: Session,
        fresh_account: Account,
        seeded_instrument_id: uuid.UUID,
    ) -> None:
        quantity = Decimal("0.1")
        price = Decimal("333.33")
        propose = client.post(
            "/api/v1/orders",
            json={
                "account_id": str(fresh_account.id),
                "instrument_id": str(seeded_instrument_id),
                "side": "BUY",
                "order_type": "MARKET",
                "quantity": str(quantity),
                "limit_price": str(price),
            },
        )
        assert propose.status_code == 201, propose.text
        order_id = propose.json()["id"]
        assert Decimal(propose.json()["quantity"]) == quantity

        confirm = client.post(f"/api/v1/orders/{order_id}/confirm")
        assert confirm.status_code == 200, confirm.text
        body = confirm.json()
        assert body["status"] == "FILLED"
        assert Decimal(body["executions"][0]["quantity"]) == quantity
        assert Decimal(body["executions"][0]["price"]) == price

        expected_cash_delta = -(price * quantity)  # exact Decimal multiply: -33.333
        account_detail = client.get(f"/api/v1/portfolio/accounts/{fresh_account.id}")
        assert account_detail.status_code == 200
        cash_body = account_detail.json()["cash"]
        actual_cash = Decimal(cash_body["cash"])
        starting_cash = Decimal(cash_body["starting_cash"])
        assert actual_cash - starting_cash == expected_cash_delta

        position = account_detail.json()["positions"][0]
        assert Decimal(position["quantity"]) == quantity

        ledger_amount = db_session.execute(
            text("SELECT amount FROM cash_ledger WHERE account_id = :a"),
            {"a": fresh_account.id},
        ).scalar()
        assert ledger_amount == expected_cash_delta.quantize(Decimal("0.000001"))
