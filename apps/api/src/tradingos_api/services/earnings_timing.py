"""Maps an `EarningsTimingCategory` to which trading session holds the
last pre-event evidence and which session shows the first post-event
reaction (Revision Prompt 4's "BEFORE_OPEN and AFTER_CLOSE entry/exit
mapping" requirement). Deliberately refuses to guess for the three
timing states that don't resolve to a specific session boundary —
returns an explicit `UNRESOLVED` pair rather than defaulting to
`BEFORE_OPEN`'s or `AFTER_CLOSE`'s mapping (principle 4/5).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SessionMapping:
    pre_event_session: str
    post_event_session: str


_UNRESOLVED = SessionMapping(pre_event_session="UNRESOLVED", post_event_session="UNRESOLVED")

_MAPPING: dict[str, SessionMapping] = {
    "BEFORE_OPEN": SessionMapping(
        pre_event_session="PRIOR_SESSION_CLOSE", post_event_session="TODAY_OPEN"
    ),
    "AFTER_CLOSE": SessionMapping(
        pre_event_session="TODAY_SESSION_CLOSE", post_event_session="NEXT_SESSION_OPEN"
    ),
    "DURING_MARKET": SessionMapping(
        pre_event_session="PRIOR_SESSION_CLOSE", post_event_session="INTRADAY_REACTION"
    ),
}


def map_earnings_timing_to_sessions(timing_category: str) -> SessionMapping:
    """`TIME_NOT_SUPPLIED`, `DATE_UNCONFIRMED`, and `UNKNOWN` all map to
    `UNRESOLVED`/`UNRESOLVED` — there is no session boundary to name
    without knowing at least the timing, so this never fabricates one."""
    return _MAPPING.get(timing_category, _UNRESOLVED)
