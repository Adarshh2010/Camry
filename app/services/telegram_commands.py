from __future__ import annotations

import asyncio
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import logger
from app.db.repositories import current_positions, latest_signals
from app.services.analytics import AnalyticsService
from app.services.dydx import DydxTestnetClient
from app.services.telegram import TelegramNotifier


SUPPORTED_COMMANDS = {"/status", "/balance", "/positions", "/signals", "/performance"}


class TelegramCommandService:
    def __init__(self) -> None:
        self.telegram = TelegramNotifier()
        self.dydx = DydxTestnetClient()

    async def handle_update(self, session: AsyncSession, update: dict) -> dict:
        update_id = update.get("update_id")
        message = update.get("message") or update.get("edited_message") or {}
        chat = message.get("chat") or {}
        chat_id = chat.get("id")
        text_value = str(message.get("text") or "").strip()
        command = normalize_command(text_value)
        logger.info(
            "telegram_webhook_update_received",
            update_id=update_id,
            chat_id=str(chat_id) if chat_id else None,
            has_text=bool(text_value),
            command=command or None,
        )
        if not chat_id or not command:
            logger.info("telegram_command_ignored", update_id=update_id, reason="no_command")
            return {"handled": False, "reason": "no_command"}
        if not self._authorized_chat(chat_id):
            await self.telegram.send("Unauthorized chat.", chat_id=chat_id)
            logger.warning(
                "telegram_command_unauthorized",
                update_id=update_id,
                chat_id=str(chat_id),
                command=command,
            )
            return {"handled": False, "reason": "unauthorized_chat"}
        if command not in SUPPORTED_COMMANDS:
            await self.telegram.send(command_help(), chat_id=chat_id)
            logger.info(
                "telegram_command_unsupported",
                update_id=update_id,
                chat_id=str(chat_id),
                command=command,
            )
            return {"handled": False, "reason": "unsupported_command", "command": command}

        logger.info(
            "telegram_command_dispatch",
            update_id=update_id,
            chat_id=str(chat_id),
            command=command,
        )
        try:
            response = await asyncio.wait_for(self._run_command(session, command), timeout=25)
        except TimeoutError:
            response = f"{command} timed out while reading live data. Try again shortly."
            logger.warning(
                "telegram_command_timeout",
                update_id=update_id,
                chat_id=str(chat_id),
                command=command,
            )
        sent = await self.telegram.send(response, chat_id=chat_id)
        logger.info(
            "telegram_command_reply_complete",
            update_id=update_id,
            chat_id=str(chat_id),
            command=command,
            sent=sent,
        )
        return {"handled": True, "command": command, "sent": sent}

    async def _run_command(self, session: AsyncSession, command: str) -> str:
        if command == "/status":
            return await self.status(session)
        if command == "/balance":
            return await self.balance()
        if command == "/positions":
            return await self.positions(session)
        if command == "/performance":
            return await self.performance(session)
        return await self.signals(session)

    async def status(self, session: AsyncSession) -> str:
        try:
            await session.execute(text("SELECT 1"))
            database = "Connected"
        except Exception:
            database = "Disconnected"
        exchange = await self.dydx.status()
        scheduler = "Enabled" if settings.decision_scheduler_enabled else "Disabled"
        return (
            "Status\n\n"
            f"App: {settings.app_name}\n"
            f"Mode: {settings.trading_mode.upper()}\n"
            f"Paper trading: {settings.is_paper_trading}\n"
            f"Database: {database}\n"
            f"dYdX: {exchange.get('connection_status')}\n"
            f"Wallet: {shorten(exchange.get('wallet_address'))}\n"
            f"Subaccount: {exchange.get('subaccount_number')}\n"
            f"Decision scheduler: {scheduler}\n"
            "Auto execution: Paper trades only\n"
            "Real exchange execution: Disabled"
        )

    async def balance(self) -> str:
        try:
            account = await self.dydx.account_summary()
        except Exception as exc:
            return f"Balance\n\ndYdX: Disconnected\nReason: {exc}"
        return (
            "Balance\n\n"
            f"Wallet: {shorten(account.get('wallet_address'))}\n"
            f"Subaccount: {account.get('subaccount_number')}\n"
            f"Balance: {fmt_money(account.get('balance'))}\n"
            f"Equity: {fmt_money(account.get('equity'))}\n"
            f"Available margin: {fmt_money(account.get('available_margin'))}\n"
            "Network: dYdX testnet"
        )

    async def positions(self, session: AsyncSession) -> str:
        dydx_positions: list[dict]
        try:
            payload = await self.dydx.open_positions()
            dydx_positions = payload.get("positions", [])
        except Exception:
            dydx_positions = []
        paper_positions = await current_positions(session)
        dydx_lines = [
            format_dydx_position(position)
            for position in dydx_positions[:5]
            if isinstance(position, dict)
        ]
        paper_lines = [
            f"{position.symbol} {position.side.value} qty={position.quantity} entry={position.entry_price}"
            for position in paper_positions[:5]
        ]
        return (
            "Positions\n\n"
            f"dYdX open: {len(dydx_positions)}\n"
            + ("\n".join(dydx_lines) if dydx_lines else "No dYdX open positions.")
            + "\n\n"
            f"Paper open: {len(paper_positions)}\n"
            + ("\n".join(paper_lines) if paper_lines else "No paper open positions.")
        )

    async def signals(self, session: AsyncSession) -> str:
        rows = await latest_signals(session, limit=5)
        if not rows:
            return "Signals\n\nNo stored signals yet."
        lines = [
            (
                f"{row.symbol} {row.action.value} "
                f"confidence={float(row.confidence):.0%} "
                f"id={row.id}\n{trim(row.reasoning, 160)}"
            )
            for row in rows
        ]
        return "Signals\n\n" + "\n\n".join(lines)

    async def performance(self, session: AsyncSession) -> str:
        metrics = await AnalyticsService().compute_and_store(session)
        return (
            "Paper Performance\n\n"
            f"Closed trades: {metrics.get('closed_trades', metrics.get('trades', 0))}\n"
            f"Win rate: {metrics.get('win_rate', 0):.2%}\n"
            f"Average win: {metrics.get('average_win', 0):.2f}\n"
            f"Average loss: {metrics.get('average_loss', 0):.2f}\n"
            f"Profit factor: {metrics.get('profit_factor', 0):.2f}\n"
            f"Max drawdown: {metrics.get('max_drawdown', 0):.2f}\n"
            f"Total PnL: {metrics.get('total_pnl', 0):.2f}"
        )

    def _authorized_chat(self, chat_id: int | str) -> bool:
        configured = settings.telegram_chat_id
        return not configured or str(chat_id) == str(configured)


def normalize_command(text_value: str) -> str:
    if not text_value.startswith("/"):
        return ""
    first = text_value.split(maxsplit=1)[0]
    command = first.split("@", 1)[0]
    return command.lower()


def command_help() -> str:
    return "Commands\n/status\n/balance\n/positions\n/signals\n/performance"


def shorten(value: object) -> str:
    text_value = str(value or "not configured")
    if len(text_value) <= 14:
        return text_value
    return f"{text_value[:8]}...{text_value[-6:]}"


def fmt_money(value: object) -> str:
    if value is None:
        return "n/a"
    try:
        return f"${Decimal(str(value)):,.2f}"
    except Exception:
        return str(value)


def format_dydx_position(position: dict) -> str:
    return (
        f"{position.get('market')} {position.get('side')} "
        f"size={position.get('size')} entry={position.get('entryPrice')} "
        f"uPnL={position.get('unrealizedPnl')}"
    )


def trim(value: str, limit: int) -> str:
    normalized = " ".join(value.split())
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[: limit - 3]}..."
