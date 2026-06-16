"""add exchange snapshots table

Revision ID: 0003_exchange_snapshots
Revises: 0002_trade_reasoning
Create Date: 2026-06-15
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0003_exchange_snapshots"
down_revision = "0002_trade_reasoning"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "exchange_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("exchange", sa.String(64), nullable=False, index=True),
        sa.Column("network", sa.String(64), nullable=False),
        sa.Column("wallet_address", sa.String(128), nullable=True, index=True),
        sa.Column("snapshot_type", sa.String(64), nullable=False, index=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
            index=True,
        ),
    )


def downgrade() -> None:
    op.drop_table("exchange_snapshots")
