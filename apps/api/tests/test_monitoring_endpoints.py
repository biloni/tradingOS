"""Monitoring router tests (Revision Prompt 11 task 74) — active-position
cards, event timeline, and confirmation-status, built through the real
manual-fill endpoint (Revision Prompt 8) so a card reflects an actual
`Position`/`PositionLot`, not a hand-constructed row."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from tradingos_api.models.execution import Account
from tradingos_api.models.market_evidence import EarningsEvent
from tradingos_api.models.security_master import Instrument


def _open_amd_position(
    client: TestClient, db_session: Session, fresh_account: Account
) -> uuid.UUID:
    response = client.post(
        f"/api/v1/portfolio/accounts/{fresh_account.id}/manual-fill",
        json={
            "side": "BUY",
            "ticker": "AMD",
            "quantity": "100",
            "price": "150.00",
            "executed_at": datetime.now(UTC).isoformat(),
            "lane": "TACTICAL",
        },
    )
    assert response.status_code == 201, response.text
    amd = db_session.scalar(select(Instrument).where(Instrument.ticker == "AMD"))
    assert amd is not None
    return amd.id


class TestActivePositionCards:
    def test_open_position_produces_a_card(
        self, client: TestClient, db_session: Session, fresh_account: Account
    ) -> None:
        _open_amd_position(client, db_session, fresh_account)
        response = client.get(
            "/api/v1/monitoring/positions", params={"account_id": str(fresh_account.id)}
        )
        assert response.status_code == 200
        cards = response.json()
        assert len(cards) == 1
        card = cards[0]
        assert card["instrument"]["ticker"] == "AMD"
        assert card["quantity"] == "100.00000000"
        assert "TACTICAL" in card["lanes"]

    def test_no_open_positions_returns_empty_list(
        self, client: TestClient, fresh_account: Account
    ) -> None:
        response = client.get(
            "/api/v1/monitoring/positions", params={"account_id": str(fresh_account.id)}
        )
        assert response.status_code == 200
        assert response.json() == []


class TestPositionTimeline:
    def test_unknown_instrument_is_404(self, client: TestClient) -> None:
        response = client.get(f"/api/v1/monitoring/positions/{uuid.uuid4()}/timeline")
        assert response.status_code == 404

    def test_timeline_merges_earnings_events_in_chronological_order(
        self, client: TestClient, db_session: Session
    ) -> None:
        amd = db_session.scalar(select(Instrument).where(Instrument.ticker == "AMD"))
        assert amd is not None
        earlier = EarningsEvent(
            instrument_id=amd.id, report_date=date(2026, 5, 1), source="test_fixture"
        )
        later = EarningsEvent(
            instrument_id=amd.id, report_date=date(2026, 8, 1), source="test_fixture"
        )
        db_session.add_all([earlier, later])
        db_session.flush()

        response = client.get(f"/api/v1/monitoring/positions/{amd.id}/timeline")
        assert response.status_code == 200
        entries = response.json()
        event_entries = [e for e in entries if e["kind"] == "EARNINGS_EVENT"]
        assert len(event_entries) >= 2
        occurred_ats = [e["occurred_at"] for e in event_entries]
        assert occurred_ats == sorted(occurred_ats)


class TestConfirmationStatus:
    def test_no_workflow_run_is_404(self, client: TestClient, fresh_account: Account) -> None:
        response = client.get(
            f"/api/v1/monitoring/positions/{uuid.uuid4()}/confirmation-status",
            params={"account_id": str(fresh_account.id)},
        )
        assert response.status_code == 404
