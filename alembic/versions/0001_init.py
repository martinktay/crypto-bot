"""init schema

Revision ID: 0001_init
Revises:
Create Date: 2026-03-29
"""

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

revision = "0001_init"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("users", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("telegram_user_id", sa.String(64), nullable=False), sa.Column("role", sa.String(32), nullable=False))
    op.create_index("ix_users_telegram_user_id", "users", ["telegram_user_id"], unique=True)

    op.create_table("bot_settings", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("mode", sa.String(32), nullable=False), sa.Column("paused", sa.Boolean(), nullable=False))

    op.create_table(
        "signals",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("symbol", sa.String(20), nullable=False),
        sa.Column("timeframe", sa.String(10), nullable=False),
        sa.Column("signal", sa.String(10), nullable=False),
        sa.Column("entry_price", sa.Float(), nullable=False),
        sa.Column("stop_loss", sa.Float(), nullable=False),
        sa.Column("take_profit", sa.Float(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("ai_explanation", sa.Text(), nullable=False),
        sa.Column("timestamp", sa.DateTime(), nullable=False),
    )

    op.create_table(
        "trades",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("signal_id", sa.Integer(), sa.ForeignKey("signals.id"), nullable=False),
        sa.Column("symbol", sa.String(20), nullable=False),
        sa.Column("mode", sa.String(32), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("quantity", sa.Float(), nullable=False),
        sa.Column("entry_price", sa.Float(), nullable=False),
        sa.Column("exit_price", sa.Float(), nullable=True),
        sa.Column("pnl", sa.Float(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )

    op.create_table(
        "positions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("trade_id", sa.Integer(), sa.ForeignKey("trades.id"), nullable=False),
        sa.Column("symbol", sa.String(20), nullable=False),
        sa.Column("quantity", sa.Float(), nullable=False),
        sa.Column("avg_price", sa.Float(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
    )

    op.create_table("knowledge_documents", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("source_type", sa.String(50), nullable=False), sa.Column("title", sa.String(200), nullable=False), sa.Column("content", sa.Text(), nullable=False), sa.Column("metadata_json", sa.JSON(), nullable=False), sa.Column("created_at", sa.DateTime(), nullable=False))
    op.create_table("knowledge_embeddings", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("document_id", sa.Integer(), sa.ForeignKey("knowledge_documents.id"), nullable=False), sa.Column("embedding", Vector(1536), nullable=False))


def downgrade() -> None:
    op.drop_table("knowledge_embeddings")
    op.drop_table("knowledge_documents")
    op.drop_table("positions")
    op.drop_table("trades")
    op.drop_table("signals")
    op.drop_table("bot_settings")
    op.drop_index("ix_users_telegram_user_id", table_name="users")
    op.drop_table("users")
