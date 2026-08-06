"""Exercises `scripts.seed_phase8._seed_r3` against the real seeded DB
inside `db_session`'s rollback-wrapped transaction (conftest.py) — proves
the R3 seed extension runs cleanly and produces coherent, cross-
referencing rows without permanently touching the dev database that
every other test and manual verification session relies on."""

from __future__ import annotations

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from tradingos_api.models.execution import Account
from tradingos_api.models.identity import UserProfile
from tradingos_api.models.investment_thesis import InvestmentThesis
from tradingos_api.models.morning_plan import MorningPlanVersion
from tradingos_api.models.order_authority import OrderApproval
from tradingos_api.models.recommendations import Recommendation, RecommendationVersion
from tradingos_api.models.security_master import Instrument, WatchlistItem
from tradingos_api.scripts.seed_phase8 import _seed_r3


def test_seed_r3_runs_cleanly_against_the_real_seeded_db(db_session: Session) -> None:
    user = db_session.scalar(select(UserProfile))
    assert user is not None, "seed data must exist (run `tradingos-seed`)"

    instruments = {
        row.ticker: row
        for row in db_session.scalars(select(Instrument)).all()
        if row.ticker in {"AAPL", "AMD", "MRVL"}
    }
    assert set(instruments) == {"AAPL", "AMD", "MRVL"}, "seed instruments missing"

    watchlist_items = {
        row.ticker: item
        for item, row in db_session.execute(
            select(WatchlistItem, Instrument).join(
                Instrument, WatchlistItem.instrument_id == Instrument.id
            )
        ).all()
        if row.ticker == "AMD"
    }
    assert "AMD" in watchlist_items

    aapl_recommendation = db_session.scalar(
        select(Recommendation).where(Recommendation.instrument_id == instruments["AAPL"].id)
    )
    assert aapl_recommendation is not None
    aapl_rec_version = db_session.scalar(
        select(RecommendationVersion)
        .where(RecommendationVersion.recommendation_id == aapl_recommendation.id)
        .order_by(RecommendationVersion.version_number.desc())
    )
    assert aapl_rec_version is not None

    manual_account = db_session.scalar(select(Account).where(Account.name == "Personal Journal"))
    assert manual_account is not None

    before_theses = db_session.scalar(select(func.count()).select_from(InvestmentThesis)) or 0
    before_plans = db_session.scalar(select(func.count()).select_from(MorningPlanVersion)) or 0
    before_approvals = db_session.scalar(select(func.count()).select_from(OrderApproval)) or 0

    _seed_r3(
        db_session,
        user,
        instruments,
        watchlist_items,
        aapl_recommendation,
        aapl_rec_version,
        manual_account,
    )
    db_session.flush()

    after_theses = db_session.scalar(select(func.count()).select_from(InvestmentThesis))
    after_plans = db_session.scalar(select(func.count()).select_from(MorningPlanVersion))
    after_approvals = db_session.scalar(select(func.count()).select_from(OrderApproval))

    assert after_theses == before_theses + 1
    assert after_plans == before_plans + 1
    assert after_approvals == before_approvals + 1

    assert aapl_rec_version.lane_action == "TRADE_ENTER"
    assert aapl_rec_version.horizon_days_max == 10

    integrity_check = db_session.execute(
        text(
            "SELECT count(*) FROM approval_bound_fields ab "
            "JOIN order_approvals oa ON oa.id = ab.order_approval_id "
            "WHERE oa.integrity_hash IS NOT NULL"
        )
    ).scalar()
    assert integrity_check and integrity_check > 0
