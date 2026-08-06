"""Policy checks for earnings-evidence cutoff enforcement (Revision
Prompt R3, docs/HYBRID_EARNINGS_STRATEGY.md HES-7). Pure unit tests —
no DB, no HTTP — matching this repo's existing fixtures-only test
policy (docs/TEST_STRATEGY.md)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from tradingos_api.policy.earnings_evidence import (
    EarningsEvidenceLeakage,
    assert_actual_not_leaked_into_pre_event_snapshot,
)

CUTOFF = datetime(2026, 8, 5, 6, 0, tzinfo=UTC)


class TestPreEventRejectsFutureActuals:
    def test_actual_usable_after_cutoff_is_rejected(self) -> None:
        with pytest.raises(EarningsEvidenceLeakage, match="leak future information"):
            assert_actual_not_leaked_into_pre_event_snapshot(
                is_pre_event=True,
                evidence_cutoff=CUTOFF,
                actual_usable_at=CUTOFF + timedelta(minutes=1),
            )

    def test_actual_usable_well_before_cutoff_is_allowed(self) -> None:
        assert_actual_not_leaked_into_pre_event_snapshot(
            is_pre_event=True,
            evidence_cutoff=CUTOFF,
            actual_usable_at=CUTOFF - timedelta(days=90),
        )

    def test_actual_usable_at_exactly_cutoff_is_allowed(self) -> None:
        assert_actual_not_leaked_into_pre_event_snapshot(
            is_pre_event=True,
            evidence_cutoff=CUTOFF,
            actual_usable_at=CUTOFF,
        )


class TestPostEventIsExempt:
    def test_actual_usable_after_cutoff_is_allowed_when_not_pre_event(self) -> None:
        assert_actual_not_leaked_into_pre_event_snapshot(
            is_pre_event=False,
            evidence_cutoff=CUTOFF,
            actual_usable_at=CUTOFF + timedelta(days=1),
        )
