from __future__ import annotations

import asyncio
from contextlib import suppress
from datetime import UTC, date, datetime

from app.core.config import settings
from app.core.logging import logger
from app.db.repositories import log_event
from app.db.session import SessionLocal
from app.services.orchestrator import ResearchOrchestrator
from app.services.signal_reports import SignalReportService
from app.services.telegram import TelegramNotifier


class DecisionCycleScheduler:
    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()
        self._last_report_date: date | None = None

    def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._task = asyncio.create_task(self._run(), name="btc-decision-cycle-scheduler")

    async def stop(self) -> None:
        self._stop.set()
        if self._task is None:
            return
        self._task.cancel()
        with suppress(asyncio.CancelledError):
            await self._task

    async def _run(self) -> None:
        interval = max(settings.decision_scheduler_interval_seconds, 60)
        symbol = settings.decision_scheduler_symbol
        logger.info(
            "decision_scheduler_started",
            symbol=symbol,
            interval_seconds=interval,
            auto_execute="paper_only",
        )
        while not self._stop.is_set():
            started_at = datetime.now(UTC)
            await self._run_once(symbol)
            await self._send_daily_report_if_due(started_at)
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=interval)
            except TimeoutError:
                continue

    async def _run_once(self, symbol: str) -> None:
        try:
            async with SessionLocal() as session:
                result = await ResearchOrchestrator().run_decision_cycle(session, symbol)
                await log_event(
                    session,
                    "INFO",
                    "scheduled_decision_cycle_complete",
                    {
                        "symbol": symbol,
                        "signal_id": result.get("signal_id"),
                        "action": result.get("decision", {}).get("action"),
                        "paper_trade_only": True,
                        "auto_execute": "paper_only",
                    },
                )
        except Exception as exc:
            logger.warning("scheduled_decision_cycle_failed", symbol=symbol, error=str(exc))
            await TelegramNotifier().error_alert("scheduled_decision_cycle", str(exc))

    async def _send_daily_report_if_due(self, now: datetime) -> None:
        if now.hour != 0:
            return
        if self._last_report_date == now.date():
            return
        self._last_report_date = now.date()
        try:
            async with SessionLocal() as session:
                await SignalReportService().daily_report(session, now=now, send_telegram=True)
        except Exception as exc:
            logger.warning("daily_signal_report_failed", error=str(exc))
            await TelegramNotifier().error_alert("daily_signal_report", str(exc))
