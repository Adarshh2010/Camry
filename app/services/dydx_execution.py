from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.repositories import (
    close_dydx_test_trade,
    insert_dydx_test_trade,
    latest_open_dydx_test_trade,
)
from app.services.dydx import DydxTestnetClient
from app.services.telegram import TelegramNotifier


SYMBOL = "BTC-USD"
HELPER = Path(__file__).resolve().parents[2] / "scripts" / "dydx_testnet_order.cjs"


class DydxExecutionError(RuntimeError):
    pass


class DydxTestnetExecutionService:
    def __init__(self) -> None:
        self.client = DydxTestnetClient()
        self.telegram = TelegramNotifier()

    async def open_long(self, session: AsyncSession) -> dict:
        return await self._open(session, "LONG")

    async def open_short(self, session: AsyncSession) -> dict:
        return await self._open(session, "SHORT")

    async def close_active(self, session: AsyncSession) -> dict:
        self._require_enabled()
        stored = await latest_open_dydx_test_trade(session)
        if stored is None:
            raise DydxExecutionError("No open dYdX test trade is stored locally.")
        positions = await self.client.open_positions()
        position = find_btc_position(positions.get("positions", []))
        if position is None:
            raise DydxExecutionError("No active BTC-USD position found on dYdX testnet.")
        size = abs_decimal(position.get("size") or stored.size)
        side = "SELL" if Decimal(str(position.get("size", "0"))) > 0 else "BUY"
        price = await self._btc_price()
        execution = await self._execute_order(side=side, size=size, price=price, reduce_only=True)
        pnl = estimate_pnl(stored.side, stored.entry_price, price, stored.size)
        closed = await close_dydx_test_trade(
            session=session,
            trade=stored,
            close_order_id=execution["order_id"],
            exit_price=price,
            realized_pnl=pnl,
            raw=execution,
        )
        duration = ""
        if closed.closed_at and closed.opened_at:
            duration = str(closed.closed_at - closed.opened_at)
        await self.telegram.send(
            "✅ Test Position Closed\n\n"
            f"Exit: {price}\n"
            f"PnL: {pnl}\n"
            f"Duration: {duration}"
        )
        return serialize_trade(closed)

    async def _open(self, session: AsyncSession, side: str) -> dict:
        self._require_enabled()
        if await latest_open_dydx_test_trade(session) is not None:
            raise DydxExecutionError("A dYdX test trade is already open locally.")
        summary = await self.client.account_summary()
        equity = Decimal(str(summary.get("equity") or summary.get("available_margin") or "0"))
        price = await self._btc_price()
        size = Decimal(str(settings.dydx_fixed_btc_size))
        self._check_risk(equity, price, size)
        order_side = "BUY" if side == "LONG" else "SELL"
        execution = await self._execute_order(side=order_side, size=size, price=price, reduce_only=False)
        trade = await insert_dydx_test_trade(
            session=session,
            order_id=execution["order_id"],
            symbol=SYMBOL,
            side=side,
            size=size,
            entry_price=price,
            status="OPEN",
            wallet_address=execution.get("wallet_address") or settings.dydx_wallet_address,
            raw=execution,
        )
        await self.telegram.send(
            "🚀 Test Position Opened\n\n"
            f"Symbol: {SYMBOL}\n"
            f"Side: {side}\n"
            f"Size: {size}\n"
            f"Entry: {price}"
        )
        return serialize_trade(trade)

    async def _btc_price(self) -> Decimal:
        markets = await self.client.markets()
        btc = markets["markets"].get(SYMBOL)
        if not btc or btc.get("price") is None:
            raise DydxExecutionError("BTC-USD market price is unavailable.")
        return Decimal(str(btc["price"]))

    def _check_risk(self, equity: Decimal, price: Decimal, size: Decimal) -> None:
        if equity <= 0:
            raise DydxExecutionError("Account equity is unavailable or zero.")
        notional = price * size
        max_notional = equity * Decimal(str(settings.dydx_max_account_risk))
        if notional > max_notional:
            raise DydxExecutionError(
                f"Fixed size notional {notional} exceeds max 0.25% account risk {max_notional}."
            )

    def _require_enabled(self) -> None:
        if not settings.dydx_enable_testnet_execution:
            raise DydxExecutionError("Set DYDX_ENABLE_TESTNET_EXECUTION=true to enable manual tests.")
        if "v4testnet" not in settings.dydx_indexer_url:
            raise DydxExecutionError("dYdX execution is restricted to testnet.")
        if not settings.dydx_test_mnemonic:
            raise DydxExecutionError("DYDX_TEST_MNEMONIC is required for signed testnet orders.")

    async def _execute_order(
        self,
        side: str,
        size: Decimal,
        price: Decimal,
        reduce_only: bool,
    ) -> dict:
        request = {
            "symbol": SYMBOL,
            "side": side,
            "size": str(size),
            "price": str(price),
            "reduce_only": reduce_only,
        }
        process = await asyncio.create_subprocess_exec(
            "node",
            str(HELPER),
            json.dumps(request),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        if process.returncode != 0:
            detail = stderr.decode().strip() or stdout.decode().strip()
            raise DydxExecutionError(detail or "dYdX order helper failed.")
        return json.loads(stdout.decode())


def find_btc_position(positions: list[dict]) -> dict | None:
    for position in positions:
        if position.get("market") == SYMBOL or position.get("ticker") == SYMBOL:
            size = Decimal(str(position.get("size") or "0"))
            if size != 0:
                return position
    return None


def abs_decimal(value) -> Decimal:
    return abs(Decimal(str(value)))


def estimate_pnl(
    side: str,
    entry_price: Decimal | None,
    exit_price: Decimal | None,
    size: Decimal,
) -> Decimal | None:
    if entry_price is None or exit_price is None:
        return None
    if side == "LONG":
        return (exit_price - entry_price) * size
    return (entry_price - exit_price) * size


def serialize_trade(trade) -> dict:
    return {
        "id": trade.id,
        "order_id": trade.order_id,
        "close_order_id": trade.close_order_id,
        "symbol": trade.symbol,
        "side": trade.side,
        "size": trade.size,
        "entry_price": trade.entry_price,
        "exit_price": trade.exit_price,
        "realized_pnl": trade.realized_pnl,
        "status": trade.status,
        "wallet_address": trade.wallet_address,
        "opened_at": trade.opened_at,
        "closed_at": trade.closed_at,
        "timestamp": trade.opened_at,
    }
