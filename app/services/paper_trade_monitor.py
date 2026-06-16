from __future__ import annotations

import asyncio
from contextlib import suppress

from app.core.config import settings
from app.core.logging import logger
from app.db.repositories import current_positions, latest_market_rows
from app.db.session import SessionLocal
from app.services.analytics import AnalyticsService
from app.services.paper_trading import PaperTradingEngine
from app.services.telegram import TelegramNotifier


class PaperTradeMonitor:
    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()

    def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._task = asyncio.create_task(self._run(), name="paper-trade-monitor")

    async def stop(self) -> None:
        self._stop.set()
        if self._task is None:
            return
        self._task.cancel()
        with suppress(asyncio.CancelledError):
            await self._task

    async def _run(self) -> None:
        interval = max(settings.paper_trade_monitor_interval_seconds, 10)
        logger.info("paper_trade_monitor_started", interval_seconds=interval)
        while not self._stop.is_set():
            await self._run_once()
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=interval)
            except TimeoutError:
                continue

    async def _run_once(self) -> None:
        try:
            async with SessionLocal() as session:
                positions = await current_positions(session)
                prices: dict[str, float] = {}
                for position in positions:
                    rows = await latest_market_rows(session, position.symbol, limit=1)
                    if rows:
                        prices[position.symbol] = float(rows[0].close)
                closed = await PaperTradingEngine().evaluate_stops(session, prices)
                for position in closed:
                    await TelegramNotifier().paper_trade_closed(
                        position.symbol,
                        position.side.value,
                        str(position.exit_price),
                        str(position.realized_pnl),
                        close_reason_text(position),
                    )
                if closed:
                    metrics = await AnalyticsService().compute_and_store(session)
                    logger.info(
                        "paper_trade_monitor_closed_positions",
                        closed_count=len(closed),
                        total_pnl=metrics.get("total_pnl"),
                    )
        except Exception as exc:
            logger.warning("paper_trade_monitor_failed", error=str(exc))
            await TelegramNotifier().error_alert("paper_trade_monitor", str(exc))


def close_reason_text(position) -> str:
    if position.extra and isinstance(position.extra, dict):
        reason = position.extra.get("last_close_reason")
        if reason:
            return str(reason)
    return "Paper close."
