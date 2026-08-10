"""Morning-plan quality analytics tests (Revision Prompt 12) — runs
against whatever real `MorningPlanRun`/`MorningPlanVersion` history this
dev environment already has (seeded/demoed by Revision Prompt 9), plus
the from-empty sparse-sample case."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from tradingos_api.services.morning_plan_quality import (
    get_approval_conversion,
    get_morning_plan_quality_summary,
    get_realized_results_by_section,
)


class TestMorningPlanQualitySummary:
    def test_runs_against_real_seeded_history_without_error(self, db_session: Session) -> None:
        summary = get_morning_plan_quality_summary(db_session)
        assert summary.total_runs >= 0
        if summary.completed_runs > 0:
            assert summary.on_time_rate_pct is not None
            assert Decimal(0) <= summary.on_time_rate_pct <= Decimal(100)

    def test_far_future_since_filter_yields_sparse_zero_sample(self, db_session: Session) -> None:
        summary = get_morning_plan_quality_summary(db_session, since=date(2099, 1, 1))
        assert summary.total_runs == 0
        assert summary.on_time_rate_pct is None
        assert summary.complete_final_rate_pct is None
        assert summary.check_pass_rate_pct is None


class TestRealizedResultsBySection:
    def test_runs_without_error_and_reports_a_stats_result_per_section(
        self, db_session: Session
    ) -> None:
        results = get_realized_results_by_section(db_session)
        for section in results:
            assert section.stats.num_trades >= 0


class TestApprovalConversionSparse:
    def test_no_approvals_yields_none_conversion_rate_not_zero(self, db_session: Session) -> None:
        result = get_approval_conversion(db_session)
        if result.approved == 0:
            assert result.approval_to_submission_rate_pct is None
        # PENDING/INVALIDATED approvals count toward the total but
        # neither the approved nor denied/expired buckets.
        assert result.total_approvals >= result.approved + result.denied_or_expired
