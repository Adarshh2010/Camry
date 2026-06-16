from __future__ import annotations

from app.services.risk import RiskEngine


def test_risk_engine_caps_leverage_and_sizes_to_one_percent_risk() -> None:
    engine = RiskEngine()
    result = engine.assess(
        equity=10_000,
        daily_pnl=0,
        open_positions=0,
        entry_price=100,
        side="LONG",
        leverage=10,
    )

    assert result.allowed is True
    assert result.leverage == 3
    assert result.stop_loss == 99
    assert result.suggested_quantity == 100
    assert result.max_position_notional == 10_000


def test_risk_engine_blocks_daily_loss() -> None:
    engine = RiskEngine()
    result = engine.assess(
        equity=10_000,
        daily_pnl=-300,
        open_positions=0,
        entry_price=100,
        side="LONG",
    )

    assert result.allowed is False
    assert result.reason == "Max daily loss reached."


def test_risk_engine_blocks_emergency_shutdown() -> None:
    engine = RiskEngine(emergency_shutdown=True)
    result = engine.assess(
        equity=10_000,
        daily_pnl=0,
        open_positions=0,
        entry_price=100,
        side="SHORT",
    )

    assert result.allowed is False
    assert "Emergency" in result.reason
