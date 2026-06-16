"""add trade reasoning table

Revision ID: 0002_trade_reasoning
Revises: 0001_initial
Create Date: 2026-06-14
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0002_trade_reasoning"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "trade_reasoning",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "signal_id",
            sa.Integer(),
            sa.ForeignKey("signals.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("data_time", sa.DateTime(timezone=True), nullable=False, index=True),
        sa.Column("news_score", sa.Float(), nullable=False),
        sa.Column("market_score", sa.Float(), nullable=False),
        sa.Column(
            "decision",
            postgresql.ENUM(
                "LONG",
                "SHORT",
                "NO_TRADE",
                name="signal_action",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("result", sa.String(64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("trade_reasoning")
