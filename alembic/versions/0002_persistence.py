"""add persistence models (pending_approvals only)

This migration only creates the ``pending_approvals`` table. The
``bot_settings`` column additions originally in this migration are
handled by ``0002_fix_bot_settings`` (a parallel branch); duplicating
them here caused ``alembic upgrade head`` to fail on fresh databases
because both branches ran and tried to add the same columns.

Revision ID: 0002_persistence
Revises: 0001_init
Create Date: 2026-03-29
"""

from alembic import op
import sqlalchemy as sa


revision = "0002_persistence"
down_revision = "0001_init"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pending_approvals",
        sa.Column("approval_id", sa.String(length=64), nullable=False),
        sa.Column("signal_id", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="pending", nullable=False),
        sa.ForeignKeyConstraint(["signal_id"], ["signals.id"]),
        sa.PrimaryKeyConstraint("approval_id"),
    )
    op.create_index(
        op.f("ix_pending_approvals_signal_id"),
        "pending_approvals",
        ["signal_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_pending_approvals_expires_at"),
        "pending_approvals",
        ["expires_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_pending_approvals_status"),
        "pending_approvals",
        ["status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_pending_approvals_status"), table_name="pending_approvals")
    op.drop_index(op.f("ix_pending_approvals_expires_at"), table_name="pending_approvals")
    op.drop_index(op.f("ix_pending_approvals_signal_id"), table_name="pending_approvals")
    op.drop_table("pending_approvals")
