"""Live-portfolio performance service tests (Revision Prompt 12) —
built through the real manual-fill endpoint (Revision Prompt 8) so the
equity curve reflects an actual `Execution`/`CashLedgerEntry` history,
not hand-constructed rows that could drift from what the accounting
engine actually writes."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from tradingos_api.models.execution import Account
from tradingos_api.models.market_evidence import MarketBar
from tradingos_api.models.security_master import Instrument
from tradingos_api.services.performance_portfolio import (
    get_equity_curve,
    get_portfolio_performance,
)


def _seed_amd_bar(db_session: Session, *, as_of, close: Decimal) -> None:
    amd = db_session.scalar(select(Instrument).where(Instrument.ticker == "AMD"))
    assert amd is not None
    db_session.add(
        MarketBar(
            instrument_id=amd.id,
            as_of=as_of,
            timeframe="DAILY",
            open=close,
            high=close,
            low=close,
            close=close,
            volume=1_000_000,
            source="test_fixture",
            observed_at=datetime.combine(as_of, datetime.min.time(), tzinfo=UTC),
        )
    )
    db_session.flush()


class TestEquityCurveNoPositions:
    def test_flat_account_equals_starting_cash(
        self, db_session: Session, fresh_account: Account
    ) -> None:
        today = datetime.now(UTC).date()
        curve = get_equity_curve(
            db_session, account=fresh_account, start=today - timedelta(days=5), end=today
        )
        assert len(curve) > 0
        for point in curve:
            assert point.equity == fresh_account.starting_cash
            assert point.market_value == Decimal(0)


class TestEquityCurveWithAnOpenPosition:
    def test_open_position_market_value_uses_last_known_close(
        self, client: TestClient, db_session: Session, fresh_account: Account
    ) -> None:
        today = datetime.now(UTC).date()
        _seed_amd_bar(db_session, as_of=today - timedelta(days=1), close=Decimal("150.00"))

        response = client.post(
            f"/api/v1/portfolio/accounts/{fresh_account.id}/manual-fill",
            json={
                "side": "BUY",
                "ticker": "AMD",
                "quantity": "10",
                "price": "100.00",
                "executed_at": (datetime.now(UTC) - timedelta(days=2)).isoformat(),
                "lane": "TACTICAL",
            },
        )
        assert response.status_code == 201, response.text

        performance = get_portfolio_performance(db_session, account=fresh_account, as_of=today)
        # Cash went down by 10*100=1000, market value = 10 * last known close (150).
        assert performance.cash == fresh_account.starting_cash - Decimal(1000)
        assert performance.market_value == Decimal("1500.00")
        assert performance.equity == performance.cash + performance.market_value
        assert performance.unrealized_pnl == Decimal("500.00")  # (150-100)*10


class TestSparsePortfolioSamples:
    def test_no_closed_trades_yields_none_trade_stats(
        self, db_session: Session, fresh_account: Account
    ) -> None:
        today = datetime.now(UTC).date()
        performance = get_portfolio_performance(db_session, account=fresh_account, as_of=today)
        assert performance.trade_stats.num_trades == 0
        assert performance.trade_stats.win_rate_pct is None
        assert performance.sharpe_ratio is None  # not enough return observations yet

    def test_open_position_pnl_excluded_from_trade_stats(
        self, client: TestClient, db_session: Session, fresh_account: Account
    ) -> None:
        """A position that is still open must never contribute to
        win-rate/profit-factor — only a *closed* `Trade.realized_pnl`
        counts, matching `compute_trade_stats()`'s own documented
        contract. This is the "open positions" required test category."""
        today = datetime.now(UTC).date()
        _seed_amd_bar(db_session, as_of=today, close=Decimal("200.00"))
        client.post(
            f"/api/v1/portfolio/accounts/{fresh_account.id}/manual-fill",
            json={
                "side": "BUY",
                "ticker": "AMD",
                "quantity": "5",
                "price": "100.00",
                "executed_at": datetime.now(UTC).isoformat(),
                "lane": "TACTICAL",
            },
        )
        performance = get_portfolio_performance(db_session, account=fresh_account, as_of=today)
        assert performance.trade_stats.num_trades == 0
        assert performance.unrealized_pnl == Decimal("500.00")  # (200-100)*5, unrealized only
        assert performance.realized_pnl == Decimal(0)
