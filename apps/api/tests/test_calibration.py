"""Calibration tests (Revision Prompt 14) — sparse-sample suppression,
regime segmentation never blending distinct regimes, and a DB-level
smoke test for `get_closed_outcomes()`."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from tradingos_api.models.execution import Account
from tradingos_api.models.recommendations import Recommendation
from tradingos_api.models.security_master import Instrument
from tradingos_api.services.calibration import (
    MIN_SAMPLE_SIZE_FOR_CALIBRATION,
    ClosedOutcome,
    _bin_from_outcomes,
    calibration_by_regime,
    calibration_by_sector,
    get_closed_outcomes,
    reliability_by_confidence_band,
    reliability_by_score_band,
    score_to_predicted_probability,
)


def _outcome(
    *,
    is_win: bool,
    score: Decimal | None = Decimal(6),
    confidence: str = "MEDIUM",
    sector: str | None = "Technology",
    regime: str | None = None,
    mode: str = "TACTICAL",
) -> ClosedOutcome:
    return ClosedOutcome(
        recommendation_id=uuid.uuid4(),
        recommendation_version_id=uuid.uuid4(),
        mode=mode,
        score=score,
        confidence=confidence,
        expected_move_pct=None,
        is_win=is_win,
        pnl_source="ACTUAL",
        sector=sector,
        regime=regime,
        event_timing_category=None,
        holding_period_days=None,
    )


class TestScoreToPredictedProbability:
    def test_known_vector(self) -> None:
        assert score_to_predicted_probability(Decimal(8)) == Decimal(1)
        assert score_to_predicted_probability(Decimal(4)) == Decimal("0.5")
        assert score_to_predicted_probability(Decimal(0)) == Decimal(0)

    def test_none_score_is_none(self) -> None:
        assert score_to_predicted_probability(None) is None


class TestSparseBinSuppression:
    def test_below_threshold_reports_sample_size_but_no_statistics(self) -> None:
        outcomes = [_outcome(is_win=True) for _ in range(MIN_SAMPLE_SIZE_FOR_CALIBRATION - 1)]
        result = _bin_from_outcomes("TEST", outcomes)
        assert result.sample_size == MIN_SAMPLE_SIZE_FOR_CALIBRATION - 1
        assert result.is_adequate is False
        assert result.observed_hit_rate_pct is None
        assert result.ci_low_pct is None
        assert result.ci_high_pct is None
        assert result.brier_score is None

    def test_exactly_at_threshold_is_adequate(self) -> None:
        outcomes = [
            _outcome(is_win=(i % 2 == 0)) for i in range(MIN_SAMPLE_SIZE_FOR_CALIBRATION)
        ]
        result = _bin_from_outcomes("TEST", outcomes)
        assert result.is_adequate is True
        assert result.observed_hit_rate_pct is not None
        assert result.ci_low_pct is not None
        assert result.brier_score is not None

    def test_zero_sample_reports_zero_not_a_crash(self) -> None:
        result = _bin_from_outcomes("EMPTY", [])
        assert result.sample_size == 0
        assert result.is_adequate is False
        assert result.observed_hit_rate_pct is None


class TestRegimeSegmentationNeverBlends:
    def test_two_distinct_regimes_reported_as_separate_bins(self) -> None:
        calm = [_outcome(is_win=True, regime="CALM") for _ in range(25)]
        stressed = [_outcome(is_win=False, regime="STRESSED") for _ in range(25)]
        bins = calibration_by_regime(calm + stressed)
        labels = {b.label for b in bins}
        assert labels == {"CALM", "STRESSED"}
        calm_bin = next(b for b in bins if b.label == "CALM")
        stressed_bin = next(b for b in bins if b.label == "STRESSED")
        assert calm_bin.observed_hit_rate_pct == Decimal(100)
        assert stressed_bin.observed_hit_rate_pct == Decimal(0)

    def test_outcome_with_no_regime_is_excluded_not_guessed(self) -> None:
        outcomes = [_outcome(is_win=True, regime=None) for _ in range(25)]
        bins = calibration_by_regime(outcomes)
        assert bins == []


class TestConfidenceAndScoreAreDistinctAxes:
    """DQ-4's own "confidence and magnitude are different numbers"
    extended to this module's own axes — grouping by confidence band
    must never fall back to grouping by score, and vice versa."""

    def test_confidence_band_grouping_ignores_score(self) -> None:
        outcomes = [
            _outcome(is_win=True, confidence="HIGH", score=Decimal(1)) for _ in range(25)
        ] + [_outcome(is_win=False, confidence="LOW", score=Decimal(1)) for _ in range(25)]
        bins = reliability_by_confidence_band(outcomes)
        labels = {b.label for b in bins}
        assert labels == {"HIGH", "LOW"}

    def test_score_band_grouping_ignores_confidence(self) -> None:
        outcomes = [
            _outcome(is_win=True, score=Decimal(8), confidence="LOW") for _ in range(25)
        ] + [_outcome(is_win=False, score=Decimal(1), confidence="LOW") for _ in range(25)]
        bins = reliability_by_score_band(outcomes)
        labels = {b.label for b in bins}
        assert "8" in labels
        assert "0-3" in labels


class TestSectorSegmentation:
    def test_sparse_sector_reported_honestly(self) -> None:
        outcomes = [_outcome(is_win=True, sector="Energy") for _ in range(3)]
        bins = calibration_by_sector(outcomes)
        assert len(bins) == 1
        assert bins[0].sample_size == 3
        assert bins[0].is_adequate is False


class TestGetClosedOutcomesDbLevel:
    def test_pending_recommendation_with_no_outcome_yet_is_excluded(
        self, db_session: Session, fresh_account: Account
    ) -> None:
        """A recommendation with a real version but no determined
        outcome yet (neither `RecommendationOutcome` nor
        `HypotheticalTradeOutcome`) — Revision Prompt 12's own `PENDING`
        disposition — must never contribute a guessed win/loss to
        calibration."""
        amd = db_session.scalar(select(Instrument).where(Instrument.ticker == "AMD"))
        assert amd is not None
        from tradingos_api.models.enums import (
            RecommendationAction,
            RecommendationConfidence,
            RecommendationMode,
            RecommendationStatus,
        )
        from tradingos_api.models.recommendations import RecommendationVersion

        rec = Recommendation(
            instrument_id=amd.id,
            mode=RecommendationMode.TACTICAL,
            opened_at=datetime.now(UTC),
            status=RecommendationStatus.ACTIVE,
        )
        db_session.add(rec)
        db_session.flush()
        db_session.add(
            RecommendationVersion(
                recommendation_id=rec.id,
                version_number=1,
                action=RecommendationAction.BUY,
                confidence=RecommendationConfidence.MEDIUM,
                score=Decimal("6.5"),
                rationale="Test fixture — no outcome recorded yet.",
                generated_at=datetime.now(UTC),
            )
        )
        db_session.flush()

        outcomes = get_closed_outcomes(db_session)
        assert all(o.recommendation_id != rec.id for o in outcomes)
