from __future__ import annotations

from decimal import Decimal

from app.db.models import Position, PositionSide, PositionStatus
from app.services.paper_trading import PaperTradingEngine, calculate_risk_reward_ratio


def make_position(side: PositionSide) -> Position:
    return Position(
        symbol="BTC",
        side=side,
        status=PositionStatus.OPEN,
        entry_price=Decimal("100"),
        quantity=Decimal("2"),
        leverage=1,
        stop_loss=Decimal("95") if side == PositionSide.LONG else Decimal("105"),
        take_profit=Decimal("110") if side == PositionSide.LONG else Decimal("90"),
        fees=Decimal("0.09"),
    )


def test_calculate_realized_pnl_for_long() -> None:
    position = make_position(PositionSide.LONG)
    pnl, exit_fee = PaperTradingEngine.calculate_realized_pnl(position, 110)

    assert exit_fee == Decimal("0.09900")
    assert pnl == Decimal("19.81100")


def test_calculate_realized_pnl_for_short() -> None:
    position = make_position(PositionSide.SHORT)
    pnl, exit_fee = PaperTradingEngine.calculate_realized_pnl(position, 90)

    assert exit_fee == Decimal("0.08100")
    assert pnl == Decimal("19.82900")


def test_stop_and_take_profit_reasons() -> None:
    long_position = make_position(PositionSide.LONG)
    short_position = make_position(PositionSide.SHORT)

    assert PaperTradingEngine.close_reason(long_position, 94) == "Paper stop loss triggered."
    assert PaperTradingEngine.close_reason(long_position, 111) == "Paper take profit triggered."
    assert PaperTradingEngine.close_reason(short_position, 106) == "Paper stop loss triggered."
    assert PaperTradingEngine.close_reason(short_position, 89) == "Paper take profit triggered."
    assert PaperTradingEngine.close_reason(long_position, 100) is None


def test_calculate_risk_reward_ratio() -> None:
    assert calculate_risk_reward_ratio(100, 99, 102, PositionSide.LONG) == 2.0
    assert calculate_risk_reward_ratio(100, 101, 98, PositionSide.SHORT) == 2.0
    assert calculate_risk_reward_ratio(100, None, 102, PositionSide.LONG) is None
    assert calculate_risk_reward_ratio(100, 101, 102, PositionSide.LONG) is None
