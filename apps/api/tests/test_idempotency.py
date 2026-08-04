"""Idempotency and duplicate-event handling tests (docs/TASKS.md Phase 8
requirement): a retried request with the same idempotency key must be a
safe no-op, not a duplicate row."""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import cast

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from tradingos_api.models.execution import Account
from tradingos_api.models.security_master import Instrument


class TestOrderProposeIdempotency:
    def test_duplicate_propose_with_same_key_returns_same_order(
        self,
        client: TestClient,
        db_session: Session,
        fresh_account: Account,
        seeded_instrument_id: uuid.UUID,
    ) -> None:
        key = f"test-propose-{uuid.uuid4()}"
        payload = {
            "account_id": str(fresh_account.id),
            "instrument_id": str(seeded_instrument_id),
            "side": "BUY",
            "order_type": "MARKET",
            "quantity": "3",
            "limit_price": "50.00",
            "idempotency_key": key,
        }
        first = client.post("/api/v1/orders", json=payload)
        second = client.post("/api/v1/orders", json=payload)
        assert first.status_code == 201
        assert second.status_code == 201
        assert first.json()["id"] == second.json()["id"]

        count = db_session.execute(
            text("SELECT count(*) FROM orders WHERE idempotency_key = :k"), {"k": key}
        ).scalar()
        assert count == 1


class TestOrderImportIdempotency:
    def test_duplicate_import_fill_does_not_double_post(
        self,
        client: TestClient,
        db_session: Session,
        fresh_account: Account,
        seeded_instrument_id: uuid.UUID,
    ) -> None:
        key = f"test-import-{uuid.uuid4()}"
        payload = {
            "account_id": str(fresh_account.id),
            "fills": [
                {
                    "instrument_id": str(seeded_instrument_id),
                    "side": "BUY",
                    "quantity": "4",
                    "price": "60.00",
                    "executed_at": "2026-01-15T14:30:00Z",
                    "idempotency_key": key,
                }
            ],
        }
        first = client.post("/api/v1/orders/import", json=payload)
        second = client.post("/api/v1/orders/import", json=payload)
        assert first.status_code == 201
        assert second.status_code == 201
        assert first.json()[0]["id"] == second.json()[0]["id"]

        order_count = db_session.execute(
            text("SELECT count(*) FROM orders WHERE idempotency_key = :k"), {"k": key}
        ).scalar()
        assert order_count == 1

        position_qty = db_session.execute(
            text("SELECT quantity FROM positions WHERE account_id = :a AND instrument_id = :i"),
            {"a": fresh_account.id, "i": seeded_instrument_id},
        ).scalar()
        # Not 8 — the second import call must be a no-op, not a second fill.
        assert cast(Decimal, position_qty) == Decimal(4)


class TestWatchlistDuplicateItem:
    def test_adding_the_same_instrument_twice_is_rejected(
        self, client: TestClient, db_session: Session
    ) -> None:
        watchlist_id = db_session.execute(text("SELECT id FROM watchlists LIMIT 1")).scalar()
        # A brand-new instrument, guaranteed not already on the seeded
        # watchlist, so the *first* add succeeds and the *second* (the one
        # under test) is rejected purely by the duplicate-item rule.
        new_instrument = Instrument(
            ticker=f"IDT{uuid.uuid4().hex[:5].upper()}",
            name="Idempotency Test Co",
            exchange="NYSE",
            asset_type="EQUITY",
        )
        db_session.add(new_instrument)
        db_session.flush()

        payload = {"instrument_id": str(new_instrument.id), "tier": 2, "priority": 500}
        first = client.post(f"/api/v1/watchlists/{watchlist_id}/items", json=payload)
        second = client.post(f"/api/v1/watchlists/{watchlist_id}/items", json=payload)
        assert first.status_code == 201
        assert second.status_code == 409


class TestOptimisticConcurrency:
    def test_watchlist_item_update_with_stale_expected_updated_at_is_rejected(
        self, client: TestClient, db_session: Session
    ) -> None:
        item = db_session.execute(
            text("SELECT id, updated_at FROM watchlist_items LIMIT 1")
        ).first()
        assert item is not None
        item_id, updated_at = item

        stale_response = client.patch(
            f"/api/v1/watchlists/items/{item_id}",
            json={"priority": 1, "expected_updated_at": "2000-01-01T00:00:00Z"},
        )
        assert stale_response.status_code == 409

        fresh_response = client.patch(
            f"/api/v1/watchlists/items/{item_id}",
            json={"priority": 1, "expected_updated_at": updated_at.isoformat()},
        )
        assert fresh_response.status_code == 200
