"""add strategy_version status lifecycle

Revision ID: eed7cb451bdc
Revises: 130bfdd45919
Create Date: 2026-08-03 12:33:23.614948

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "eed7cb451bdc"
down_revision: str | Sequence[str] | None = "130bfdd45919"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema.

    Not purely additive (ADR-027): `is_active` is a live NOT NULL column
    with a real row today, so it's replaced with a proper `status`
    lifecycle via add-nullable -> backfill -> set-not-null -> drop, rather
    than a single autogenerate-style add/drop pair.
    """
    # Unlike op.create_table(), op.add_column() on an existing table does
    # NOT implicitly issue CREATE TYPE for an sa.Enum column — it must be
    # created explicitly first, or the ALTER TABLE fails with
    # "type ... does not exist".
    status_enum = sa.Enum(
        "PROPOSED", "ACTIVE", "REJECTED", "SUPERSEDED", name="strategy_version_status"
    )
    status_enum.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "strategy_versions",
        sa.Column("status", status_enum, nullable=True),
    )
    op.execute("UPDATE strategy_versions SET status = 'ACTIVE' WHERE is_active = true")
    op.execute("UPDATE strategy_versions SET status = 'PROPOSED' WHERE is_active = false")
    op.alter_column("strategy_versions", "status", nullable=False)

    op.add_column(
        "strategy_versions", sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("strategy_versions", sa.Column("decision_comment", sa.Text(), nullable=True))
    op.drop_column("strategy_versions", "is_active")


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column("strategy_versions", sa.Column("is_active", sa.Boolean(), nullable=True))
    op.execute("UPDATE strategy_versions SET is_active = (status = 'ACTIVE')")
    op.alter_column("strategy_versions", "is_active", nullable=False)

    op.drop_column("strategy_versions", "decision_comment")
    op.drop_column("strategy_versions", "decided_at")
    op.drop_column("strategy_versions", "status")
    # Manually added (same gotcha hit in Phase 2-5 migrations): op.drop_column()
    # does not drop the native Postgres ENUM type it created.
    sa.Enum(name="strategy_version_status").drop(op.get_bind(), checkfirst=True)
