"""fix bot_settings columns

Revision ID: 0002_fix_bot_settings
Revises: 0001_init
Create Date: 2026-03-30
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0002_fix_bot_settings"
down_revision = "0001_init"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Adding missing columns to bot_settings
    # We use sa.JSON() which translates to JSON in Postgres
    op.add_column("bot_settings", sa.Column("symbols", sa.JSON(), nullable=False, server_default='["BTC/USDT"]'))
    op.add_column("bot_settings", sa.Column("timeframes", sa.JSON(), nullable=False, server_default='["15m"]'))
    op.add_column("bot_settings", sa.Column("strategy", sa.String(length=100), nullable=False, server_default='ema_rsi'))
    op.add_column("bot_settings", sa.Column("paper_balance", sa.Float(), nullable=False, server_default='10000.0'))
    op.add_column("bot_settings", sa.Column("daily_pnl", sa.Float(), nullable=False, server_default='0.0'))


def downgrade() -> None:
    op.drop_column("bot_settings", "daily_pnl")
    op.drop_column("bot_settings", "paper_balance")
    op.drop_column("bot_settings", "strategy")
    op.drop_column("bot_settings", "timeframes")
    op.drop_column("bot_settings", "symbols")
