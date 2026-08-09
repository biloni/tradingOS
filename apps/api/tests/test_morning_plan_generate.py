"""Morning plan generation orchestrator tests (Revision Prompt 9) — the
required "provider partial outage," "required data stale," "no
qualified trades," "existing position requiring action," and "evidence
reproducibility" categories.

Every test here injects its own `recommendation_lookup` callable rather
than relying on `default_recommendation_lookup` against whatever
committee/pipeline rows other tests or demo scripts may have already
committed to the shared dev database — this keeps each scenario fully
deterministic and isolated. A watchlist entry with no matching entry in
the injected lookup dict models exactly what a live provider/committee
outage looks like to this orchestrator: `lookup(...)` returns `None`,
and stage 9's candidate is created with `version=None`, `lane_action=None`
— skipped, never crashing the run and never fabricating an action."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from tradingos_api.models.enums import (
    LotLane,
    MorningPlanRunStatus,
    MorningPlanSectionKey,
    MorningPlanVersionLabel,
    OrderSide,
    OrderStatus,
    OrderType,
    RecommendationAction,
    RecommendationConfidence,
    RecommendationMode,
)
from tradingos_api.models.execution import Account, Execution, Order
from tradingos_api.models.morning_plan import (
    MorningPlanInputLink,
    MorningPlanItem,
    MorningPlanQualityCheck,
    MorningPlanRun,
    MorningPlanSection,
)
from tradingos_api.models.recommendations import Recommendation, RecommendationVersion
from tradingos_api.models.security_master import Instrument, Watchlist, WatchlistItem
from tradingos_api.services.morning_plan_generate import (
    STALE_RECOMMENDATION_AGE,
    generate_morning_plan,
)
from tradingos_api.services.portfolio_accounting import apply_buy_execution

_PLAN_DATE = datetime(2026, 8, 11).date()  # a plain Tuesday


def _instrument(db: Session, ticker: str) -> Instrument:
    inst = db.scalar(select(Instrument).where(Instrument.ticker == ticker))
    assert inst is not None, f"seed data must include {ticker}"
    return inst


def _make_run(db: Session, *, plan_date: object = _PLAN_DATE) -> MorningPlanRun:
    run = MorningPlanRun(
        plan_date=plan_date,
        triggered_by="test",
        status=MorningPlanRunStatus.RUNNING,
        started_at=datetime.now(UTC),
    )
    db.add(run)
    db.flush()
    return run


def _add_to_watchlist(db: Session, *, owner_user_id: uuid.UUID, instrument_id: uuid.UUID) -> None:
    watchlist = Watchlist(owner_user_id=owner_user_id, name=f"test-{uuid.uuid4()}")
    db.add(watchlist)
    db.flush()
    db.add(
        WatchlistItem(
            watchlist_id=watchlist.id,
            instrument_id=instrument_id,
            added_at=datetime.now(UTC).date(),
        )
    )
    db.flush()


def _make_recommendation_version(
    db: Session,
    *,
    instrument_id: uuid.UUID,
    mode: RecommendationMode,
    lane_action: str | None,
    generated_at: datetime,
) -> RecommendationVersion:
    rec = Recommendation(instrument_id=instrument_id, mode=mode, opened_at=generated_at)
    db.add(rec)
    db.flush()
    version = RecommendationVersion(
        recommendation_id=rec.id,
        version_number=1,
        action=RecommendationAction.HOLD,
        lane_action=lane_action,
        confidence=RecommendationConfidence.MEDIUM,
        rationale="test fixture",
        generated_at=generated_at,
        deterministic_inputs_snapshot={},
    )
    db.add(version)
    db.flush()
    return version


def _make_lookup(
    versions: dict[tuple[uuid.UUID, RecommendationMode], RecommendationVersion],
) -> object:
    def _lookup(
        db: Session, *, instrument_id: uuid.UUID, mode: RecommendationMode
    ) -> RecommendationVersion | None:
        return versions.get((instrument_id, mode))

    return _lookup


def _items_by_section(
    db: Session, section_key: MorningPlanSectionKey, version_id: uuid.UUID
) -> list[MorningPlanItem]:
    section = db.scalar(
        select(MorningPlanSection).where(
            MorningPlanSection.morning_plan_version_id == version_id,
            MorningPlanSection.section_key == section_key,
        )
    )
    if section is None:
        return []
    return list(
        db.scalars(
            select(MorningPlanItem).where(MorningPlanItem.morning_plan_section_id == section.id)
        ).all()
    )


class TestProviderPartialOutage:
    def test_an_instrument_with_no_available_recommendation_is_skipped_not_crashed(
        self, db_session: Session, fresh_account: Account
    ) -> None:
        healthy = _instrument(db_session, "AAPL")
        outaged = _instrument(db_session, "ADI")
        _add_to_watchlist(
            db_session, owner_user_id=fresh_account.owner_user_id, instrument_id=healthy.id
        )
        _add_to_watchlist(
            db_session, owner_user_id=fresh_account.owner_user_id, instrument_id=outaged.id
        )
        now = datetime.now(UTC)
        healthy_version = _make_recommendation_version(
            db_session,
            instrument_id=healthy.id,
            mode=RecommendationMode.INVESTMENT,
            lane_action="INVEST_BUY",
            generated_at=now,
        )
        # `outaged` has no entry in the lookup dict at all — models a
        # provider/committee outage for that one symbol specifically.
        lookup = _make_lookup({(healthy.id, RecommendationMode.INVESTMENT): healthy_version})

        run = _make_run(db_session)
        result = generate_morning_plan(
            db_session,
            run=run,
            plan_date=_PLAN_DATE,
            version_label=MorningPlanVersionLabel.AD_HOC,
            version_number=1,
            now=now,
            account_id=fresh_account.id,
            recommendation_lookup=lookup,
        )

        assert result.skipped is False
        assert result.version is not None
        approval_items = _items_by_section(
            db_session, MorningPlanSectionKey.APPROVAL_REQUIRED, result.version.id
        )
        headlines = {item.headline for item in approval_items}
        assert any("AAPL" in h for h in headlines)
        assert not any("ADI" in h for h in headlines)
        # No Data Problems entry either — an outage (no data at all) is
        # distinct from stale data (data that exists but is too old);
        # only the latter is modeled as a quality-check failure here.
        data_problem_items = _items_by_section(
            db_session, MorningPlanSectionKey.DATA_PROBLEMS, result.version.id
        )
        assert not any("ADI" in item.headline for item in data_problem_items)


class TestRequiredDataStale:
    def test_a_stale_recommendation_is_routed_to_data_problems_not_shown_as_actionable(
        self, db_session: Session, fresh_account: Account
    ) -> None:
        instrument = _instrument(db_session, "AMAT")
        _add_to_watchlist(
            db_session, owner_user_id=fresh_account.owner_user_id, instrument_id=instrument.id
        )
        now = datetime.now(UTC)
        stale_generated_at = now - STALE_RECOMMENDATION_AGE - timedelta(hours=1)
        stale_version = _make_recommendation_version(
            db_session,
            instrument_id=instrument.id,
            mode=RecommendationMode.TACTICAL,
            lane_action="TRADE_ENTER",  # would otherwise be actionable
            generated_at=stale_generated_at,
        )
        lookup = _make_lookup({(instrument.id, RecommendationMode.TACTICAL): stale_version})

        run = _make_run(db_session)
        result = generate_morning_plan(
            db_session,
            run=run,
            plan_date=_PLAN_DATE,
            version_label=MorningPlanVersionLabel.AD_HOC,
            version_number=1,
            now=now,
            account_id=fresh_account.id,
            recommendation_lookup=lookup,
        )

        assert result.version is not None
        approval_items = _items_by_section(
            db_session, MorningPlanSectionKey.APPROVAL_REQUIRED, result.version.id
        )
        assert not any("AMAT" in item.headline for item in approval_items)
        data_problem_items = _items_by_section(
            db_session, MorningPlanSectionKey.DATA_PROBLEMS, result.version.id
        )
        assert any("AMAT" in item.headline for item in data_problem_items)
        quality_checks = db_session.scalars(
            select(MorningPlanQualityCheck).where(
                MorningPlanQualityCheck.morning_plan_version_id == result.version.id
            )
        ).all()
        stale_checks = [
            c for c in quality_checks if c.check_name.startswith("stale_recommendation:")
        ]
        assert len(stale_checks) == 1
        assert stale_checks[0].passed is False
        assert "AMAT" in stale_checks[0].detail

    def test_a_stale_majority_marks_the_plan_incomplete(
        self, db_session: Session, fresh_account: Account, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from tradingos_api.models.enums import PlanCompletenessStatus
        from tradingos_api.services import morning_plan_generate as morning_plan_generate_module

        instrument = _instrument(db_session, "AVGO")
        # `_watchlist_instruments()` reads every `WatchlistItem` row in
        # the database rather than scoping to one account (Revision
        # Prompt 9's own scope, not this test's concern) — deleting real
        # rows would hit `recommendations.watchlist_item_id`'s FK, so
        # this test isolates its candidate set by substituting the
        # module's own watchlist lookup for the duration of the test,
        # making the stale-percentage math deterministic regardless of
        # whatever else the shared dev database already has watchlisted.
        monkeypatch.setattr(
            morning_plan_generate_module,
            "_watchlist_instruments",
            lambda db, account_id: [instrument],
        )
        now = datetime.now(UTC)
        stale_version = _make_recommendation_version(
            db_session,
            instrument_id=instrument.id,
            mode=RecommendationMode.INVESTMENT,
            lane_action="INVEST_BUY",
            generated_at=now - STALE_RECOMMENDATION_AGE - timedelta(hours=1),
        )
        # The one watchlist instrument yields two candidates (INVESTMENT
        # + TACTICAL); TACTICAL returns no data via the lookup, so the
        # single stale INVESTMENT candidate is 50% of the total —
        # comfortably over the 10% incomplete threshold.
        lookup = _make_lookup({(instrument.id, RecommendationMode.INVESTMENT): stale_version})

        run = _make_run(db_session)
        result = generate_morning_plan(
            db_session,
            run=run,
            plan_date=_PLAN_DATE,
            version_label=MorningPlanVersionLabel.AD_HOC,
            version_number=1,
            now=now,
            account_id=fresh_account.id,
            recommendation_lookup=lookup,
        )
        assert result.version is not None
        assert result.version.completeness_status == PlanCompletenessStatus.INCOMPLETE


class TestNoQualifiedTrades:
    def test_no_action_recommendations_produce_no_actionable_items_without_crashing(
        self, db_session: Session, fresh_account: Account
    ) -> None:
        instrument = _instrument(db_session, "CRM")
        _add_to_watchlist(
            db_session, owner_user_id=fresh_account.owner_user_id, instrument_id=instrument.id
        )
        now = datetime.now(UTC)
        no_action_version = _make_recommendation_version(
            db_session,
            instrument_id=instrument.id,
            mode=RecommendationMode.INVESTMENT,
            lane_action="NO_ACTION",
            generated_at=now,
        )
        lookup = _make_lookup({(instrument.id, RecommendationMode.INVESTMENT): no_action_version})

        run = _make_run(db_session)
        result = generate_morning_plan(
            db_session,
            run=run,
            plan_date=_PLAN_DATE,
            version_label=MorningPlanVersionLabel.AD_HOC,
            version_number=1,
            now=now,
            account_id=fresh_account.id,
            recommendation_lookup=lookup,
        )

        assert result.skipped is False
        assert result.version is not None
        for section_key in (
            MorningPlanSectionKey.ACT_NOW,
            MorningPlanSectionKey.APPROVAL_REQUIRED,
        ):
            items = _items_by_section(db_session, section_key, result.version.id)
            assert not any("CRM" in item.headline for item in items)

    def test_an_entirely_empty_watchlist_still_produces_a_valid_complete_plan(
        self, db_session: Session, fresh_account: Account
    ) -> None:
        from tradingos_api.models.enums import PlanCompletenessStatus

        run = _make_run(db_session)
        now = datetime.now(UTC)
        result = generate_morning_plan(
            db_session,
            run=run,
            plan_date=_PLAN_DATE,
            version_label=MorningPlanVersionLabel.AD_HOC,
            version_number=1,
            now=now,
            account_id=fresh_account.id,
            recommendation_lookup=_make_lookup({}),
        )
        assert result.skipped is False
        assert result.version is not None
        # Zero total candidates must not divide by zero or otherwise
        # blow up completeness math — a normal, honestly-labeled result.
        assert result.version.completeness_status == PlanCompletenessStatus.COMPLETE


class TestExistingPositionRequiringAction:
    def test_a_held_lot_whose_source_recommendation_says_exit_is_routed_to_act_now(
        self, db_session: Session, fresh_account: Account
    ) -> None:
        instrument = _instrument(db_session, "AMD")
        now = datetime.now(UTC)
        exit_version = _make_recommendation_version(
            db_session,
            instrument_id=instrument.id,
            mode=RecommendationMode.TACTICAL,
            lane_action="TRADE_EXIT",
            generated_at=now,
        )
        order = Order(
            account_id=fresh_account.id,
            instrument_id=instrument.id,
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=Decimal(10),
            status=OrderStatus.FILLED,
        )
        db_session.add(order)
        db_session.flush()
        execution = Execution(
            order_id=order.id, quantity=Decimal(10), price=Decimal(100), executed_at=now
        )
        db_session.add(execution)
        db_session.flush()
        apply_buy_execution(
            db_session,
            execution=execution,
            account_id=fresh_account.id,
            instrument_id=instrument.id,
            lane=LotLane.TACTICAL,
            source_recommendation_version_id=exit_version.id,
        )

        run = _make_run(db_session)
        result = generate_morning_plan(
            db_session,
            run=run,
            plan_date=_PLAN_DATE,
            version_label=MorningPlanVersionLabel.AD_HOC,
            version_number=1,
            now=now,
            account_id=fresh_account.id,
            recommendation_lookup=_make_lookup({}),
        )

        assert result.version is not None
        act_now_items = _items_by_section(
            db_session, MorningPlanSectionKey.ACT_NOW, result.version.id
        )
        matching = [item for item in act_now_items if "AMD" in item.headline]
        assert matching, f"expected an AMD Act Now item, got: {[i.headline for i in act_now_items]}"
        assert matching[0].action_label == "TRADE_EXIT"

    def test_a_held_lot_with_a_routine_hold_action_is_not_forced_into_act_now(
        self, db_session: Session, fresh_account: Account
    ) -> None:
        instrument = _instrument(db_session, "ARM")
        now = datetime.now(UTC)
        hold_version = _make_recommendation_version(
            db_session,
            instrument_id=instrument.id,
            mode=RecommendationMode.INVESTMENT,
            lane_action="INVEST_HOLD",
            generated_at=now,
        )
        order = Order(
            account_id=fresh_account.id,
            instrument_id=instrument.id,
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=Decimal(5),
            status=OrderStatus.FILLED,
        )
        db_session.add(order)
        db_session.flush()
        execution = Execution(
            order_id=order.id, quantity=Decimal(5), price=Decimal(50), executed_at=now
        )
        db_session.add(execution)
        db_session.flush()
        apply_buy_execution(
            db_session,
            execution=execution,
            account_id=fresh_account.id,
            instrument_id=instrument.id,
            lane=LotLane.INVESTMENT,
            source_recommendation_version_id=hold_version.id,
        )

        run = _make_run(db_session)
        result = generate_morning_plan(
            db_session,
            run=run,
            plan_date=_PLAN_DATE,
            version_label=MorningPlanVersionLabel.AD_HOC,
            version_number=1,
            now=now,
            account_id=fresh_account.id,
            recommendation_lookup=_make_lookup({}),
        )
        assert result.version is not None
        act_now_items = _items_by_section(
            db_session, MorningPlanSectionKey.ACT_NOW, result.version.id
        )
        assert not any("ARM" in item.headline for item in act_now_items)
        hold_items = _items_by_section(
            db_session, MorningPlanSectionKey.BUY_AND_HOLD, result.version.id
        )
        assert any("ARM" in item.headline for item in hold_items)


class TestEvidenceReproducibility:
    def test_two_runs_against_identical_stored_inputs_produce_identical_classification(
        self, db_session: Session, fresh_account: Account
    ) -> None:
        instrument = _instrument(db_session, "BAC")
        _add_to_watchlist(
            db_session, owner_user_id=fresh_account.owner_user_id, instrument_id=instrument.id
        )
        frozen_now = datetime.now(UTC)
        version = _make_recommendation_version(
            db_session,
            instrument_id=instrument.id,
            mode=RecommendationMode.INVESTMENT,
            lane_action="INVEST_BUY",
            generated_at=frozen_now,
        )
        lookup = _make_lookup({(instrument.id, RecommendationMode.INVESTMENT): version})

        run_a = _make_run(db_session)
        result_a = generate_morning_plan(
            db_session,
            run=run_a,
            plan_date=_PLAN_DATE,
            version_label=MorningPlanVersionLabel.AD_HOC,
            version_number=1,
            now=frozen_now,
            account_id=fresh_account.id,
            recommendation_lookup=lookup,
        )
        run_b = _make_run(db_session)
        result_b = generate_morning_plan(
            db_session,
            run=run_b,
            plan_date=_PLAN_DATE,
            version_label=MorningPlanVersionLabel.AD_HOC,
            version_number=2,
            now=frozen_now,
            account_id=fresh_account.id,
            recommendation_lookup=lookup,
        )

        assert result_a.version is not None
        assert result_b.version is not None
        assert result_a.version.completeness_status == result_b.version.completeness_status
        assert [s.stage_name for s in result_a.stage_log] == [
            s.stage_name for s in result_b.stage_log
        ]

        a_items = _items_by_section(
            db_session, MorningPlanSectionKey.APPROVAL_REQUIRED, result_a.version.id
        )
        b_items = _items_by_section(
            db_session, MorningPlanSectionKey.APPROVAL_REQUIRED, result_b.version.id
        )
        a_headlines = sorted(item.headline for item in a_items)
        b_headlines = sorted(item.headline for item in b_items)
        assert a_headlines == b_headlines
        assert any("BAC" in h for h in a_headlines)

        # The exact recommendation version consulted is captured in the
        # input-link manifest both times, identically — the property
        # that makes "reproducible from stored inputs" a checkable fact
        # rather than an assertion about behavior.
        a_links = {
            link.input_id
            for link in db_session.scalars(
                select(MorningPlanInputLink).where(
                    MorningPlanInputLink.morning_plan_version_id == result_a.version.id
                )
            ).all()
        }
        b_links = {
            link.input_id
            for link in db_session.scalars(
                select(MorningPlanInputLink).where(
                    MorningPlanInputLink.morning_plan_version_id == result_b.version.id
                )
            ).all()
        }
        assert version.id in a_links
        assert version.id in b_links
