"""Earnings actuals provider + ingestion tests (Revision Prompt 11 task
70) — provider-level fixture lookup and ingestion-level idempotency
(the "duplicate release" required test category)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from tradingos_api.models.market_evidence import EarningsActual, EarningsEvent
from tradingos_api.models.security_master import Instrument
from tradingos_api.providers.synthetic_evidence import SyntheticEarningsActualsProvider
from tradingos_api.services.ingest_evidence import ingest_earnings_actuals


class TestProviderFixtureLookup:
    def test_amd_q3_2026_returns_eps_and_revenue(self) -> None:
        records = SyntheticEarningsActualsProvider().get_actuals("AMD", "Q3-2026")
        metrics = {r.metric: r.actual_value for r in records}
        assert metrics == {"eps": "1.2200", "revenue": "8350000000.00"}

    def test_unreleased_period_returns_empty_not_fabricated(self) -> None:
        assert SyntheticEarningsActualsProvider().get_actuals("AMD", "Q4-2026") == []

    def test_unknown_ticker_returns_empty(self) -> None:
        assert SyntheticEarningsActualsProvider().get_actuals("ZZZZ", "Q3-2026") == []

    def test_records_carry_official_source_type(self) -> None:
        records = SyntheticEarningsActualsProvider().get_actuals("AMD", "Q3-2026")
        assert all(r.source_type == "official_ir_release" for r in records)


class TestIngestionIsIdempotentAcrossDuplicateReleases:
    def _fresh_event(self, db_session: Session) -> EarningsEvent:
        amd = db_session.scalar(select(Instrument).where(Instrument.ticker == "AMD"))
        assert amd is not None
        event = EarningsEvent(
            instrument_id=amd.id, report_date=date(2026, 9, 1), source="test_fixture"
        )
        db_session.add(event)
        db_session.flush()
        return event

    def test_first_ingestion_writes_both_metrics(self, db_session: Session) -> None:
        event = self._fresh_event(db_session)
        created = ingest_earnings_actuals(
            db_session,
            SyntheticEarningsActualsProvider(),
            earnings_event_id=event.id,
            ticker="AMD",
            fiscal_period="Q3-2026",
        )
        assert len(created) == 2
        stored = db_session.scalars(
            select(EarningsActual).where(EarningsActual.earnings_event_id == event.id)
        ).all()
        assert len(stored) == 2
        eps_row = next(r for r in stored if r.metric == "eps")
        assert eps_row.actual_value == Decimal("1.2200")
        assert eps_row.usable_at is not None

    def test_replaying_the_same_release_does_not_duplicate_rows(self, db_session: Session) -> None:
        event = self._fresh_event(db_session)
        provider = SyntheticEarningsActualsProvider()
        ingest_earnings_actuals(
            db_session, provider, earnings_event_id=event.id, ticker="AMD", fiscal_period="Q3-2026"
        )
        second = ingest_earnings_actuals(
            db_session, provider, earnings_event_id=event.id, ticker="AMD", fiscal_period="Q3-2026"
        )
        assert len(second) == 2
        stored = db_session.scalars(
            select(EarningsActual).where(EarningsActual.earnings_event_id == event.id)
        ).all()
        assert len(stored) == 2

    def test_unreleased_period_ingests_nothing(self, db_session: Session) -> None:
        event = self._fresh_event(db_session)
        created = ingest_earnings_actuals(
            db_session,
            SyntheticEarningsActualsProvider(),
            earnings_event_id=event.id,
            ticker="AMD",
            fiscal_period="Q4-2026",
        )
        assert created == []
