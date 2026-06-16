from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import websockets

from app.core.config import settings
from app.core.http import http_client, request_json

TESTNET_BASE_URL = "https://api.hyperliquid-testnet.xyz"
TESTNET_WS_URL = "wss://api.hyperliquid-testnet.xyz/ws"


class HyperliquidClient:
    def __init__(self, base_url: str | None = None, ws_url: str | None = None) -> None:
        configured_base_url = base_url or str(settings.hyperliquid_base_url)
        configured_ws_url = ws_url or settings.hyperliquid_ws_url
        if settings.is_paper_trading and base_url is None:
            configured_base_url = TESTNET_BASE_URL
        if settings.is_paper_trading and ws_url is None:
            configured_ws_url = TESTNET_WS_URL
        self.base_url = configured_base_url.rstrip("/")
        self.ws_url = configured_ws_url

    async def info(self, payload: dict[str, Any]) -> Any:
        async with http_client() as client:
            return await request_json(
                client,
                "POST",
                f"{self.base_url}/info",
                json=payload,
                headers={"Content-Type": "application/json"},
            )

    async def all_mids(self) -> dict[str, str]:
        return await self.info({"type": "allMids"})

    async def meta_and_asset_contexts(self) -> Any:
        return await self.info({"type": "metaAndAssetCtxs"})

    async def candle_snapshot(
        self,
        symbol: str,
        interval: str,
        start_time_ms: int,
        end_time_ms: int,
    ) -> list[dict[str, Any]]:
        return await self.info(
            {
                "type": "candleSnapshot",
                "req": {
                    "coin": symbol,
                    "interval": interval,
                    "startTime": start_time_ms,
                    "endTime": end_time_ms,
                },
            }
        )

    async def stream_trades(self, symbols: list[str]) -> AsyncIterator[dict[str, Any]]:
        async with websockets.connect(self.ws_url, ping_interval=20, ping_timeout=20) as websocket:
            for symbol in symbols:
                await websocket.send(
                    json.dumps(
                        {"method": "subscribe", "subscription": {"type": "trades", "coin": symbol}}
                    )
                )
            while True:
                message = await websocket.recv()
                yield json.loads(message)
                await asyncio.sleep(0)


def normalize_candle(symbol: str, interval: str, raw: dict[str, Any]) -> dict:
    timestamp_ms = int(raw.get("t") or raw.get("T"))
    return {
        "symbol": symbol,
        "source": "hyperliquid",
        "timeframe": interval,
        "timestamp": datetime.fromtimestamp(timestamp_ms / 1000, tz=UTC),
        "open": Decimal(str(raw.get("o"))),
        "high": Decimal(str(raw.get("h"))),
        "low": Decimal(str(raw.get("l"))),
        "close": Decimal(str(raw.get("c"))),
        "volume": Decimal(str(raw.get("v"))) if raw.get("v") is not None else None,
        "open_interest": None,
        "funding_rate": None,
        "liquidations": None,
        "raw": raw,
    }


def asset_contexts_by_symbol(raw: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(raw, list) or len(raw) < 2:
        return {}
    meta, contexts = raw[0], raw[1]
    universe = meta.get("universe", []) if isinstance(meta, dict) else []
    if not isinstance(universe, list) or not isinstance(contexts, list):
        return {}
    mapped: dict[str, dict[str, Any]] = {}
    for asset, context in zip(universe, contexts, strict=False):
        if not isinstance(asset, dict) or not isinstance(context, dict):
            continue
        name = asset.get("name")
        if isinstance(name, str):
            mapped[name] = context
    return mapped


def enrich_with_asset_context(row: dict, context: dict[str, Any] | None) -> dict:
    if not context:
        return row
    enriched = {**row}
    mark_price = context.get("markPx") or context.get("midPx")
    volume = context.get("dayNtlVlm") or context.get("dayBaseVlm")
    open_interest = context.get("openInterest")
    funding_rate = context.get("funding")
    if mark_price is not None:
        enriched["close"] = Decimal(str(mark_price))
    if volume is not None:
        enriched["volume"] = Decimal(str(volume))
    if open_interest is not None:
        enriched["open_interest"] = Decimal(str(open_interest))
    if funding_rate is not None:
        enriched["funding_rate"] = Decimal(str(funding_rate))
    enriched["raw"] = {**(row.get("raw") or {}), "asset_context": context}
    return enriched
