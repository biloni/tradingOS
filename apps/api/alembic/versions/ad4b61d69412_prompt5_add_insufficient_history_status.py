"""prompt5_add_insufficient_history_status

Revision ID: ad4b61d69412
Revises: b5b705be657a
Create Date: 2026-08-06 21:56:54.383034

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "ad4b61d69412"
down_revision: str | Sequence[str] | None = "b5b705be657a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Discovered by actually running the Prompt 5 demo end-to-end:
    # `services/analytics.py` and `services/earnings_score.py` report
    # `INSUFFICIENT_HISTORY` for components whose input series is too
    # short (e.g. `PRIOR_GAP_BIAS` with fewer than 2 prior earnings
    # gaps), but the enum this migration's parent (b5b705be657a) created
    # only had PASS/FAIL/MISSING_DATA/CAPABILITY_UNAVAILABLE — persisting
    # such a component raised a real `ValueError` at write time. Additive
    # `ALTER TYPE ... ADD VALUE`, matching 6230f16ff209's precedent;
    # Alembic's autogenerate does not detect new native-enum members.
    op.execute("ALTER TYPE feature_component_status ADD VALUE IF NOT EXISTS 'INSUFFICIENT_HISTORY'")


def downgrade() -> None:
    """Downgrade schema."""
    # Postgres has no `DROP VALUE` for enum types — the added value is
    # left in place on downgrade, an accepted, harmless limitation
    # matching every prior `ADD VALUE` migration in this project
    # (6230f16ff209, ce0a85382604).
    pass
