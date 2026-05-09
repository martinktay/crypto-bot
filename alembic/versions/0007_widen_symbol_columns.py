"""Widen symbol columns for long linear-perp tickers (e.g. 1000000BABYDOGE/USDT:USDT).

Revision ID: 0007_widen_symbol
Revises: 0006_signal_extras
Create Date: 2026-05-09
"""

from alembic import op
import sqlalchemy as sa

revision = "0007_widen_symbol"
down_revision = "0006_signal_extras"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "signals",
        "symbol",
        existing_type=sa.String(20),
        type_=sa.String(80),
        existing_nullable=False,
    )
    op.alter_column(
        "backtest_history",
        "symbol",
        existing_type=sa.String(20),
        type_=sa.String(80),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "signals",
        "symbol",
        existing_type=sa.String(80),
        type_=sa.String(20),
        existing_nullable=False,
    )
    op.alter_column(
        "backtest_history",
        "symbol",
        existing_type=sa.String(80),
        type_=sa.String(20),
        existing_nullable=False,
    )
