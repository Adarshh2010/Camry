from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models import Position, PositionSide, PositionStatus, Signal, Trade
from app.schemas.domain import Decision, TradeAction


class PaperTradingEngine:
    async def open_position(
        self,
        session: AsyncSession,
        symbol: str,
        side: PositionSide,
        entry_price: float,
        quantity: float,
        leverage: float = 1,
        stop_loss: float | None = None,
        take_profit: float | None = None,
        signal_id: int | None = None,
        notes: str = "Paper entry.",
        metadata: dict | None = None,
    ) -> Position | None:
        if not settings.is_paper_trading:
            return None
        leverage = min(leverage, settings.max_leverage)
        fee = self.calculate_fee(entry_price, quantity)
        risk_reward = calculate_risk_reward_ratio(entry_price, stop_loss, take_profit, side)
        position_metadata = {
            **(metadata or {}),
            "paper_trade": True,
            "entry_price": entry_price,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "risk_reward": risk_reward,
        }
        position = Position(
            symbol=symbol,
            side=side,
            status=PositionStatus.OPEN,
            entry_price=Decimal(str(entry_price)),
            quantity=Decimal(str(quantity)),
            leverage=leverage,
            stop_loss=Decimal(str(stop_loss)) if stop_loss else None,
            take_profit=Decimal(str(take_profit)) if take_profit else None,
            fees=fee,
            extra=position_metadata,
        )
        session.add(position)
        await session.flush()
        session.add(
            Trade(
                position_id=position.id,
                signal_id=signal_id,
                symbol=symbol,
                side=side,
                entry_price=Decimal(str(entry_price)),
                quantity=Decimal(str(quantity)),
                fees=fee,
                notes=notes,
            )
        )
        await session.commit()
        return position

    async def execute_signal(
        self,
        session: AsyncSession,
        signal: Signal,
        decision: Decision,
        price: float,
        quantity: float,
        leverage: float,
        stop_loss: float | None,
        take_profit: float | None,
    ) -> Position | None:
        if not settings.is_paper_trading or decision.action == TradeAction.NO_TRADE:
            return None
        return await self.open_position(
            session=session,
            symbol=decision.symbol,
            side=PositionSide(decision.action.value),
            entry_price=price,
            quantity=quantity,
            leverage=leverage,
            stop_loss=stop_loss,
            take_profit=take_profit,
            signal_id=signal.id,
            notes="Paper entry from decision agent.",
            metadata={
                "decision": decision.model_dump(mode="json"),
                "decision_risk_reward": decision.risk_reward,
            },
        )

    async def close_position(
        self,
        session: AsyncSession,
        position: Position,
        exit_price: float,
        notes: str = "Paper close.",
    ) -> Position:
        if position.status != PositionStatus.OPEN:
            return position
        realized, exit_fee = self.calculate_realized_pnl(position, exit_price)
        now = datetime.now(UTC)
        position.exit_price = Decimal(str(exit_price))
        position.realized_pnl = realized
        position.fees += exit_fee
        position.status = PositionStatus.CLOSED
        position.closed_at = now
        position.extra = {**(position.extra or {}), "last_close_reason": notes}
        session.add(position)
        session.add(
            Trade(
                position_id=position.id,
                symbol=position.symbol,
                side=position.side,
                entry_price=position.entry_price,
                exit_price=Decimal(str(exit_price)),
                quantity=position.quantity,
                realized_pnl=realized,
                fees=position.fees,
                notes=notes,
                opened_at=position.opened_at,
                closed_at=now,
            )
        )
        await session.commit()
        return position

    async def evaluate_stops(
        self,
        session: AsyncSession,
        prices: dict[str, float],
    ) -> list[Position]:
        result = await session.execute(
            select(Position)
            .where(Position.status == PositionStatus.OPEN)
            .order_by(desc(Position.opened_at))
        )
        closed: list[Position] = []
        for position in result.scalars():
            price = prices.get(position.symbol)
            if price is None:
                continue
            reason = self.close_reason(position, price)
            if reason:
                closed.append(await self.close_position(session, position, price, reason))
        return closed

    @staticmethod
    def close_reason(position: Position, price: float) -> str | None:
        current = Decimal(str(price))
        if position.side == PositionSide.LONG:
            if position.stop_loss is not None and current <= position.stop_loss:
                return "Paper stop loss triggered."
            if position.take_profit is not None and current >= position.take_profit:
                return "Paper take profit triggered."
        else:
            if position.stop_loss is not None and current >= position.stop_loss:
                return "Paper stop loss triggered."
            if position.take_profit is not None and current <= position.take_profit:
                return "Paper take profit triggered."
        return None

    @staticmethod
    def calculate_fee(price: float, quantity: float) -> Decimal:
        return Decimal(str(price)) * Decimal(str(quantity)) * Decimal(str(settings.paper_fee_rate))

    @staticmethod
    def calculate_realized_pnl(position: Position, exit_price: float) -> tuple[Decimal, Decimal]:
        direction = Decimal("1") if position.side == PositionSide.LONG else Decimal("-1")
        exit_value = Decimal(str(exit_price))
        gross = (exit_value - position.entry_price) * position.quantity * direction
        exit_fee = exit_value * position.quantity * Decimal(str(settings.paper_fee_rate))
        return gross - position.fees - exit_fee, exit_fee


def calculate_risk_reward_ratio(
    entry_price: float,
    stop_loss: float | None,
    take_profit: float | None,
    side: PositionSide,
) -> float | None:
    if stop_loss is None or take_profit is None:
        return None
    entry = Decimal(str(entry_price))
    stop = Decimal(str(stop_loss))
    target = Decimal(str(take_profit))
    if side == PositionSide.LONG:
        risk = entry - stop
        reward = target - entry
    else:
        risk = stop - entry
        reward = entry - target
    if risk <= 0 or reward <= 0:
        return None
    return float(reward / risk)
