"""Strategy-level performance breakdown tests (Revision Prompt 12) —
built through real manual-fill BUY/SELL round trips (Revision Prompt 8)
so `Trade.realized_pnl`/`Trade.lane` reflect the real accounting
engine, not hand-constructed rows."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tradingos_api.models.execution import Account
from tradingos_api.services.performance_strategy import (
    get_lane_contribution,
    get_policy_veto_outcomes,
    get_pre_event_vs_post_confirmation_contribution,
)


def _round_trip(
    client: TestClient, account_id: str, *, buy_price: str, sell_price: str, lane: str = "TACTICAL"
) -> None:
    now = datetime.now(UTC).isoformat()
    buy = client.post(
        f"/api/v1/portfolio/accounts/{account_id}/manual-fill",
        json={
            "side": "BUY",
            "ticker": "AMD",
            "quantity": "10",
            "price": buy_price,
            "executed_at": now,
            "lane": lane,
        },
    )
    assert buy.status_code == 201, buy.text
    sell = client.post(
        f"/api/v1/portfolio/accounts/{account_id}/manual-fill",
        json={
            "side": "SELL",
            "ticker": "AMD",
            "quantity": "10",
            "price": sell_price,
            "executed_at": now,
            "lane": lane,
        },
    )
    assert sell.status_code == 201, sell.text


class TestLaneContribution:
    def test_tactical_win_groups_under_tactical(
        self, client: TestClient, db_session: Session, fresh_account: Account
    ) -> None:
        _round_trip(
            client, str(fresh_account.id), buy_price="100.00", sell_price="120.00", lane="TACTICAL"
        )
        groups = get_lane_contribution(db_session, account_id=fresh_account.id)
        tactical = next((g for g in groups if g.group_key == "TACTICAL"), None)
        assert tactical is not None
        assert tactical.stats.num_trades == 1
        assert tactical.stats.num_wins == 1

    def test_no_trades_yields_empty_groups(
        self, db_session: Session, fresh_account: Account
    ) -> None:
        groups = get_lane_contribution(db_session, account_id=fresh_account.id)
        assert groups == []


class TestPreEventVsPostConfirmation:
    def test_manual_fill_with_no_attribution_is_unattributed(
        self, client: TestClient, db_session: Session, fresh_account: Account
    ) -> None:
        """A manual fill has no `RecommendationAttribution` row at all
        (it never went through the committee/pipeline) — it must be
        reported as its own explicit bucket, never silently dropped or
        mis-bucketed as one of the two real strategy stages."""
        _round_trip(client, str(fresh_account.id), buy_price="100.00", sell_price="90.00")
        groups = get_pre_event_vs_post_confirmation_contribution(
            db_session, account_id=fresh_account.id
        )
        assert len(groups) == 1
        assert groups[0].group_key == "UNATTRIBUTED"
        assert groups[0].stats.num_losses == 1


class TestPolicyVetoOutcomesSparse:
    def test_no_proposals_yields_zero_evaluations(
        self, db_session: Session, fresh_account: Account
    ) -> None:
        result = get_policy_veto_outcomes(db_session, account_id=fresh_account.id)
        assert result.total_evaluations == 0
        assert result.denial_reasons == {}
