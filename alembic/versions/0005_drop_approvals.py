"""drop legacy approvals (table + bot_settings.approval_mode)

The signal-only product no longer has a manual approval flow. Risk-passing
signals are auto-broadcast; rejected ones are filtered silently.

Revision ID: 0005_drop_approvals
Revises: 0004_signal_only_outcomes
Create Date: 2026-05-09
"""

from alembic import op
import sqlalchemy as sa


revision = "0005_drop_approvals"
down_revision = "0004_signal_only_outcomes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    existing_tables = set(insp.get_table_names())

    if "pending_approvals" in existing_tables:
        existing_indexes = {
            ix["name"] for ix in insp.get_indexes("pending_approvals")
        }
        for ix_name in (
            "ix_pending_approvals_status",
            "ix_pending_approvals_expires_at",
            "ix_pending_approvals_signal_id",
        ):
            if ix_name in existing_indexes:
                op.drop_index(ix_name, table_name="pending_approvals")
        op.drop_table("pending_approvals")

    if "bot_settings" in existing_tables:
        bot_settings_columns = {
            c["name"] for c in insp.get_columns("bot_settings")
        }
        if "approval_mode" in bot_settings_columns:
            with op.batch_alter_table("bot_settings") as batch_op:
                batch_op.drop_column("approval_mode")


def downgrade() -> None:
    op.add_column(
        "bot_settings",
        sa.Column(
            "approval_mode",
            sa.String(length=32),
            nullable=False,
            server_default="manual_approval",
        ),
    )

    op.create_table(
        "pending_approvals",
        sa.Column("approval_id", sa.String(length=64), nullable=False),
        sa.Column("signal_id", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column(
            "status",
            sa.String(length=20),
            server_default="pending",
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["signal_id"], ["signals.id"]),
        sa.PrimaryKeyConstraint("approval_id"),
    )
    op.create_index(
        "ix_pending_approvals_signal_id",
        "pending_approvals",
        ["signal_id"],
    )
    op.create_index(
        "ix_pending_approvals_expires_at",
        "pending_approvals",
        ["expires_at"],
    )
    op.create_index(
        "ix_pending_approvals_status",
        "pending_approvals",
        ["status"],
    )
