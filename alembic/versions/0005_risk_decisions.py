"""add risk decisions table

Revision ID: 0005_risk_decisions
Revises: 0004_dydx_test_trades
Create Date: 2026-06-15
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0005_risk_decisions"
down_revision = "0004_dydx_test_trades"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "risk_decisions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("symbol", sa.String(32), nullable=False, index=True),
        sa.Column("decision", sa.String(32), nullable=False, index=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("daily_pnl", sa.Numeric(30, 10), nullable=False),
        sa.Column("open_positions", sa.Integer(), nullable=False),
        sa.Column("remaining_risk_budget", sa.Numeric(30, 10), nullable=False),
        sa.Column("trading_enabled", sa.Boolean(), nullable=False),
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
    op.drop_table("risk_decisions")
