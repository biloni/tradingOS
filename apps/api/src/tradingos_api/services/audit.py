from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from tradingos_api.models.audit_event import AuditEvent


def record_audit_event(
    session: Session, record_type: str, ref_id: int, snapshot: dict[str, Any]
) -> AuditEvent:
    """The one place `AuditEvent` rows get written from (principle 9).
    Flushes (not commits) so the caller controls the transaction boundary —
    an audit event is normally written in the same transaction as the
    change it's recording."""
    event = AuditEvent(
        record_type=record_type,
        ref_id=ref_id,
        snapshot=snapshot,
        created_at=datetime.now(UTC),
    )
    session.add(event)
    session.flush()
    return event
