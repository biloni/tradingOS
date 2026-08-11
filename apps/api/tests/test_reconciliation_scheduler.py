"""Tests for automatic (broker-fetched) reconciliation and the
reconciliation scheduling decision function (Revision Prompt 16
idempotency review)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from tradingos_api.models.enums import AccountType, ReconciliationStatus
from tradingos_api.models.execution import Account
from tradingos_api.models.portfolio_ext import ReconciliationRun
from tradingos_api.models.security_master import Instrument
from tradingos_api.services.reconciliation import reconcile_from_broker
from tradingos_api.services.reconciliation_scheduler import decide_reconciliation_schedule


class _FakePositionsBroker:
    """Implements only what `reconcile_from_broker()` calls — this
    project's established style for a minimal fake provider in tests
    (mirrors `_FakeLLM` in test_committee_orchestrator.py)."""

    def __init__(self, positions: list[dict[str, str]]) -> None:
        self._positions = positions

    def get_paper_positions(self) -> list[dict[str, str]]:
        return self._positions


def _account(db_session: Session) -> Account:
    account = db_session.scalar(select(Account).limit(1))
    assert account is not None
    return account


def _instrument(db_session: Session) -> Instrument:
    inst = db_session.scalar(select(Instrument).where(Instrument.ticker == "AMD"))
    assert inst is not None
    return inst


class TestReconcileFromBroker:
    def test_fetches_positions_from_the_broker_directly(self, db_session: Session) -> None:
        account = _account(db_session)
        instrument = _instrument(db_session)
        broker = _FakePositionsBroker(
            [
                {
                    "symbol": instrument.ticker,
                    "qty": "0",
                    "avg_entry_price": "",
                    "current_price": "",
                    "market_value": "",
                }
            ]
        )

        run, replayed = reconcile_from_broker(
            db_session,
            account_id=account.id,
            broker=broker,
            as_of=datetime.now(UTC),  # type: ignore[arg-type]
        )
        assert replayed is False
        assert run.overall_status == ReconciliationStatus.MATCHED

    def test_unknown_ticker_is_skipped_not_an_error(self, db_session: Session) -> None:
        account = _account(db_session)
        broker = _FakePositionsBroker(
            [
                {
                    "symbol": "NOT-A-REAL-TICKER",
                    "qty": "5",
                    "avg_entry_price": "",
                    "current_price": "",
                    "market_value": "",
                }
            ]
        )

        run, _replayed = reconcile_from_broker(
            db_session,
            account_id=account.id,
            broker=broker,
            as_of=datetime.now(UTC),  # type: ignore[arg-type]
        )
        # Nothing to compare (the unknown ticker was skipped, and this
        # account holds nothing) -- MATCHED, not an exception.
        assert run.overall_status == ReconciliationStatus.MATCHED

    def test_idempotency_key_passes_through(self, db_session: Session) -> None:
        account = _account(db_session)
        broker = _FakePositionsBroker([])

        first, first_replayed = reconcile_from_broker(
            db_session,
            account_id=account.id,
            broker=broker,  # type: ignore[arg-type]
            as_of=datetime.now(UTC),
            idempotency_key="auto-key-1",
        )
        second, second_replayed = reconcile_from_broker(
            db_session,
            account_id=account.id,
            broker=broker,  # type: ignore[arg-type]
            as_of=datetime.now(UTC),
            idempotency_key="auto-key-1",
        )
        assert first_replayed is False
        assert second_replayed is True
        assert second.id == first.id


class TestReconcileAutomaticEndpoint:
    def test_manual_account_is_rejected(self, client: TestClient, db_session: Session) -> None:
        manual_account = db_session.scalar(
            select(Account).where(Account.account_type == AccountType.MANUAL)
        )
        assert manual_account is not None

        response = client.post(
            f"/api/v1/portfolio/accounts/{manual_account.id}/reconcile-automatic"
        )
        assert response.status_code == 422

    def test_unknown_account_404s(self, client: TestClient) -> None:
        response = client.post(f"/api/v1/portfolio/accounts/{uuid.uuid4()}/reconcile-automatic")
        assert response.status_code == 404


class TestDecideReconciliationSchedule:
    def test_should_run_when_no_prior_run_exists(self, db_session: Session) -> None:
        account_id = uuid.uuid4()  # guaranteed no ReconciliationRun rows
        decision = decide_reconciliation_schedule(
            db_session, account_id=account_id, now=datetime.now(UTC)
        )
        assert decision.should_run is True
        assert "no prior reconciliation run" in decision.reason

    def test_should_not_run_when_recently_reconciled(self, db_session: Session) -> None:
        account = _account(db_session)
        now = datetime.now(UTC)
        db_session.add(
            ReconciliationRun(
                account_id=account.id,
                as_of=now - timedelta(hours=1),
                overall_status=ReconciliationStatus.MATCHED,
            )
        )
        db_session.flush()

        decision = decide_reconciliation_schedule(
            db_session,
            account_id=account.id,
            now=now,
            cadence=timedelta(hours=24),
        )
        assert decision.should_run is False

    def test_should_run_once_cadence_has_elapsed(self, db_session: Session) -> None:
        account = _account(db_session)
        now = datetime.now(UTC)
        db_session.add(
            ReconciliationRun(
                account_id=account.id,
                as_of=now - timedelta(hours=25),
                overall_status=ReconciliationStatus.MATCHED,
            )
        )
        db_session.flush()

        decision = decide_reconciliation_schedule(
            db_session,
            account_id=account.id,
            now=now,
            cadence=timedelta(hours=24),
        )
        assert decision.should_run is True
