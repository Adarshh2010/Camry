"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-06-14
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    action_enum = sa.Enum("LONG", "SHORT", "NO_TRADE", name="signal_action")
    side_enum = sa.Enum("LONG", "SHORT", name="position_side")
    status_enum = sa.Enum("OPEN", "CLOSED", "CANCELLED", name="position_status")

    op.create_table(
        "market_data",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("symbol", sa.String(32), nullable=False, index=True),
        sa.Column("source", sa.String(64), nullable=False),
        sa.Column("timeframe", sa.String(16), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False, index=True),
        sa.Column("open", sa.Numeric(24, 10), nullable=True),
        sa.Column("high", sa.Numeric(24, 10), nullable=True),
        sa.Column("low", sa.Numeric(24, 10), nullable=True),
        sa.Column("close", sa.Numeric(24, 10), nullable=False),
        sa.Column("volume", sa.Numeric(30, 10), nullable=True),
        sa.Column("open_interest", sa.Numeric(30, 10), nullable=True),
        sa.Column("funding_rate", sa.Numeric(18, 10), nullable=True),
        sa.Column("liquidations", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("raw", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("symbol", "source", "timeframe", "timestamp", name="uq_market_data"),
    )
    op.create_table(
        "news",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source", sa.String(128), nullable=False),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("url", sa.String(1024), nullable=False, unique=True),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True, index=True),
        sa.Column("dedupe_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("raw", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_table(
        "sentiment",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "news_id", sa.Integer(), sa.ForeignKey("news.id", ondelete="CASCADE"), nullable=True
        ),
        sa.Column("symbol", sa.String(32), nullable=True, index=True),
        sa.Column("sentiment_score", sa.Float(), nullable=False),
        sa.Column("impact_score", sa.Float(), nullable=False),
        sa.Column("confidence_score", sa.Float(), nullable=False),
        sa.Column("reasoning", sa.Text(), nullable=False),
        sa.Column("model", sa.String(128), nullable=False),
        sa.Column("raw", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_table(
        "signals",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("symbol", sa.String(32), nullable=False, index=True),
        sa.Column("action", action_enum, nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("bullish_score", sa.Float(), nullable=True),
        sa.Column("bearish_score", sa.Float(), nullable=True),
        sa.Column("risk_reward", sa.Float(), nullable=True),
        sa.Column("reasoning", sa.Text(), nullable=False),
        sa.Column("inputs", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
            index=True,
        ),
    )
    op.create_table(
        "positions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("symbol", sa.String(32), nullable=False, index=True),
        sa.Column("side", side_enum, nullable=False),
        sa.Column("status", status_enum, nullable=False),
        sa.Column("entry_price", sa.Numeric(24, 10), nullable=False),
        sa.Column("exit_price", sa.Numeric(24, 10), nullable=True),
        sa.Column("quantity", sa.Numeric(30, 10), nullable=False),
        sa.Column("leverage", sa.Float(), nullable=False),
        sa.Column("stop_loss", sa.Numeric(24, 10), nullable=True),
        sa.Column("take_profit", sa.Numeric(24, 10), nullable=True),
        sa.Column(
            "opened_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("realized_pnl", sa.Numeric(30, 10), nullable=True),
        sa.Column("fees", sa.Numeric(30, 10), nullable=False, server_default="0"),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.create_table(
        "trades",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "position_id",
            sa.Integer(),
            sa.ForeignKey("positions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "signal_id",
            sa.Integer(),
            sa.ForeignKey("signals.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("symbol", sa.String(32), nullable=False, index=True),
        sa.Column("side", side_enum, nullable=False),
        sa.Column("entry_price", sa.Numeric(24, 10), nullable=False),
        sa.Column("exit_price", sa.Numeric(24, 10), nullable=True),
        sa.Column("quantity", sa.Numeric(30, 10), nullable=False),
        sa.Column("realized_pnl", sa.Numeric(30, 10), nullable=True),
        sa.Column("fees", sa.Numeric(30, 10), nullable=False, server_default="0"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "opened_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "analytics",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("period", sa.String(32), nullable=False),
        sa.Column("metrics", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_table(
        "logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("level", sa.String(16), nullable=False),
        sa.Column("event", sa.String(256), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
            index=True,
        ),
    )


def downgrade() -> None:
    for table in [
        "logs",
        "analytics",
        "trades",
        "positions",
        "signals",
        "sentiment",
        "news",
        "market_data",
    ]:
        op.drop_table(table)
    op.execute("DROP TYPE IF EXISTS position_status")
    op.execute("DROP TYPE IF EXISTS position_side")
    op.execute("DROP TYPE IF EXISTS signal_action")
