"""Validation grid tests (Revision Prompt 13) — sweep functions cover
every requested value, walk-forward windows are non-overlapping and
chronologically ordered, and the baseline reproduction report is honest
about both the locked and widened windows."""

from __future__ import annotations

from sqlalchemy.orm import Session

from tradingos_api.services.backtest_validation import (
    BASELINE_TARGETS,
    reproduce_baseline_scenario,
    run_lane_variant_comparison,
    run_score_threshold_sweep,
    run_walk_forward,
)


class TestScoreThresholdSweep:
    def test_returns_one_point_per_threshold(self, db_session: Session) -> None:
        points = run_score_threshold_sweep(db_session, thresholds=(4, 5, 6, 7))
        assert [p.label for p in points] == [">=4", ">=5", ">=6", ">=7"]

    def test_higher_threshold_never_admits_more_trades(self, db_session: Session) -> None:
        points = run_score_threshold_sweep(db_session, thresholds=(4, 7))
        low, high = points[0], points[1]
        assert high.result.trade_stats.num_trades <= low.result.trade_stats.num_trades


class TestLaneVariantComparison:
    def test_returns_pre_post_and_hybrid(self, db_session: Session) -> None:
        points = run_lane_variant_comparison(db_session)
        assert [p.label for p in points] == ["PRE_EVENT_ONLY", "POST_CONFIRMATION_ONLY", "HYBRID"]


class TestWalkForward:
    def test_three_non_overlapping_ordered_windows(self, db_session: Session) -> None:
        windows = run_walk_forward(db_session)
        assert [w.label for w in windows] == ["TRAIN", "VALIDATION", "OUT_OF_SAMPLE"]
        for earlier, later in zip(windows, windows[1:], strict=False):
            assert earlier.end < later.start


class TestBaselineReproduction:
    def test_reports_both_locked_and_wide_windows_with_targets(self, db_session: Session) -> None:
        report = reproduce_baseline_scenario(db_session)
        assert report.targets == BASELINE_TARGETS
        assert report.locked_window_result.config.start.year == 2026
        assert report.wide_window_result.config.start.year == 2024
        assert "synthetic" in report.deviation_explanation.lower()

    def test_locked_window_is_the_narrower_scenario(self, db_session: Session) -> None:
        report = reproduce_baseline_scenario(db_session)
        locked_days = (
            report.locked_window_result.config.end - report.locked_window_result.config.start
        ).days
        wide_days = (
            report.wide_window_result.config.end - report.wide_window_result.config.start
        ).days
        assert locked_days < wide_days
