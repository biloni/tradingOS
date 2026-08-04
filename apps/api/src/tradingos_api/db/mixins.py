"""Shared column mixins for the Phase 8 domain model (ADR-043).

`sa.Uuid(as_uuid=True)` is SQLAlchemy 2.0's own cross-dialect UUID type —
native `uuid` on PostgreSQL, a portable fallback everywhere else (the same
"native on Postgres, portable elsewhere" philosophy `db/json_type.py`
already established for JSON) — so the same model works against the real
Postgres database and the in-memory SQLite used by endpoint-test fixtures,
without a hand-rolled TypeDecorator.

Every *new* (Phase 8+) table uses `UUIDPkMixin` for its primary key (ADR-043
— UUIDs "where appropriate" means the whole new domain model, since several
of its tables are natural idempotency/ingestion-key targets and a UUID
avoids any future multi-source-ingestion collision risk). Tables carried
over unchanged from Phases 1-7 (only `audit_events`, which is never
referenced by an FK and gains nothing from a UUID swap) keep their existing
integer PK.
"""

from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column


class UUIDPkMixin:
    """A random (v4) UUID primary key, generated application-side so the id
    is known before the first flush (useful for constructing related rows
    in the same transaction without a round-trip)."""

    id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )


class CreatedAtMixin:
    """`created_at` only — for append-only/immutable rows (evidence,
    snapshots, events) where there is no second write to timestamp."""

    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )


class TimestampMixin(CreatedAtMixin):
    """`created_at` + `updated_at` — for rows that are genuinely mutated in
    place (not append-only). `updated_at` is maintained by the ORM's
    `onupdate`, not application code, so it can't be forgotten at a call
    site."""

    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        server_default=sa.func.now(),
        onupdate=sa.func.now(),
    )


class OwnedMixin:
    """Row ownership (per the refinement brief: "add row ownership even
    though the initial system is single-user"). Every table that
    represents *this user's* data (as opposed to shared reference/master
    data like `instruments` or `sectors`) carries this. Not nullable —
    every owned row is unambiguously owned from the moment it's created,
    even though `services/identity.py`'s `get_or_create_default_user()`
    (Phase 8, no auth yet — ADR-007 unchanged) is the only source of a
    `user_profile.id` today.
    """

    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("user_profile.id"), index=True
    )
