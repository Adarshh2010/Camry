from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from app.db.models import PositionSide, Trade
from app.services.analytics import compute_trade_metrics


def make_trade(pnl: str) -> Trade:
    return Trade(
        symbol="BTC",
        side=PositionSide.LONG,
        entry_price=Decimal("100"),
        exit_price=Decimal("101"),
        quantity=Decimal("1"),
        realized_pnl=Decimal(pnl),
        fees=Decimal("0"),
        closed_at=datetime(2026, 6, 14, tzinfo=UTC),
    )


def test_compute_trade_metrics() -> None:
    metrics = compute_trade_metrics([make_trade("10"), make_trade("-5"), make_trade("15")])

    assert metrics["trades"] == 3
    assert metrics["win_rate"] == 2 / 3
    assert metrics["profit_factor"] == 5
    assert metrics["average_trade"] == 20 / 3
    assert metrics["daily_performance"]["2026-06-14"] == 20
