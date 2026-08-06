"""General point-in-time cutoff enforcement (Revision Prompt 4) — the
same discipline `policy/earnings_evidence.py` (R3) already applies to
`EarningsActual.usable_at` vs. a pre-event snapshot's `evidence_cutoff`,
generalized to every evidence type carrying its own `usable_at` field
(`NewsItem`, `EarningsGuidanceItem`, `EarningsConsensusSnapshot`,
`EarningsRevision`, `FundamentalsSnapshot`). "A feature snapshot may use
only evidence with usable_at <= its cutoff."

Pure, DB-agnostic Python — no SQLAlchemy import, no query — matching
this package's existing pattern: callers pass the timestamps they
already loaded from whichever ORM rows, so this module never becomes a
second, hidden source of truth for how evidence is fetched.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


class EvidenceNotYetUsable(Exception):
    """Raised when a single piece of evidence's `usable_at` is later
    than the cutoff it's being used against."""


@dataclass(frozen=True)
class EvidenceUsabilityViolation:
    label: str
    usable_at: datetime
    cutoff: datetime


class SnapshotLeakageError(Exception):
    """Raised by `assert_snapshot_evidence_usable_by_cutoff()` — carries
    every violation found, not just the first, since a real pre-event
    snapshot construction pulls from several evidence tables at once and
    a caller fixing a leak wants to see the whole list in one pass."""

    def __init__(self, violations: list[EvidenceUsabilityViolation]) -> None:
        self.violations = violations
        detail = "; ".join(
            f"{v.label} usable_at={v.usable_at.isoformat()} > cutoff={v.cutoff.isoformat()}"
            for v in violations
        )
        super().__init__(f"{len(violations)} evidence item(s) not usable by cutoff: {detail}")


def assert_evidence_usable_by_cutoff(label: str, usable_at: datetime, cutoff: datetime) -> None:
    """Raise `EvidenceNotYetUsable` iff `usable_at` is strictly later
    than `cutoff`. Equal timestamps are allowed (the evidence became
    usable at exactly the cutoff, not after it)."""
    if usable_at > cutoff:
        raise EvidenceNotYetUsable(
            f"{label}: usable_at {usable_at.isoformat()} is after cutoff {cutoff.isoformat()}"
        )


def assert_snapshot_evidence_usable_by_cutoff(
    evidence: list[tuple[str, datetime]], cutoff: datetime
) -> None:
    """Batch form for constructing a real snapshot from several evidence
    rows at once (news + guidance + consensus + revisions +
    fundamentals) — collects every violation rather than stopping at the
    first, so a caller can see everything that needs fixing in one
    error."""
    violations = [
        EvidenceUsabilityViolation(label=label, usable_at=usable_at, cutoff=cutoff)
        for label, usable_at in evidence
        if usable_at > cutoff
    ]
    if violations:
        raise SnapshotLeakageError(violations)
