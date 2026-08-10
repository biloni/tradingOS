"""prompt14_change_governance_activation

Revision ID: 488f095f1425
Revises: 5078feb6e647
Create Date: 2026-08-09 20:48:58.945518

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "488f095f1425"
down_revision: str | Sequence[str] | None = "5078feb6e647"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Postgres enum values can only be added, never autodetected by
    # autogenerate (only new/changed columns are) — same gotcha every
    # prior revision's migration documents.
    op.execute("ALTER TYPE model_change_proposal_status ADD VALUE IF NOT EXISTS 'ACTIVATED'")
    op.execute("ALTER TYPE model_change_proposal_status ADD VALUE IF NOT EXISTS 'ROLLED_BACK'")

    # `evidence_package` is NOT NULL on a table with a pre-existing
    # seeded row — a server_default of an empty JSON object backfills it
    # (matching `ModelChangeProposal.evidence_package`'s own Python-side
    # `default=dict`, which only applies to new ORM inserts, not this
    # migration's existing row) rather than blocking the migration.
    op.add_column(
        "model_change_proposals",
        sa.Column(
            "evidence_package",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
            server_default="{}",
        ),
    )
    op.add_column(
        "model_change_proposals",
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "model_change_proposals", sa.Column("activated_by", sa.String(length=80), nullable=True)
    )
    op.add_column(
        "model_change_proposals",
        sa.Column("rolled_back_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "model_change_proposals", sa.Column("rolled_back_by", sa.String(length=80), nullable=True)
    )
    op.add_column(
        "model_change_proposals", sa.Column("rollback_reason", sa.Text(), nullable=True)
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("model_change_proposals", "rollback_reason")
    op.drop_column("model_change_proposals", "rolled_back_by")
    op.drop_column("model_change_proposals", "rolled_back_at")
    op.drop_column("model_change_proposals", "activated_by")
    op.drop_column("model_change_proposals", "activated_at")
    op.drop_column("model_change_proposals", "evidence_package")

    # Postgres has no DROP VALUE for an enum type — `ACTIVATED`/
    # `ROLLED_BACK` remain in `model_change_proposal_status`'s vocabulary
    # after downgrade, the same accepted limitation every prior
    # revision's migration documents (e.g. ADR-060's downgrade note).
