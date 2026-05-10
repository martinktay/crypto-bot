"""Add optional EMA-separation audit score column on signals.

Revision ID: 0008_signal_audit
Revises: 0007_widen_symbol
Create Date: 2026-05-09
"""

from alembic import op
import sqlalchemy as sa

revision = "0008_signal_audit"
down_revision = "0007_widen_symbol"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "signals",
        sa.Column("confidence_audit_ema_bps", sa.Float(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("signals", "confidence_audit_ema_bps")
