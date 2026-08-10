"""prompt13_event_backtest_engine

Revision ID: 5078feb6e647
Revises: b66014442014
Create Date: 2026-08-09 18:38:23.509203

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "5078feb6e647"
down_revision: str | Sequence[str] | None = "b66014442014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "event_backtest_runs",
        sa.Column(
            "strategy_key",
            sa.Enum(
                "SCORED_PRE_EARNINGS_BASELINE",
                "CONSERVATIVE_SCORE_6",
                "HYBRID_PRE_AND_POST",
                "POST_CONFIRMATION_ONLY",
                "TRADE_EVERY_EARNINGS_CONTROL",
                "EMA_CROSS_COMPARISON",
                "REGIME_PULLBACK_COMPARISON",
                "SPY_BUY_AND_HOLD",
                name="event_backtest_strategy_key",
            ),
            nullable=False,
        ),
        sa.Column(
            "dataset_split",
            sa.Enum(
                "FULL", "TRAIN", "VALIDATION", "OUT_OF_SAMPLE", name="event_backtest_dataset_split"
            ),
            nullable=False,
        ),
        sa.Column("walk_forward_window_label", sa.String(length=60), nullable=True),
        sa.Column("date_range_start", sa.Date(), nullable=False),
        sa.Column("date_range_end", sa.Date(), nullable=False),
        sa.Column(
            "config",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column(
            "results_summary",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("is_golden_regression", sa.Boolean(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "event_backtest_trades",
        sa.Column("backtest_run_id", sa.Uuid(), nullable=False),
        sa.Column("instrument_id", sa.Uuid(), nullable=False),
        sa.Column(
            "lane",
            sa.Enum("PRE_EVENT", "POST_CONFIRMATION", "CONTROL", name="event_backtest_trade_lane"),
            nullable=False,
        ),
        sa.Column("event_date", sa.Date(), nullable=True),
        sa.Column("fiscal_period", sa.String(length=20), nullable=True),
        sa.Column("entry_date", sa.Date(), nullable=False),
        sa.Column("entry_price", sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column("exit_date", sa.Date(), nullable=False),
        sa.Column("exit_price", sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column("quantity", sa.Numeric(precision=20, scale=8), nullable=False),
        sa.Column("fees_usd", sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column("pnl_usd", sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column("pnl_pct", sa.Numeric(precision=10, scale=4), nullable=False),
        sa.Column(
            "exit_reason",
            sa.Enum(
                "STOP", "TARGET", "TIME_EXIT", "END_OF_HISTORY", name="event_backtest_exit_reason"
            ),
            nullable=False,
        ),
        sa.Column("score", sa.Numeric(precision=6, scale=2), nullable=True),
        sa.Column("expected_move_pct", sa.Numeric(precision=10, scale=4), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["backtest_run_id"], ["event_backtest_runs.id"], name="fk_event_backtest_trades_run_id"
        ),
        sa.ForeignKeyConstraint(
            ["instrument_id"], ["instruments.id"], name="fk_event_backtest_trades_instrument_id"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_event_backtest_trades_backtest_run_id"),
        "event_backtest_trades",
        ["backtest_run_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_event_backtest_trades_instrument_id"),
        "event_backtest_trades",
        ["instrument_id"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        op.f("ix_event_backtest_trades_instrument_id"), table_name="event_backtest_trades"
    )
    op.drop_index(
        op.f("ix_event_backtest_trades_backtest_run_id"), table_name="event_backtest_trades"
    )
    op.drop_table("event_backtest_trades")
    op.drop_table("event_backtest_runs")
    sa.Enum(name="event_backtest_trade_lane").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="event_backtest_exit_reason").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="event_backtest_dataset_split").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="event_backtest_strategy_key").drop(op.get_bind(), checkfirst=True)
