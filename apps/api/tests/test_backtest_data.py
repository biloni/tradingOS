"""Synthetic backtest universe generator tests (Revision Prompt 13) —
determinism is the load-bearing property this module's entire honesty
claim depends on ("re-running produces byte-identical bars/events")."""

from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from tradingos_api.services.backtest_data import (
    BENCHMARK_TICKER,
    DEFAULT_UNIVERSE_TICKERS,
    generate_synthetic_universe,
)

_START = date(2024, 8, 1)
_END = date(2025, 1, 31)


class TestDeterminism:
    def test_identical_seed_produces_identical_bars(self, db_session: Session) -> None:
        first = generate_synthetic_universe(db_session, start=_START, end=_END, seed=42)
        second = generate_synthetic_universe(db_session, start=_START, end=_END, seed=42)
        assert first.instruments[0].bars == second.instruments[0].bars
        assert first.instruments[0].earnings_events == second.instruments[0].earnings_events
        assert first.benchmark.bars == second.benchmark.bars

    def test_different_seed_produces_different_bars(self, db_session: Session) -> None:
        first = generate_synthetic_universe(db_session, start=_START, end=_END, seed=42)
        second = generate_synthetic_universe(db_session, start=_START, end=_END, seed=7)
        assert first.instruments[0].bars != second.instruments[0].bars


class TestUniverseShape:
    def test_covers_every_requested_ticker_present_in_seed_data(self, db_session: Session) -> None:
        universe = generate_synthetic_universe(db_session, start=_START, end=_END)
        tickers = {i.ticker for i in universe.instruments}
        assert tickers == set(DEFAULT_UNIVERSE_TICKERS)

    def test_benchmark_is_spy_and_has_no_earnings_events(self, db_session: Session) -> None:
        universe = generate_synthetic_universe(db_session, start=_START, end=_END)
        assert universe.benchmark.ticker == BENCHMARK_TICKER
        assert universe.benchmark.earnings_events == []

    def test_every_instrument_has_at_least_one_earnings_event_over_6_months(
        self, db_session: Session
    ) -> None:
        universe = generate_synthetic_universe(db_session, start=_START, end=_END)
        for instrument in universe.instruments:
            assert len(instrument.earnings_events) >= 1

    def test_bars_are_ordered_and_weekday_only(self, db_session: Session) -> None:
        universe = generate_synthetic_universe(db_session, start=_START, end=_END)
        bars = universe.instruments[0].bars
        dates = [b.as_of for b in bars]
        assert dates == sorted(dates)
        assert all(d.weekday() < 5 for d in dates)

    def test_narrower_ticker_subset_returns_only_those_instruments(
        self, db_session: Session
    ) -> None:
        universe = generate_synthetic_universe(
            db_session, start=_START, end=_END, tickers=("AMD", "TSM")
        )
        assert {i.ticker for i in universe.instruments} == {"AMD", "TSM"}
