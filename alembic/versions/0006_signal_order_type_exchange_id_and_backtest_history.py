"""add signals.order_type, signals.exchange_id, and backtest_history table

The ORM model in ``app/models/entities.py`` declares ``Signal.order_type``,
``Signal.exchange_id``, and a ``BacktestHistory`` table that no migration ever
created — so any deployment that ran ``alembic upgrade head`` ends up with a
schema that's missing the columns the app reads at request time, and a missing
``backtest_history`` table the dashboard and ``/backtests`` endpoint depend on.

This migration backfills the gap idempotently: it inspects the live schema and
only adds what's missing, so it works against fresh DBs and against partially
migrated ones (e.g. databases provisioned before this revision was authored).

Revision ID: 0006_signal_extras
Revises: 0005_drop_approvals
Create Date: 2026-05-09
"""

from alembic import op
import sqlalchemy as sa


revision = "0006_signal_extras"
down_revision = "0005_drop_approvals"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    existing_tables = set(insp.get_table_names())

    if "signals" in existing_tables:
        signal_columns = {c["name"] for c in insp.get_columns("signals")}
        signal_indexes = {ix["name"] for ix in insp.get_indexes("signals")}

        # NOT NULL with a server_default backfills existing rows safely; the
        # ORM no longer relies on the server_default once the column exists.
        if "order_type" not in signal_columns:
            op.add_column(
                "signals",
                sa.Column(
                    "order_type",
                    sa.String(length=20),
                    nullable=False,
                    server_default="LIMIT",
                ),
            )

        if "exchange_id" not in signal_columns:
            op.add_column(
                "signals",
                sa.Column(
                    "exchange_id",
                    sa.String(length=32),
                    nullable=False,
                    server_default="binance",
                ),
            )
        if "ix_signals_exchange_id" not in signal_indexes:
            op.create_index(
                "ix_signals_exchange_id",
                "signals",
                ["exchange_id"],
            )

    if "backtest_history" not in existing_tables:
        op.create_table(
            "backtest_history",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("symbol", sa.String(length=20), nullable=False),
            sa.Column("strategy", sa.String(length=100), nullable=False),
            sa.Column("timeframe", sa.String(length=10), nullable=False),
            sa.Column("params", sa.JSON(), nullable=False, server_default="{}"),
            sa.Column("initial_balance", sa.Float(), nullable=False),
            sa.Column("final_balance", sa.Float(), nullable=False),
            sa.Column("total_trades", sa.Integer(), nullable=False),
            sa.Column("win_rate", sa.Float(), nullable=False),
            sa.Column("max_drawdown", sa.Float(), nullable=False),
            sa.Column("sharpe_ratio", sa.Float(), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.func.now(),
            ),
        )
        op.create_index(
            "ix_backtest_history_symbol",
            "backtest_history",
            ["symbol"],
        )
        op.create_index(
            "ix_backtest_history_strategy",
            "backtest_history",
            ["strategy"],
        )
        op.create_index(
            "ix_backtest_history_created_at",
            "backtest_history",
            ["created_at"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    existing_tables = set(insp.get_table_names())

    if "backtest_history" in existing_tables:
        for ix_name in (
            "ix_backtest_history_created_at",
            "ix_backtest_history_strategy",
            "ix_backtest_history_symbol",
        ):
            try:
                op.drop_index(ix_name, table_name="backtest_history")
            except Exception:
                pass
        op.drop_table("backtest_history")

    if "signals" in existing_tables:
        signal_columns = {c["name"] for c in insp.get_columns("signals")}
        signal_indexes = {ix["name"] for ix in insp.get_indexes("signals")}

        if "ix_signals_exchange_id" in signal_indexes:
            op.drop_index("ix_signals_exchange_id", table_name="signals")
        if "exchange_id" in signal_columns:
            with op.batch_alter_table("signals") as batch_op:
                batch_op.drop_column("exchange_id")
        if "order_type" in signal_columns:
            with op.batch_alter_table("signals") as batch_op:
                batch_op.drop_column("order_type")
