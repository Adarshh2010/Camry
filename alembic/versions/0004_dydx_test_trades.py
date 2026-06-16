"""add dydx test trades table

Revision ID: 0004_dydx_test_trades
Revises: 0003_exchange_snapshots
Create Date: 2026-06-15
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0004_dydx_test_trades"
down_revision = "0003_exchange_snapshots"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "dydx_test_trades",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("order_id", sa.String(128), nullable=False, unique=True, index=True),
        sa.Column("close_order_id", sa.String(128), nullable=True, unique=True),
        sa.Column("symbol", sa.String(32), nullable=False, index=True),
        sa.Column("side", sa.String(16), nullable=False),
        sa.Column("size", sa.Numeric(30, 10), nullable=False),
        sa.Column("entry_price", sa.Numeric(24, 10), nullable=True),
        sa.Column("exit_price", sa.Numeric(24, 10), nullable=True),
        sa.Column("realized_pnl", sa.Numeric(30, 10), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, index=True),
        sa.Column("wallet_address", sa.String(128), nullable=True, index=True),
        sa.Column(
            "opened_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("raw", postgresql.JSONB(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("dydx_test_trades")
