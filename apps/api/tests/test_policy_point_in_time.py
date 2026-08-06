"""Point-in-time cutoff and future-data rejection tests (Revision
Prompt 4's required test #1). Pure unit tests — no DB — matching this
repo's existing fixtures-only test policy."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from tradingos_api.policy.point_in_time import (
    EvidenceNotYetUsable,
    SnapshotLeakageError,
    assert_evidence_usable_by_cutoff,
    assert_snapshot_evidence_usable_by_cutoff,
)

CUTOFF = datetime(2026, 8, 6, 6, 0, tzinfo=UTC)


class TestSingleEvidenceCutoff:
    def test_evidence_usable_before_cutoff_is_allowed(self) -> None:
        assert_evidence_usable_by_cutoff("news", CUTOFF - timedelta(hours=1), CUTOFF)

    def test_evidence_usable_exactly_at_cutoff_is_allowed(self) -> None:
        assert_evidence_usable_by_cutoff("news", CUTOFF, CUTOFF)

    def test_future_evidence_is_rejected(self) -> None:
        with pytest.raises(EvidenceNotYetUsable, match="news"):
            assert_evidence_usable_by_cutoff("news", CUTOFF + timedelta(minutes=1), CUTOFF)


class TestSnapshotBatchCutoff:
    def test_all_evidence_before_cutoff_passes(self) -> None:
        assert_snapshot_evidence_usable_by_cutoff(
            [
                ("news", CUTOFF - timedelta(days=1)),
                ("guidance", CUTOFF - timedelta(hours=2)),
                ("consensus", CUTOFF),
            ],
            CUTOFF,
        )

    def test_one_future_item_fails_the_whole_snapshot(self) -> None:
        with pytest.raises(SnapshotLeakageError) as exc_info:
            assert_snapshot_evidence_usable_by_cutoff(
                [
                    ("news", CUTOFF - timedelta(days=1)),
                    ("consensus", CUTOFF + timedelta(minutes=5)),
                ],
                CUTOFF,
            )
        assert len(exc_info.value.violations) == 1
        assert exc_info.value.violations[0].label == "consensus"

    def test_every_violation_is_collected_not_just_the_first(self) -> None:
        with pytest.raises(SnapshotLeakageError) as exc_info:
            assert_snapshot_evidence_usable_by_cutoff(
                [
                    ("news", CUTOFF + timedelta(minutes=1)),
                    ("guidance", CUTOFF + timedelta(hours=1)),
                    ("consensus", CUTOFF - timedelta(days=1)),
                ],
                CUTOFF,
            )
        labels = {v.label for v in exc_info.value.violations}
        assert labels == {"news", "guidance"}
