from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories import daily_dydx_test_pnl, latest_dydx_loss, store_risk_decision
from app.services.dydx import DydxTestnetClient


SYMBOL = "BTC-USD"
MAX_OPEN_POSITIONS = 1
MAX_ACCOUNT_RISK = Decimal("0.01")
DAILY_LOSS_LIMIT = Decimal("0.03")
LOSS_COOLDOWN = timedelta(minutes=15)


class RiskEngineV1:
    def __init__(self) -> None:
        self.exchange = DydxTestnetClient()

    async def status(self, session: AsyncSession) -> dict:
        account = await self.exchange.account_summary()
        equity = Decimal(str(account.get("equity") or "0"))
        daily_pnl = await daily_dydx_test_pnl(session)
        positions = account.get("open_positions", [])
        btc_positions = [position for position in positions if position.get("market") == SYMBOL]
        open_position_count = len([position for position in btc_positions if has_open_size(position)])
        daily_loss_limit_amount = equity * DAILY_LOSS_LIMIT
        max_risk_amount = equity * MAX_ACCOUNT_RISK
        remaining_daily_loss_budget = daily_loss_limit_amount + daily_pnl
        remaining_risk_budget = min(max_risk_amount, max(Decimal("0"), remaining_daily_loss_budget))
        latest_loss = await latest_dydx_loss(session)
        cooldown_until = None
        if latest_loss and latest_loss.closed_at:
            cooldown_until = latest_loss.closed_at + LOSS_COOLDOWN
        reasons = []
        if open_position_count >= MAX_OPEN_POSITIONS:
            reasons.append("Maximum 1 open position reached.")
        if daily_pnl <= -daily_loss_limit_amount:
            reasons.append("Daily loss limit reached.")
        if cooldown_until and datetime.now(UTC) < cooldown_until:
            reasons.append("Cooldown active after loss.")
        if not btc_positions:
            stop_required = True
            take_profit_required = True
        else:
            stop_required = True
            take_profit_required = True
            reasons.append("Hard stop loss and take profit must be attached before new entries.")
        trading_enabled = not reasons
        payload = {
            "symbol": SYMBOL,
            "rules": {
                "btc_only": True,
                "max_open_positions": MAX_OPEN_POSITIONS,
                "max_account_risk": str(MAX_ACCOUNT_RISK),
                "daily_loss_limit": str(DAILY_LOSS_LIMIT),
                "cooldown_minutes_after_loss": 15,
                "hard_stop_loss_required": stop_required,
                "hard_take_profit_required": take_profit_required,
            },
            "daily_pnl": str(daily_pnl),
            "account_equity": str(equity),
            "open_positions": open_position_count,
            "remaining_risk_budget": str(remaining_risk_budget),
            "trading_enabled": trading_enabled,
            "trading_status": "enabled" if trading_enabled else "disabled",
            "reasons": reasons or ["Risk checks passed."],
            "cooldown_until": cooldown_until.isoformat() if cooldown_until else None,
            "raw_open_positions": btc_positions,
        }
        await store_risk_decision(
            session=session,
            symbol=SYMBOL,
            decision="ALLOW" if trading_enabled else "BLOCK",
            reason="; ".join(payload["reasons"]),
            daily_pnl=daily_pnl,
            open_positions=open_position_count,
            remaining_risk_budget=remaining_risk_budget,
            trading_enabled=trading_enabled,
            payload=payload,
        )
        return payload


def has_open_size(position: dict) -> bool:
    try:
        return Decimal(str(position.get("size") or "0")) != 0
    except Exception:
        return False
