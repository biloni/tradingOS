"""Future-data leakage tests for the Revision Prompt 5 feature engines.
P5's compute_* functions are pure and take caller-supplied values, so
the leakage boundary they must respect is the same one Revision Prompt
4 already built: `policy/point_in_time.py`'s "a feature snapshot may use
only evidence with usable_at <= its cutoff." This proves a P5 snapshot's
`evidence_cutoff` is enforced by that same guard against the evidence
feeding the tactical/investment engines (consensus, revisions, guidance)
— not a second, parallel leakage rule invented for this revision."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from tradingos_api.policy.point_in_time import (
    SnapshotLeakageError,
    assert_snapshot_evidence_usable_by_cutoff,
)


class TestEvidenceUsableStrictlyAfterCutoffIsRejected:
    def test_consensus_usable_after_the_snapshot_cutoff_raises(self) -> None:
        cutoff = datetime(2026, 8, 6, 6, 0, tzinfo=UTC)  # pre-market cutoff, report day
        future_consensus_usable_at = cutoff + timedelta(hours=2)  # published after the cutoff
        with pytest.raises(SnapshotLeakageError) as exc_info:
            assert_snapshot_evidence_usable_by_cutoff(
                [("EarningsConsensusSnapshot", future_consensus_usable_at)], cutoff
            )
        assert "EarningsConsensusSnapshot" in str(exc_info.value)

    def test_all_evidence_types_feeding_the_tactical_score_are_checked_together(self) -> None:
        """A real pre-event tactical snapshot pulls consensus, analyst
        revisions, and guidance at once — this proves the batch form
        surfaces every violation, not just the first, so nothing slips
        through because an earlier item happened to pass."""
        cutoff = datetime(2026, 8, 6, 6, 0, tzinfo=UTC)
        evidence = [
            ("EarningsConsensusSnapshot", cutoff - timedelta(days=1)),  # OK
            ("AnalystRevision", cutoff + timedelta(hours=1)),  # leaks
            ("EarningsGuidanceItem", cutoff + timedelta(days=1)),  # leaks
        ]
        with pytest.raises(SnapshotLeakageError) as exc_info:
            assert_snapshot_evidence_usable_by_cutoff(evidence, cutoff)
        assert len(exc_info.value.violations) == 2
        violating_labels = {v.label for v in exc_info.value.violations}
        assert violating_labels == {"AnalystRevision", "EarningsGuidanceItem"}


class TestEvidenceUsableAtOrBeforeCutoffIsAccepted:
    def test_evidence_usable_exactly_at_the_cutoff_is_not_a_violation(self) -> None:
        cutoff = datetime(2026, 8, 6, 6, 0, tzinfo=UTC)
        assert_snapshot_evidence_usable_by_cutoff(
            [
                ("EarningsConsensusSnapshot", cutoff),
                ("FundamentalsSnapshot", cutoff - timedelta(days=30)),
            ],
            cutoff,
        )  # must not raise

    def test_post_earnings_cutoff_after_the_report_correctly_admits_the_actual(self) -> None:
        """`PostEarningsConfirmationSnapshot` is structurally the
        post-event table (see `models/market_evidence.py`) — its cutoff
        is naturally after the report, so the same guard correctly
        admits the now-published actual rather than rejecting it."""
        post_event_cutoff = datetime(2026, 8, 6, 20, 0, tzinfo=UTC)  # after the close
        actual_usable_at = datetime(2026, 8, 6, 16, 5, tzinfo=UTC)  # published at the close
        assert_snapshot_evidence_usable_by_cutoff(
            [("EarningsActual", actual_usable_at)], post_event_cutoff
        )  # must not raise
