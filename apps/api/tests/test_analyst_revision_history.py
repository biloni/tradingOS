"""Analyst revision history tests (Revision Prompt 4's required test
#4) — both the provider-level windowing (`SyntheticAnalystRevisionProvider`)
and the ingestion-level persistence (`ingest_analyst_revisions`)."""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from tradingos_api.models.market_evidence import EarningsEvent, EarningsRevision
from tradingos_api.models.security_master import Instrument
from tradingos_api.providers.synthetic_evidence import SyntheticAnalystRevisionProvider
from tradingos_api.services.ingest_evidence import ingest_analyst_revisions


class TestProviderWindowFiltering:
    def test_7_day_window_returns_only_the_most_recent_revision(self) -> None:
        revisions = SyntheticAnalystRevisionProvider().get_revisions("AMD", 7)
        assert len(revisions) == 1
        assert revisions[0].new_eps_estimate == "1.1500"

    def test_30_day_window_returns_two_revisions_in_recency_order(self) -> None:
        revisions = SyntheticAnalystRevisionProvider().get_revisions("AMD", 30)
        assert [r.new_eps_estimate for r in revisions] == ["1.1500", "1.1000"]

    def test_90_day_window_returns_all_four_revisions(self) -> None:
        revisions = SyntheticAnalystRevisionProvider().get_revisions("AMD", 90)
        assert len(revisions) == 4

    def test_widening_the_window_never_drops_a_revision_already_included(self) -> None:
        seven = {
            r.new_eps_estimate for r in SyntheticAnalystRevisionProvider().get_revisions("AMD", 7)
        }
        thirty = {
            r.new_eps_estimate for r in SyntheticAnalystRevisionProvider().get_revisions("AMD", 30)
        }
        ninety = {
            r.new_eps_estimate for r in SyntheticAnalystRevisionProvider().get_revisions("AMD", 90)
        }
        assert seven <= thirty <= ninety

    def test_a_ticker_with_no_history_returns_empty(self) -> None:
        assert SyntheticAnalystRevisionProvider().get_revisions("ZZZZ", 90) == []

    def test_directions_are_reported_per_revision(self) -> None:
        revisions = SyntheticAnalystRevisionProvider().get_revisions("AMD", 90)
        directions = {r.direction for r in revisions}
        assert directions == {"UP", "DOWN"}


class TestIngestionPersistsTheFullHistory:
    def test_ingesting_the_90_day_window_writes_4_revision_rows(self, db_session: Session) -> None:
        amd = db_session.scalar(select(Instrument).where(Instrument.ticker == "AMD"))
        assert amd is not None
        # Use a fresh, distinguishable earnings_event_id so this test's
        # count assertion can't be polluted by any other seeded revision.
        fresh_event = EarningsEvent(
            instrument_id=amd.id,
            report_date=date(2026, 9, 1),
            source="test_fixture",
        )
        db_session.add(fresh_event)
        db_session.flush()

        created = ingest_analyst_revisions(
            db_session,
            SyntheticAnalystRevisionProvider(),
            earnings_event_id=fresh_event.id,
            ticker="AMD",
            window_days=90,
        )
        assert len(created) == 4

        stored = db_session.scalars(
            select(EarningsRevision).where(EarningsRevision.earnings_event_id == fresh_event.id)
        ).all()
        assert len(stored) == 4
        assert all(row.usable_at is not None for row in stored)
