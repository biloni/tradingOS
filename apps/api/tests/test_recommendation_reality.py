"""Recommendation-vs-reality tests (Revision Prompt 12) — known vectors
for `compute_hypothetical_outcome()` (the "hypothetical-fill edge
cases" required test category) plus a DB-level smoke test for
`get_recommendation_reality_rows()`."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from tradingos_api.models.execution import Account
from tradingos_api.models.recommendations import Recommendation
from tradingos_api.models.security_master import Instrument
from tradingos_api.services.recommendation_reality import (
    compute_hypothetical_outcome,
    get_recommendation_reality_rows,
)

_OPENED = date(2026, 6, 1)


class TestEntryNeverReached:
    def test_price_stays_above_entry_zone(self) -> None:
        bars = [
            (date(2026, 6, 2), Decimal("105"), Decimal("108"), Decimal("107")),
            (date(2026, 6, 3), Decimal("106"), Decimal("109"), Decimal("108")),
        ]
        result = compute_hypothetical_outcome(
            entry_price=Decimal(100),
            stop_price=Decimal(95),
            target_prices=[Decimal(110)],
            opened_at=_OPENED,
            bars=bars,
            entry_window_days=3,
        )
        assert result.entry_reachable is False
        assert result.simulated_exit_reason == "ENTRY_NEVER_REACHED"
        assert result.simulated_pnl_pct is None

    def test_entry_reached_outside_the_window_still_counts_as_never_reached(self) -> None:
        # The zone is touched, but only after the entry window has closed.
        bars = [
            (date(2026, 6, 2), Decimal("105"), Decimal("108"), Decimal("107")),
            (date(2026, 6, 10), Decimal("99"), Decimal("101"), Decimal("100")),
        ]
        result = compute_hypothetical_outcome(
            entry_price=Decimal(100),
            stop_price=Decimal(95),
            target_prices=[Decimal(110)],
            opened_at=_OPENED,
            bars=bars,
            entry_window_days=3,
        )
        assert result.entry_reachable is False


class TestStopHit:
    def test_known_vector_stop_loss(self) -> None:
        bars = [
            (date(2026, 6, 2), Decimal(99), Decimal(101), Decimal(100)),  # entry reached
            (date(2026, 6, 3), Decimal(94), Decimal(96), Decimal(95)),  # stop hit
        ]
        result = compute_hypothetical_outcome(
            entry_price=Decimal(100),
            stop_price=Decimal(95),
            target_prices=[Decimal(110)],
            opened_at=_OPENED,
            bars=bars,
        )
        assert result.entry_reachable is True
        assert result.simulated_exit_reason == "STOP"
        assert result.simulated_exit_price == Decimal(95)
        assert result.simulated_pnl_pct == Decimal("-5.00")


class TestTargetHit:
    def test_known_vector_target(self) -> None:
        bars = [
            (date(2026, 6, 2), Decimal(99), Decimal(101), Decimal(100)),
            (date(2026, 6, 3), Decimal(105), Decimal(111), Decimal(110)),
        ]
        result = compute_hypothetical_outcome(
            entry_price=Decimal(100),
            stop_price=Decimal(95),
            target_prices=[Decimal(110)],
            opened_at=_OPENED,
            bars=bars,
        )
        assert result.simulated_exit_reason == "TARGET"
        assert result.simulated_exit_price == Decimal(110)
        assert result.simulated_pnl_pct == Decimal("10.00")

    def test_stop_and_target_both_touched_same_bar_stop_wins(self) -> None:
        """A single wide-range bar that touches both the stop and the
        target is ambiguous about which happened first intraday — this
        function resolves the ambiguity conservatively by checking the
        stop first, the same "assume the worse outcome under ambiguity"
        principle `services/hard_vetoes.py` applies elsewhere in this
        codebase."""
        bars = [
            (date(2026, 6, 2), Decimal(99), Decimal(101), Decimal(100)),
            (date(2026, 6, 3), Decimal(90), Decimal(120), Decimal(100)),
        ]
        result = compute_hypothetical_outcome(
            entry_price=Decimal(100),
            stop_price=Decimal(95),
            target_prices=[Decimal(110)],
            opened_at=_OPENED,
            bars=bars,
        )
        assert result.simulated_exit_reason == "STOP"


class TestTimeExit:
    def test_neither_stop_nor_target_hit_within_max_holding_days(self) -> None:
        bars = [(date(2026, 6, 2), Decimal(99), Decimal(101), Decimal(100))]
        for i in range(3, 3 + 12):
            bars.append((date(2026, 6, i), Decimal(99), Decimal(102), Decimal(101)))
        result = compute_hypothetical_outcome(
            entry_price=Decimal(100),
            stop_price=Decimal(90),
            target_prices=[Decimal(130)],
            opened_at=_OPENED,
            bars=bars,
            max_holding_days=5,
        )
        assert result.simulated_exit_reason == "TIME_EXIT"

    def test_running_out_of_history_before_any_exit_condition(self) -> None:
        bars = [
            (date(2026, 6, 2), Decimal(99), Decimal(101), Decimal(100)),
            (date(2026, 6, 3), Decimal(99), Decimal(102), Decimal(101)),
        ]
        result = compute_hypothetical_outcome(
            entry_price=Decimal(100),
            stop_price=Decimal(80),
            target_prices=[Decimal(200)],
            opened_at=_OPENED,
            bars=bars,
            max_holding_days=30,
        )
        assert result.simulated_exit_reason == "END_OF_HISTORY"
        assert result.simulated_exit_price == Decimal(101)


class TestNoStopOrTargetConfigured:
    def test_only_time_exit_is_reachable(self) -> None:
        bars = [(date(2026, 6, 2), Decimal(99), Decimal(101), Decimal(100))]
        for i in range(3, 15):
            bars.append((date(2026, 6, i), Decimal(99), Decimal(102), Decimal(101)))
        result = compute_hypothetical_outcome(
            entry_price=Decimal(100),
            stop_price=None,
            target_prices=[],
            opened_at=_OPENED,
            bars=bars,
            max_holding_days=5,
        )
        assert result.simulated_exit_reason == "TIME_EXIT"


class TestRecommendationRealityRowsSparse:
    def test_recommendation_with_no_outcome_yet_is_pending(
        self, db_session: Session, fresh_account: Account
    ) -> None:
        amd = db_session.scalar(select(Instrument).where(Instrument.ticker == "AMD"))
        assert amd is not None
        from datetime import UTC, datetime

        from tradingos_api.models.enums import RecommendationMode, RecommendationStatus

        rec = Recommendation(
            instrument_id=amd.id,
            mode=RecommendationMode.TACTICAL,
            opened_at=datetime.now(UTC),
            status=RecommendationStatus.ACTIVE,
        )
        db_session.add(rec)
        db_session.flush()

        rows = get_recommendation_reality_rows(db_session)
        row = next(r for r in rows if r.recommendation_id == rec.id)
        assert row.disposition == "PENDING"
        assert row.actual_pnl is None
        assert row.hypothetical_pnl_pct is None
