"""advanced risk fields

Revision ID: 0003_advanced_risk_fields
Revises: 0002_fix_bot_settings
Create Date: 2026-03-30
"""

from alembic import op
import sqlalchemy as sa


revision = "0003_advanced_risk_fields"
down_revision = "0002_fix_bot_settings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Adding fields to positions for TSL
    op.add_column("positions", sa.Column("highest_price", sa.Float(), nullable=True))
    op.add_column("positions", sa.Column("lowest_price", sa.Float(), nullable=True))
    op.add_column("positions", sa.Column("trailing_stop_activated", sa.Boolean(), nullable=False, server_default="false"))
    
    # Adding ATR to signals for volatility-aware tracking
    op.add_column("signals", sa.Column("atr_value", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("signals", "atr_value")
    op.drop_column("positions", "trailing_stop_activated")
    op.drop_column("positions", "lowest_price")
    op.drop_column("positions", "highest_price")
