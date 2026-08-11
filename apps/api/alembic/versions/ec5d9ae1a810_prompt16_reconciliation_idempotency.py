"""prompt16_reconciliation_idempotency

Revision ID: ec5d9ae1a810
Revises: b12a331c7d77
Create Date: 2026-08-11 15:15:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "ec5d9ae1a810"
down_revision: str | Sequence[str] | None = "b12a331c7d77"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "reconciliation_runs",
        sa.Column("idempotency_key", sa.String(length=120), nullable=True),
    )
    op.create_index(
        "ix_reconciliation_runs_idempotency_key",
        "reconciliation_runs",
        ["idempotency_key"],
        unique=True,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_reconciliation_runs_idempotency_key", table_name="reconciliation_runs")
    op.drop_column("reconciliation_runs", "idempotency_key")
