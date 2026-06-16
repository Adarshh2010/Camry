from __future__ import annotations

import asyncio
from contextlib import suppress

from app.core.config import settings
from app.core.logging import logger
from app.db.session import SessionLocal
from app.services.telegram import TelegramNotifier
from app.services.telegram_commands import TelegramCommandService


class TelegramCommandPoller:
    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()
        self._offset: int | None = None

    def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._task = asyncio.create_task(self._run(), name="telegram-command-poller")

    async def stop(self) -> None:
        self._stop.set()
        if self._task is None:
            return
        self._task.cancel()
        with suppress(asyncio.CancelledError):
            await self._task

    async def _run(self) -> None:
        notifier = TelegramNotifier()
        try:
            webhook_info = await asyncio.wait_for(notifier.get_webhook_info(), timeout=8)
        except TimeoutError:
            webhook_info = {"ok": False, "description": "webhook info timed out"}
            logger.warning("telegram_webhook_info_timeout_polling_anyway")
        webhook_result = webhook_info.get("result") if isinstance(webhook_info, dict) else {}
        webhook_url = webhook_result.get("url") if isinstance(webhook_result, dict) else None
        if webhook_url:
            logger.info(
                "telegram_command_poller_skipped_webhook_configured",
                pending_update_count=webhook_result.get("pending_update_count"),
            )
            return

        interval = max(settings.telegram_command_polling_interval_seconds, 1)
        logger.info("telegram_command_poller_started", interval_seconds=interval)
        while not self._stop.is_set():
            await self._poll_once(notifier)
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=interval)
            except TimeoutError:
                continue

    async def _poll_once(self, notifier: TelegramNotifier) -> None:
        try:
            response = await asyncio.wait_for(
                notifier.get_updates(offset=self._offset, timeout=0),
                timeout=8,
            )
        except TimeoutError:
            logger.warning("telegram_command_poll_timeout")
            return
        if not response.get("ok"):
            logger.warning("telegram_command_poll_failed", error=response.get("description"))
            return
        updates = response.get("result") or []
        if not updates:
            return
        logger.info("telegram_command_poll_updates_received", count=len(updates))
        for update in updates:
            update_id = update.get("update_id")
            if update_id is not None:
                self._offset = int(update_id) + 1
            try:
                async with SessionLocal() as session:
                    result = await TelegramCommandService().handle_update(session, update)
                    logger.info(
                        "telegram_command_poll_update_complete",
                        update_id=update_id,
                        result=result,
                    )
            except Exception as exc:
                logger.exception(
                    "telegram_command_poll_update_failed",
                    update_id=update_id,
                    error=str(exc),
                )
                await notifier.error_alert("telegram_command_poll", str(exc))
