"""signal-only cleanup + real outcome tracking

- Drops ``positions`` and ``trades`` tables (signal-only architecture).
- Adds outcome tracking columns to ``signals`` so the dashboard can show
  real performance instead of values fabricated from confidence.

Revision ID: 0004_signal_only_outcomes
Revises: 1b3d17642dc2
Create Date: 2026-05-07
"""

from alembic import op
import sqlalchemy as sa


revision = "0004_signal_only_outcomes"
down_revision = "1b3d17642dc2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    existing_tables = set(insp.get_table_names())

    if "positions" in existing_tables:
        op.drop_table("positions")
    if "trades" in existing_tables:
        op.drop_table("trades")

    signal_columns = {c["name"] for c in insp.get_columns("signals")}

    if "outcome_status" not in signal_columns:
        op.add_column(
            "signals",
            sa.Column(
                "outcome_status",
                sa.String(length=20),
                nullable=False,
                server_default="pending",
            ),
        )
    if "outcome_pnl_percent" not in signal_columns:
        op.add_column(
            "signals",
            sa.Column("outcome_pnl_percent", sa.Float(), nullable=True),
        )
    if "outcome_max_drawdown_percent" not in signal_columns:
        op.add_column(
            "signals",
            sa.Column("outcome_max_drawdown_percent", sa.Float(), nullable=True),
        )
    if "outcome_resolved_at" not in signal_columns:
        op.add_column(
            "signals",
            sa.Column("outcome_resolved_at", sa.DateTime(), nullable=True),
        )

    op.create_index(
        "ix_signals_outcome_status",
        "signals",
        ["outcome_status"],
    )


def downgrade() -> None:
    op.drop_index("ix_signals_outcome_status", table_name="signals")
    op.drop_column("signals", "outcome_resolved_at")
    op.drop_column("signals", "outcome_max_drawdown_percent")
    op.drop_column("signals", "outcome_pnl_percent")
    op.drop_column("signals", "outcome_status")

    op.create_table(
        "trades",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("signal_id", sa.Integer(), sa.ForeignKey("signals.id"), nullable=False, index=True),
        sa.Column("symbol", sa.String(20), nullable=False, index=True),
        sa.Column("mode", sa.String(32), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, index=True),
        sa.Column("quantity", sa.Float(), nullable=False),
        sa.Column("entry_price", sa.Float(), nullable=False),
        sa.Column("exit_price", sa.Float(), nullable=True),
        sa.Column("pnl", sa.Float(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "positions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("trade_id", sa.Integer(), sa.ForeignKey("trades.id"), nullable=False, index=True),
        sa.Column("symbol", sa.String(20), nullable=False, index=True),
        sa.Column("quantity", sa.Float(), nullable=False),
        sa.Column("avg_price", sa.Float(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="open", index=True),
    )
