"""Order-flow endpoint tests run against an in-memory SQLite database and a
fake broker provider — no live Postgres, no real Alpaca calls, per the
project's fixtures-not-live-APIs test policy."""

from collections.abc import Generator
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from tradingos_api.core.dependencies import get_broker_provider
from tradingos_api.db.base import Base
from tradingos_api.db.session import get_db
from tradingos_api.main import app
from tradingos_api.models.price_bar import PriceBar, Timeframe
from tradingos_api.models.symbol import AssetType, Symbol
from tradingos_api.providers.broker import PaperOrderRequest, PaperOrderResult

STARTING_CASH = Decimal("10000.00")
SPY_PRICE = Decimal("500.00")


class FakeBrokerProvider:
    def __init__(self) -> None:
        self.submitted_requests: list[PaperOrderRequest] = []
        self.canceled_order_ids: list[str] = []
        self.positions: list[dict[str, str]] = []
        self.next_result: PaperOrderResult | None = None
        self.next_status_check_result: PaperOrderResult | None = None
        self.status_check_calls = 0

    def submit_paper_order(self, request: PaperOrderRequest) -> PaperOrderResult:
        self.submitted_requests.append(request)
        assert self.next_result is not None, "test must set next_result before confirming"
        return self.next_result

    def get_paper_order_status(self, broker_order_id: str) -> PaperOrderResult:
        self.status_check_calls += 1
        assert self.next_status_check_result is not None, (
            "test must set next_status_check_result before triggering a status check"
        )
        return self.next_status_check_result

    def get_paper_positions(self) -> list[dict[str, str]]:
        return self.positions

    def cancel_paper_order(self, broker_order_id: str) -> None:
        self.canceled_order_ids.append(broker_order_id)


@pytest.fixture
def broker() -> FakeBrokerProvider:
    return FakeBrokerProvider()


@pytest.fixture
def db_session(broker: FakeBrokerProvider) -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestSessionLocal = sessionmaker(bind=engine)
    session = TestSessionLocal()

    spy = Symbol(
        ticker="SPY", name="SPDR S&P 500 ETF", exchange="NYSEARCA", asset_type=AssetType.ETF
    )
    session.add(spy)
    session.commit()
    session.refresh(spy)

    session.add(
        PriceBar(
            symbol_id=spy.id,
            as_of=date.today(),
            timeframe=Timeframe.DAY,
            open=SPY_PRICE,
            high=SPY_PRICE,
            low=SPY_PRICE,
            close=SPY_PRICE,
            volume=1000,
            source="alpaca",
            adjustment="split",
            fetched_at=datetime.now(UTC),
        )
    )
    session.commit()

    def override_get_db() -> Generator[Session, None, None]:
        yield session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_broker_provider] = lambda: broker
    try:
        yield session
    finally:
        app.dependency_overrides.clear()
        session.close()


@pytest.fixture
def client(db_session: Session) -> TestClient:
    return TestClient(app)


def _propose(client: TestClient, **overrides: object) -> dict[str, Any]:
    body = {"ticker": "SPY", "side": "BUY", "quantity": 1, "order_type": "MARKET"}
    body.update(overrides)
    response = client.post("/api/v1/paper-orders", json=body)
    result: dict[str, Any] = response.json() | {"_status_code": response.status_code}
    return result


class TestProposeValidation:
    def test_rejected_for_insufficient_cash(self, client: TestClient) -> None:
        result = _propose(client, quantity=1000)  # 1000 * 500 >> 10000 cash
        assert result["_status_code"] == 400
        assert "exceeds available cash" in result["detail"]

    def test_rejected_for_insufficient_position_on_sell(self, client: TestClient) -> None:
        result = _propose(client, side="SELL", quantity=1)
        assert result["_status_code"] == 400
        assert "only 0 held" in result["detail"]

    def test_rejected_for_unknown_symbol(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/paper-orders",
            json={"ticker": "ZZZZ", "side": "BUY", "quantity": 1, "order_type": "MARKET"},
        )
        assert response.status_code == 404


class TestProposeConfirmFlow:
    def test_happy_path_updates_status_cash_and_position(
        self, client: TestClient, broker: FakeBrokerProvider
    ) -> None:
        proposed = _propose(client, quantity=1)
        assert proposed["_status_code"] == 201
        assert proposed["status"] == "DRAFT"
        order_id = proposed["id"]

        broker.next_result = PaperOrderResult(
            broker_order_id="broker-abc",
            status="filled",
            filled_quantity="1",
            filled_avg_price="500.00",
            filled_at=datetime.now(UTC).isoformat(),
        )
        confirm_response = client.post(f"/api/v1/paper-orders/{order_id}/confirm")
        assert confirm_response.status_code == 200
        confirmed = confirm_response.json()
        assert confirmed["status"] == "FILLED"
        assert confirmed["broker_order_id"] == "broker-abc"
        assert confirmed["filled_quantity"] == 1
        assert len(broker.submitted_requests) == 1
        assert broker.submitted_requests[0].symbol == "SPY"

        portfolio = client.get("/api/v1/portfolio").json()
        # Decimal arithmetic with the Numeric(18,6) filled_avg_price widens
        # the result's scale beyond starting_cash_usd's Numeric(18,2) — same
        # precision behavior observed in Phase 2 (docs/TEST_EVIDENCE.md).
        assert Decimal(portfolio["cash_usd"]) == STARTING_CASH - SPY_PRICE
        assert len(portfolio["positions"]) == 1
        assert portfolio["positions"][0]["ticker"] == "SPY"
        assert portfolio["positions"][0]["quantity"] == 1

    def test_double_confirm_rejected(self, client: TestClient, broker: FakeBrokerProvider) -> None:
        proposed = _propose(client, quantity=1)
        order_id = proposed["id"]
        broker.next_result = PaperOrderResult(
            broker_order_id="broker-abc",
            status="filled",
            filled_quantity="1",
            filled_avg_price="500.00",
            filled_at=datetime.now(UTC).isoformat(),
        )
        client.post(f"/api/v1/paper-orders/{order_id}/confirm")

        second_confirm = client.post(f"/api/v1/paper-orders/{order_id}/confirm")
        assert second_confirm.status_code == 400
        assert len(broker.submitted_requests) == 1  # not submitted again


class TestAsynchronousFill:
    """Order fills are asynchronous — a market order's submit response
    commonly reflects a pre-fill state. Confirmed live against the real
    Alpaca paper API (docs/TEST_EVIDENCE.md): a submitted market order came
    back "new", then filled moments later."""

    def test_confirm_catches_a_same_cycle_fill(
        self, client: TestClient, broker: FakeBrokerProvider
    ) -> None:
        proposed = _propose(client, quantity=1)
        broker.next_result = PaperOrderResult(
            broker_order_id="broker-abc",
            status="new",
            filled_quantity="0",
            filled_avg_price=None,
            filled_at=None,
        )
        broker.next_status_check_result = PaperOrderResult(
            broker_order_id="broker-abc",
            status="filled",
            filled_quantity="1",
            filled_avg_price="500.00",
            filled_at=datetime.now(UTC).isoformat(),
        )

        response = client.post(f"/api/v1/paper-orders/{proposed['id']}/confirm")

        assert response.status_code == 200
        assert response.json()["status"] == "FILLED"
        assert broker.status_check_calls == 1

    def test_refresh_endpoint_catches_a_later_fill(
        self, client: TestClient, broker: FakeBrokerProvider
    ) -> None:
        proposed = _propose(client, quantity=1)
        broker.next_result = PaperOrderResult(
            broker_order_id="broker-abc",
            status="new",
            filled_quantity="0",
            filled_avg_price=None,
            filled_at=None,
        )
        # The immediate re-check inside confirm also still sees "new" — a
        # slower fill that only /refresh (called later) will catch.
        broker.next_status_check_result = PaperOrderResult(
            broker_order_id="broker-abc",
            status="new",
            filled_quantity="0",
            filled_avg_price=None,
            filled_at=None,
        )
        confirm_response = client.post(f"/api/v1/paper-orders/{proposed['id']}/confirm")
        assert confirm_response.json()["status"] == "SUBMITTED"

        broker.next_status_check_result = PaperOrderResult(
            broker_order_id="broker-abc",
            status="filled",
            filled_quantity="1",
            filled_avg_price="500.00",
            filled_at=datetime.now(UTC).isoformat(),
        )
        refresh_response = client.post(f"/api/v1/paper-orders/{proposed['id']}/refresh")

        assert refresh_response.status_code == 200
        assert refresh_response.json()["status"] == "FILLED"

    def test_refresh_rejected_for_a_terminal_order(
        self, client: TestClient, broker: FakeBrokerProvider
    ) -> None:
        proposed = _propose(client, quantity=1)
        broker.next_result = PaperOrderResult(
            broker_order_id="broker-abc",
            status="filled",
            filled_quantity="1",
            filled_avg_price="500.00",
            filled_at=datetime.now(UTC).isoformat(),
        )
        client.post(f"/api/v1/paper-orders/{proposed['id']}/confirm")

        response = client.post(f"/api/v1/paper-orders/{proposed['id']}/refresh")
        assert response.status_code == 400


class TestCancel:
    def test_cancel_draft_order_does_not_call_broker(
        self, client: TestClient, broker: FakeBrokerProvider
    ) -> None:
        proposed = _propose(client, quantity=1)
        order_id = proposed["id"]

        response = client.post(f"/api/v1/paper-orders/{order_id}/cancel")
        assert response.status_code == 200
        assert response.json()["status"] == "CANCELED"
        assert broker.canceled_order_ids == []


class TestReconciliation:
    def test_matches_when_broker_reports_the_same_position(
        self, client: TestClient, broker: FakeBrokerProvider
    ) -> None:
        proposed = _propose(client, quantity=1)
        broker.next_result = PaperOrderResult(
            broker_order_id="broker-abc",
            status="filled",
            filled_quantity="1",
            filled_avg_price="500.00",
            filled_at=datetime.now(UTC).isoformat(),
        )
        client.post(f"/api/v1/paper-orders/{proposed['id']}/confirm")

        broker.positions = [
            {
                "symbol": "SPY",
                "qty": "1",
                "avg_entry_price": "500.00",
                "current_price": "500.00",
                "market_value": "500.00",
            }
        ]
        rows = client.get("/api/v1/portfolio/reconciliation").json()
        assert len(rows) == 1
        assert rows[0]["ticker"] == "SPY"
        assert rows[0]["our_quantity"] == 1
        assert rows[0]["discrepancy"] == "0"

    def test_flags_a_discrepancy(self, client: TestClient, broker: FakeBrokerProvider) -> None:
        proposed = _propose(client, quantity=1)
        broker.next_result = PaperOrderResult(
            broker_order_id="broker-abc",
            status="filled",
            filled_quantity="1",
            filled_avg_price="500.00",
            filled_at=datetime.now(UTC).isoformat(),
        )
        client.post(f"/api/v1/paper-orders/{proposed['id']}/confirm")

        broker.positions = []  # Alpaca reports nothing — a real divergence
        rows = client.get("/api/v1/portfolio/reconciliation").json()
        assert len(rows) == 1
        assert rows[0]["discrepancy"] == "1"
