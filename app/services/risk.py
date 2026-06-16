from __future__ import annotations

from dataclasses import dataclass

from app.core.config import settings
from app.schemas.domain import PositionSizeResult, RiskAssessment


@dataclass
class RiskEngine:
    emergency_shutdown: bool = False

    def assess(
        self,
        equity: float,
        daily_pnl: float,
        open_positions: int,
        entry_price: float,
        side: str,
        leverage: float = 1,
    ) -> RiskAssessment:
        leverage = min(leverage, settings.max_leverage)
        if self.emergency_shutdown:
            return self._blocked(equity, "Emergency shutdown is active.", leverage)
        if daily_pnl <= -(equity * settings.max_daily_loss):
            return self._blocked(equity, "Max daily loss reached.", leverage)
        if open_positions >= settings.max_simultaneous_trades:
            return self._blocked(equity, "Max simultaneous trades reached.", leverage)
        stop_loss = self.default_stop(entry_price, side)
        take_profit = self.default_take_profit(entry_price, side)
        size = self.position_size(equity, entry_price, stop_loss, leverage)
        return RiskAssessment(
            allowed=size.quantity > 0,
            reason="Allowed within hard risk limits.",
            equity=equity,
            max_position_notional=size.notional,
            suggested_quantity=size.quantity,
            stop_loss=stop_loss,
            take_profit=take_profit,
            leverage=leverage,
        )

    def position_size(
        self,
        equity: float,
        entry_price: float,
        stop_loss: float,
        leverage: float,
    ) -> PositionSizeResult:
        leverage = min(leverage, settings.max_leverage)
        risk_amount = equity * settings.max_risk_per_trade
        per_unit_risk = abs(entry_price - stop_loss)
        quantity = 0.0 if per_unit_risk <= 0 else risk_amount / per_unit_risk
        notional = quantity * entry_price
        max_notional = equity * leverage
        if notional > max_notional:
            quantity = max_notional / entry_price
            notional = max_notional
        return PositionSizeResult(
            risk_amount=risk_amount,
            quantity=quantity,
            notional=notional,
            leverage=leverage,
        )

    @staticmethod
    def default_stop(entry_price: float, side: str) -> float:
        return entry_price * (0.99 if side == "LONG" else 1.01)

    @staticmethod
    def default_take_profit(entry_price: float, side: str) -> float:
        return entry_price * (1.02 if side == "LONG" else 0.98)

    @staticmethod
    def _blocked(equity: float, reason: str, leverage: float) -> RiskAssessment:
        return RiskAssessment(
            allowed=False,
            reason=reason,
            equity=equity,
            max_position_notional=0,
            suggested_quantity=0,
            stop_loss=None,
            take_profit=None,
            leverage=leverage,
        )
