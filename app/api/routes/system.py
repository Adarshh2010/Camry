from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import get_session

router = APIRouter()


@router.get("/status")
async def status(session: AsyncSession = Depends(get_session)) -> dict:
    await session.execute(text("SELECT 1"))
    return {
        "app": settings.app_name,
        "environment": settings.environment,
        "trading_mode": settings.trading_mode,
        "paper_trading": settings.is_paper_trading,
        "risk_limits": {
            "max_risk_per_trade": settings.max_risk_per_trade,
            "max_daily_loss": settings.max_daily_loss,
            "max_leverage": settings.max_leverage,
            "max_simultaneous_trades": settings.max_simultaneous_trades,
        },
        "database": "ok",
    }
