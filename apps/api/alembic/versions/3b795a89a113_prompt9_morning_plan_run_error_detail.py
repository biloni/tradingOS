"""prompt9_morning_plan_run_error_detail

Revision ID: 3b795a89a113
Revises: e36f3fdbf6a8
Create Date: 2026-08-08 18:28:07.715970

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "3b795a89a113"
down_revision: str | Sequence[str] | None = "e36f3fdbf6a8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("morning_plan_runs", sa.Column("error_detail", sa.Text(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("morning_plan_runs", "error_detail")
