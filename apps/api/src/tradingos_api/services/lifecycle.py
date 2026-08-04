"""Generic lifecycle-transition guard (models/enums.py's transition maps).

One function, reused by every domain service that mutates a status column,
so "is this transition even legal" is answered identically everywhere
rather than re-implemented per entity.
"""

from __future__ import annotations


class InvalidTransitionError(ValueError):
    def __init__(self, entity: str, current: str, attempted: str) -> None:
        super().__init__(f"{entity}: cannot transition from {current} to {attempted}")
        self.entity = entity
        self.current = current
        self.attempted = attempted


def assert_transition_allowed(
    entity: str,
    current: str,
    attempted: str,
    transitions: dict[str, set[str]],
) -> None:
    """Raises `InvalidTransitionError` unless `attempted` is in the allowed
    set for `current`. A `current` state missing from `transitions` (a
    terminal state with no outgoing edges) has an implicit empty allowed
    set — any attempted transition from it is rejected."""
    allowed = transitions.get(current, set())
    if attempted not in allowed:
        raise InvalidTransitionError(entity, current, attempted)
