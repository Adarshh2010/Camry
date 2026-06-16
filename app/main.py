from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes.exchange import router as exchange_router
from app.api.routes.research import router as research_router
from app.api.routes.risk import router as risk_router
from app.api.routes.system import router as system_router
from app.api.routes.telegram import router as telegram_router
from app.core.config import settings
from app.core.logging import configure_logging, logger
from app.db import models  # noqa: F401
from app.db.base import Base
from app.db.session import engine
from app.services.decision_scheduler import DecisionCycleScheduler
from app.services.paper_trade_monitor import PaperTradeMonitor
from app.services.telegram_poller import TelegramCommandPoller


decision_scheduler = DecisionCycleScheduler()
telegram_command_poller = TelegramCommandPoller()
paper_trade_monitor = PaperTradeMonitor()


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    logger.info("app_starting", trading_mode=settings.trading_mode)
    if settings.auto_create_tables:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        logger.info("database_tables_created")
    if settings.decision_scheduler_enabled:
        decision_scheduler.start()
        logger.info(
            "decision_scheduler_enabled",
            symbol=settings.decision_scheduler_symbol,
            interval_seconds=settings.decision_scheduler_interval_seconds,
            auto_execute=False,
        )
    if settings.telegram_command_polling_enabled:
        telegram_command_poller.start()
        logger.info(
            "telegram_command_polling_enabled",
            interval_seconds=settings.telegram_command_polling_interval_seconds,
        )
    if settings.paper_trade_monitor_enabled:
        paper_trade_monitor.start()
        logger.info(
            "paper_trade_monitor_enabled",
            interval_seconds=settings.paper_trade_monitor_interval_seconds,
        )
    yield
    await decision_scheduler.stop()
    await telegram_command_poller.stop()
    await paper_trade_monitor.stop()
    logger.info("app_stopping")


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="AI-powered Hyperliquid research and paper-trading backend.",
    lifespan=lifespan,
)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "trading_mode": settings.trading_mode}


app.include_router(system_router, prefix="/api", tags=["system"])
app.include_router(exchange_router, prefix="/api", tags=["exchange"])
app.include_router(research_router, prefix="/api", tags=["research"])
app.include_router(risk_router, prefix="/api", tags=["risk"])
app.include_router(telegram_router, prefix="/api", tags=["telegram"])
