from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories import store_risk_decision
from app.db.session import get_session
from app.services.risk_v1 import SYMBOL, RiskEngineV1

router = APIRouter()


@router.get("/risk/status")
async def risk_status(session: AsyncSession = Depends(get_session)) -> dict:
    try:
        return await RiskEngineV1().status(session)
    except ValueError as exc:
        payload = {
            "symbol": SYMBOL,
            "daily_pnl": "0",
            "open_positions": 0,
            "remaining_risk_budget": "0",
            "trading_enabled": False,
            "trading_status": "disabled",
            "reasons": [str(exc)],
        }
        await store_risk_decision(
            session=session,
            symbol=SYMBOL,
            decision="BLOCK",
            reason=str(exc),
            daily_pnl=Decimal("0"),
            open_positions=0,
            remaining_risk_budget=Decimal("0"),
            trading_enabled=False,
            payload=payload,
        )
        return payload
