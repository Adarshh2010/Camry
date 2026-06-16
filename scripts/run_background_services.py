from __future__ import annotations

import asyncio
import signal
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.logging import configure_logging, logger
from app.services.paper_trade_monitor import PaperTradeMonitor
from app.services.decision_scheduler import DecisionCycleScheduler
from app.services.telegram_poller import TelegramCommandPoller


async def main() -> None:
    configure_logging()
    stop_event = asyncio.Event()
    poller = TelegramCommandPoller()
    scheduler = DecisionCycleScheduler()
    paper_monitor = PaperTradeMonitor()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop_event.set)

    poller.start()
    scheduler.start()
    paper_monitor.start()
    logger.info(
        "background_services_started",
        telegram_poller=True,
        btc_scheduler=True,
        paper_trade_monitor=True,
    )
    await stop_event.wait()
    await paper_monitor.stop()
    await poller.stop()
    await scheduler.stop()
    logger.info("background_services_stopped")


if __name__ == "__main__":
    asyncio.run(main())
