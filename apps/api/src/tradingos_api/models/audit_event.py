from datetime import datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from tradingos_api.db.base import Base

# Native JSONB on Postgres (production); portable JSON everywhere else
# (in-memory SQLite in tests/test_symbols_endpoints.py-style fixtures)
# — SQLAlchemy's standard cross-dialect JSON pattern.
_JSON_TYPE = sa.JSON().with_variant(JSONB(), "postgresql")


class AuditEvent(Base):
    """The audit trail (principle 9). Written for every recommendation,
    score, input snapshot, prompt version, model response, user action,
    order, and override — starting this phase with `PaperOrder` actions
    (propose/confirm/cancel), via services/audit.py's
    `record_audit_event()`, the one place these rows get written from.

    `ref_id` is a plain integer, not a foreign key — a generic audit log
    references many different entity types over the life of this app
    (`record_type` disambiguates), which a single-target FK column can't
    express. Append-only: nothing here is ever updated or deleted.
    """

    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    record_type: Mapped[str] = mapped_column(sa.String(50), index=True)
    ref_id: Mapped[int] = mapped_column(sa.Integer)
    snapshot: Mapped[dict[str, Any]] = mapped_column(_JSON_TYPE)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
