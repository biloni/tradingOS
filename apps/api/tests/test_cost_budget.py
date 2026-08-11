"""Tests for the cost-budget-triggered kill switch (Revision Prompt 16)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from tradingos_api.core.config import get_settings
from tradingos_api.models.operations import ModelCallRecord
from tradingos_api.models.security_master import Instrument
from tradingos_api.policy.recommendation_modes import RecommendationMode
from tradingos_api.services.committee_orchestrator import CommitteeInputBundle, run_committee
from tradingos_api.services.cost_budget import (
    check_and_enforce_cost_budget,
    get_todays_llm_spend_usd,
)
from tradingos_api.services.order_authority import activate_kill_switch, is_kill_switch_active

from .test_committee_orchestrator import (
    _INVESTMENT_ANALYST_ARGS,
    _INVESTMENT_CIO_BUY_ARGS,
    _make_fake_llm,
)

_NOW = datetime(2026, 8, 11, 12, 0, tzinfo=UTC)


def _make_call_record(db: Session, *, cost_usd: Decimal, created_at: datetime) -> ModelCallRecord:
    record = ModelCallRecord(
        prompt_version_label="test-v1",
        model="claude-test",
        input_tokens=100,
        output_tokens=100,
        cost_usd=cost_usd,
        latency_ms=500,
        stop_reason="end_turn",
        created_at=created_at,
    )
    db.add(record)
    db.flush()
    return record


class TestGetTodaysLlmSpend:
    def test_sums_only_todays_records(self, db_session: Session) -> None:
        _make_call_record(db_session, cost_usd=Decimal("1.00"), created_at=_NOW)
        _make_call_record(
            db_session, cost_usd=Decimal("2.00"), created_at=_NOW - timedelta(hours=1)
        )
        _make_call_record(
            db_session, cost_usd=Decimal("50.00"), created_at=_NOW - timedelta(days=1)
        )
        spend = get_todays_llm_spend_usd(db_session, now=_NOW)
        assert spend == Decimal("3.00")

    def test_zero_when_no_records_today(self, db_session: Session) -> None:
        _make_call_record(
            db_session, cost_usd=Decimal("50.00"), created_at=_NOW - timedelta(days=1)
        )
        spend = get_todays_llm_spend_usd(db_session, now=_NOW)
        assert spend == Decimal("0")


class TestCheckAndEnforceCostBudget:
    def test_no_op_when_under_budget(
        self, db_session: Session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("DAILY_LLM_COST_BUDGET_USD", "5.00")
        get_settings.cache_clear()
        try:
            _make_call_record(db_session, cost_usd=Decimal("1.00"), created_at=_NOW)
            tripped = check_and_enforce_cost_budget(db_session, now=_NOW)
            assert tripped is False
            assert is_kill_switch_active(db_session) is False
        finally:
            get_settings.cache_clear()

    def test_trips_kill_switch_when_over_budget(
        self, db_session: Session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("DAILY_LLM_COST_BUDGET_USD", "5.00")
        get_settings.cache_clear()
        try:
            _make_call_record(db_session, cost_usd=Decimal("6.00"), created_at=_NOW)
            tripped = check_and_enforce_cost_budget(db_session, now=_NOW)
            assert tripped is True
            assert is_kill_switch_active(db_session) is True
        finally:
            get_settings.cache_clear()

    def test_exactly_at_budget_trips(
        self, db_session: Session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("DAILY_LLM_COST_BUDGET_USD", "5.00")
        get_settings.cache_clear()
        try:
            _make_call_record(db_session, cost_usd=Decimal("5.00"), created_at=_NOW)
            tripped = check_and_enforce_cost_budget(db_session, now=_NOW)
            assert tripped is True
        finally:
            get_settings.cache_clear()

    def test_does_not_reactivate_or_touch_an_already_active_switch(
        self, db_session: Session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("DAILY_LLM_COST_BUDGET_USD", "5.00")
        get_settings.cache_clear()
        try:
            existing = activate_kill_switch(
                db_session, activated_by="human:test", reason="manual test activation", now=_NOW
            )
            db_session.flush()
            _make_call_record(db_session, cost_usd=Decimal("100.00"), created_at=_NOW)

            tripped = check_and_enforce_cost_budget(db_session, now=_NOW)

            assert tripped is False
            assert existing.reason == "manual test activation"
            assert existing.activated_by == "human:test"
        finally:
            get_settings.cache_clear()


class TestCostBudgetEndpoint:
    def test_reports_spend_and_budget(
        self, client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("DAILY_LLM_COST_BUDGET_USD", "10.00")
        get_settings.cache_clear()
        try:
            _make_call_record(db_session, cost_usd=Decimal("3.00"), created_at=datetime.now(UTC))
            db_session.commit()

            response = client.get("/api/v1/ops/cost-budget")
            assert response.status_code == 200
            body = response.json()
            assert Decimal(body["daily_spend_usd"]) == Decimal("3.00")
            assert Decimal(body["daily_budget_usd"]) == Decimal("10.00")
            assert Decimal(body["budget_remaining_usd"]) == Decimal("7.00")
            assert body["kill_switch_active"] is False
        finally:
            get_settings.cache_clear()

    def test_requires_authentication(self) -> None:
        from fastapi.testclient import TestClient as RawTestClient

        from tradingos_api.main import app

        raw_client = RawTestClient(app)
        response = raw_client.get("/api/v1/ops/cost-budget")
        assert response.status_code == 401


class TestCommitteeRunTripsOverBudget:
    """Integration: `run_committee()` actually calls the enforcement
    hook, not just a unit-level check of `services/cost_budget.py` in
    isolation."""

    def test_run_completes_normally_and_trips_the_switch_for_the_next_run(
        self, db_session: Session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("DAILY_LLM_COST_BUDGET_USD", "0.01")
        get_settings.cache_clear()
        try:
            from datetime import date

            instrument = db_session.scalar(select(Instrument).limit(1))
            assert instrument is not None

            cio_args = dict(_INVESTMENT_CIO_BUY_ARGS)
            cio_args["review_date"] = date.today().isoformat()
            llm = _make_fake_llm(_INVESTMENT_ANALYST_ARGS, cio_args)

            bundle = CommitteeInputBundle(
                instrument_id=instrument.id,
                symbol="TEST",
                as_of=datetime.now(UTC),
                evidence_cutoff=datetime.now(UTC),
                evidence=[],
                deterministic_feature_ids=["feat-1"],
                deterministic_summary="n/a",
                hard_veto_active=False,
                hard_veto_reason=None,
            )

            assert is_kill_switch_active(db_session) is False

            result = run_committee(
                db_session,
                lane=RecommendationMode.INVESTMENT,
                bundle=bundle,
                llm=llm,
                cost_ceiling_usd=Decimal("5.00"),
                per_call_timeout_seconds=30,
                triggered_by="TEST",
            )

            # The run itself still completed and wrote a recommendation —
            # a budget trip stops the *next* run, never corrupts the one
            # that pushed spend over the line.
            assert result.recommendation is not None
            assert result.cost_budget_tripped is True
            assert is_kill_switch_active(db_session) is True
        finally:
            get_settings.cache_clear()
