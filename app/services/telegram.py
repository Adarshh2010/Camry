from __future__ import annotations

import asyncio
import json
import os
import logging
from urllib import error, request

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)
TELEGRAM_HTTP_TIMEOUT_SECONDS = float(os.getenv("TELEGRAM_HTTP_TIMEOUT_SECONDS", "6"))


def _telegram_credentials() -> tuple[str | None, str | None]:
    return os.getenv("TELEGRAM_BOT_TOKEN"), os.getenv("TELEGRAM_CHAT_ID")


async def send_telegram_message(text: str) -> bool:
    return await TelegramNotifier().send(text)


class TelegramNotifier:
    async def send(self, message: str, chat_id: str | int | None = None) -> bool:
        bot_token, default_chat_id = _telegram_credentials()
        target_chat_id = chat_id or default_chat_id
        if not bot_token or not target_chat_id:
            logger.info("telegram_skipped: missing_credentials")
            return False
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = {
            "chat_id": target_chat_id,
            "text": message,
            "disable_web_page_preview": True,
        }
        logger.info(
            "telegram_send_message_start",
            extra={"chat_id": str(target_chat_id), "message_length": len(message)},
        )
        response = await asyncio.to_thread(_post_json, url, payload)
        ok = bool(response.get("ok"))
        logger.info(
            "telegram_send_message_complete",
            extra={"chat_id": str(target_chat_id), "ok": ok, "error": response.get("description")},
        )
        return ok

    async def set_commands(self) -> bool:
        bot_token, _ = _telegram_credentials()
        if not bot_token:
            logger.info("telegram_commands_skipped: missing_bot_token")
            return False
        url = f"https://api.telegram.org/bot{bot_token}/setMyCommands"
        payload = {
            "commands": [
                {"command": "status", "description": "System and dYdX connection status"},
                {"command": "balance", "description": "dYdX testnet balance and margin"},
                {"command": "positions", "description": "Open dYdX and paper positions"},
                {"command": "signals", "description": "Latest stored trading signals"},
                {"command": "performance", "description": "Paper trading performance"},
            ]
        }
        response = await asyncio.to_thread(_post_json, url, payload)
        logger.info(
            "telegram_set_commands_complete",
            extra={"ok": response.get("ok"), "error": response.get("description")},
        )
        return bool(response.get("ok"))

    async def get_updates(self, offset: int | None = None, timeout: int = 0) -> dict:
        bot_token, _ = _telegram_credentials()
        if not bot_token:
            return {"ok": False, "description": "missing TELEGRAM_BOT_TOKEN"}
        url = f"https://api.telegram.org/bot{bot_token}/getUpdates"
        payload = {"timeout": timeout, "allowed_updates": ["message", "edited_message"]}
        if offset is not None:
            payload["offset"] = offset
        response = await asyncio.to_thread(_post_json, url, payload)
        logger.info(
            "telegram_get_updates_complete",
            extra={
                "ok": response.get("ok"),
                "count": len(response.get("result") or []),
                "error": response.get("description"),
            },
        )
        return response

    async def get_webhook_info(self) -> dict:
        bot_token, _ = _telegram_credentials()
        if not bot_token:
            return {"ok": False, "description": "missing TELEGRAM_BOT_TOKEN"}
        url = f"https://api.telegram.org/bot{bot_token}/getWebhookInfo"
        response = await asyncio.to_thread(_get_json, url)
        result = response.get("result") if isinstance(response, dict) else None
        logger.info(
            "telegram_get_webhook_info_complete",
            extra={
                "ok": response.get("ok"),
                "webhook_url_configured": bool(result.get("url")) if isinstance(result, dict) else False,
                "pending_update_count": result.get("pending_update_count") if isinstance(result, dict) else None,
                "last_error_message": result.get("last_error_message") if isinstance(result, dict) else None,
            },
        )
        return response

    async def trade_opened(self, symbol: str, side: str, quantity: str, entry_price: str) -> bool:
        return await self.send(
            f"Trade Opened\nMode: PAPER\n{side} {symbol}\n"
            f"Quantity: {quantity}\nEntry: {entry_price}"
        )

    async def paper_trade_opened(
        self,
        symbol: str,
        side: str,
        quantity: str,
        entry_price: str,
        stop_loss: str,
        take_profit: str,
        risk_reward: str,
    ) -> bool:
        return await self.send(
            "Paper Trade Opened\n\n"
            f"Symbol: {symbol}\n"
            f"Side: {side}\n"
            f"Quantity: {quantity}\n"
            f"Entry: {entry_price}\n"
            f"Stop loss: {stop_loss}\n"
            f"Take profit: {take_profit}\n"
            f"Risk/reward: {risk_reward}\n\n"
            "Mode: PAPER ONLY"
        )

    async def trade_closed(self, symbol: str, side: str, exit_price: str, pnl: str) -> bool:
        return await self.send(
            f"Trade Closed\nMode: PAPER\n{side} {symbol}\nExit: {exit_price}\nPnL: {pnl}"
        )

    async def paper_trade_closed(
        self,
        symbol: str,
        side: str,
        exit_price: str,
        pnl: str,
        reason: str,
    ) -> bool:
        if "take profit" in reason.lower():
            title = "Paper TP Hit"
        elif "stop loss" in reason.lower():
            title = "Paper SL Hit"
        else:
            title = "Paper Trade Closed"
        return await self.send(
            f"{title}\n\n"
            f"Symbol: {symbol}\n"
            f"Side: {side}\n"
            f"Exit: {exit_price}\n"
            f"PnL: {pnl}\n"
            f"Reason: {reason}\n\n"
            "Mode: PAPER ONLY"
        )

    async def daily_summary(
        self, total_pnl: float, win_rate: float, open_count: int, closed_count: int
    ) -> bool:
        return await self.send(
            "Daily Summary\n"
            "Mode: PAPER\n"
            f"Total PnL: {total_pnl:.2f}\n"
            f"Win rate: {win_rate:.2%}\n"
            f"Open positions: {open_count}\n"
            f"Closed positions: {closed_count}"
        )

    async def error_alert(self, source: str, message: str) -> bool:
        return await self.send(f"Error Alert\nSource: {source}\n{message}")

    async def agent_decision(
        self,
        symbol: str,
        decision: str,
        confidence: float,
        reasoning: str,
    ) -> bool:
        return await self.send(
            "Agent Decision\n"
            f"Symbol: {symbol}\n"
            f"Decision: {decision}\n"
            f"Confidence: {confidence:.2%}\n"
            f"Reasoning: {reasoning}"
        )

    async def signal_detected(
        self,
        symbol: str,
        decision: str,
        confidence: float,
        reasoning: str,
    ) -> bool:
        return await self.send(
            "Signal Detected\n\n"
            f"{symbol} {decision}\n\n"
            f"Confidence: {confidence:.0%}\n\n"
            "Reasoning:\n"
            f"{reasoning}\n\n"
            "Paper mode: LONG/SHORT signals open simulated trades automatically.\n"
            "No real exchange execution."
        )

    async def signal_daily_report(self, report: dict) -> bool:
        patterns = report.get("top_reasoning_patterns") or []
        pattern_lines = "\n".join(
            f"- {item['pattern']} ({item['count']})" for item in patterns[:5]
        )
        if not pattern_lines:
            pattern_lines = "- None"
        return await self.send(
            "Daily Signal Report\n\n"
            f"Total signals: {report['total_signals']}\n"
            f"LONG count: {report['long_count']}\n"
            f"SHORT count: {report['short_count']}\n"
            f"NO_TRADE count: {report['no_trade_count']}\n"
            f"Average confidence: {report['average_confidence']:.0%}\n\n"
            "Top reasoning patterns:\n"
            f"{pattern_lines}\n\n"
            "Mode: PAPER TRADING ONLY"
        )

    async def performance_report(self, metrics: dict) -> bool:
        return await self.send(
            "Paper Performance\n\n"
            f"Closed trades: {metrics.get('closed_trades', metrics.get('trades', 0))}\n"
            f"Win rate: {metrics.get('win_rate', 0):.2%}\n"
            f"Average win: {metrics.get('average_win', 0):.2f}\n"
            f"Average loss: {metrics.get('average_loss', 0):.2f}\n"
            f"Profit factor: {metrics.get('profit_factor', 0):.2f}\n"
            f"Max drawdown: {metrics.get('max_drawdown', 0):.2f}\n"
            f"Total PnL: {metrics.get('total_pnl', 0):.2f}"
        )


def _post_json(url: str, payload: dict[str, object]) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    return _request_json(req)


def _get_json(url: str) -> dict:
    req = request.Request(url, method="GET")
    return _request_json(req)


def _request_json(req: request.Request) -> dict:
    try:
        with request.urlopen(req, timeout=TELEGRAM_HTTP_TIMEOUT_SECONDS) as response:
            payload = json.loads(response.read().decode("utf-8"))
            return payload if isinstance(payload, dict) else {"ok": False, "result": payload}
    except (TimeoutError, OSError, error.URLError, error.HTTPError) as exc:
        logger.warning("telegram_send_failed: %s", exc)
        return {"ok": False, "description": str(exc)}
