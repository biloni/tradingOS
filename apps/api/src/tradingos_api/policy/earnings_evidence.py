"""Earnings-evidence cutoff enforcement (Revision Prompt R3,
docs/HYBRID_EARNINGS_STRATEGY.md HES-7: "no leakage from the future").

A pre-event snapshot (`models.market_evidence.EarningsFeatureSnapshot`)
is a claim about what was knowable as of its `evidence_cutoff`. If it
were ever linked to a reported `EarningsActual` that only became usable
*after* that cutoff, the snapshot would silently encode information the
real pipeline could never have had at that moment — a correctness bug
that is easy to introduce (a stray join, a backfill script) and easy to
miss in review. `assert_actual_not_leaked_into_pre_event_snapshot()` is
the one deterministic gate any code path that links the two must call.

Pure, DB-agnostic Python — no SQLAlchemy import, no query — matching
this package's existing `order_authority.py`/`recommendation_modes.py`
pattern: callers pass the two timestamps (and the pre/post-event flag)
they already have from whichever ORM rows they loaded, so this module
never becomes a hidden second source of truth for how evidence is
fetched.
"""

from __future__ import annotations

from datetime import datetime


class EarningsEvidenceLeakage(Exception):
    """Raised when linking an actual to a snapshot would leak
    not-yet-usable information into a pre-event snapshot. Fail-closed:
    an ambiguous ordering (equal timestamps count as *not* leaked, since
    the actual became usable at exactly the cutoff, not after it) is the
    only case treated as safe."""


def assert_actual_not_leaked_into_pre_event_snapshot(
    *,
    is_pre_event: bool,
    evidence_cutoff: datetime,
    actual_usable_at: datetime,
) -> None:
    """Raise `EarningsEvidenceLeakage` iff `is_pre_event` is True and the
    actual's `usable_at` is strictly later than the snapshot's
    `evidence_cutoff` — i.e. the snapshot claims a cutoff earlier than
    the moment the linked actual could safely be used. A post-event
    snapshot (`is_pre_event=False`, e.g. `PostEarningsConfirmationSnapshot`'s
    own `evidence_cutoff`) is exempt: linking an actual there is the
    entire point, not a leak."""
    if not is_pre_event:
        return
    if actual_usable_at > evidence_cutoff:
        raise EarningsEvidenceLeakage(
            "actual became usable at "
            f"{actual_usable_at.isoformat()}, after the pre-event snapshot's "
            f"evidence_cutoff of {evidence_cutoff.isoformat()} — linking it would "
            "leak future information into a pre-event snapshot"
        )
