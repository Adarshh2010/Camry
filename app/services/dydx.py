from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from decimal import Decimal
from urllib import error, parse, request

from app.core.config import settings


DYDX_MARKETS = ["BTC-USD", "ETH-USD"]


@dataclass(frozen=True)
class DydxAccountConfig:
    wallet_address: str | None = settings.dydx_wallet_address
    subaccount_number: int = settings.dydx_subaccount_number


class DydxTestnetClient:
    def __init__(
        self,
        base_url: str | None = None,
        account: DydxAccountConfig | None = None,
    ) -> None:
        self.base_url = (base_url or settings.dydx_indexer_url).rstrip("/")
        self.account = account or DydxAccountConfig()

    async def status(self) -> dict:
        try:
            markets = await self.markets()
        except Exception as exc:
            return {
                "connection_status": "Disconnected",
                "exchange": "dydx",
                "network": "testnet",
                "reason": str(exc),
            }
        status = "Connected" if markets else "Disconnected"
        return {
            "connection_status": status,
            "exchange": "dydx",
            "network": "testnet",
            "wallet_address": self.account.wallet_address,
            "subaccount_number": self.account.subaccount_number,
        }

    async def markets(self) -> dict:
        raw = await self._get("/perpetualMarkets", {"limit": "100"})
        markets = raw.get("markets", {}) if isinstance(raw, dict) else {}
        selected = {
            symbol: normalize_market(symbol, markets[symbol])
            for symbol in DYDX_MARKETS
            if symbol in markets
        }
        return {"markets": selected, "raw": raw}

    async def account_summary(self) -> dict:
        wallet = self._require_wallet()
        address_raw = await self._get(f"/addresses/{parse.quote(wallet)}")
        asset_positions = await self.asset_positions()
        perpetual_positions = await self.open_positions()
        subaccount = find_subaccount(address_raw, self.account.subaccount_number)
        balance = extract_balance(subaccount, asset_positions)
        equity = extract_first_decimal(subaccount, ["equity", "accountEquity"])
        available_margin = extract_first_decimal(
            subaccount,
            ["freeCollateral", "availableMargin", "availableBalance"],
        )
        return {
            "wallet_address": wallet,
            "subaccount_number": self.account.subaccount_number,
            "balance": balance,
            "equity": equity,
            "available_margin": available_margin,
            "open_positions": perpetual_positions.get("positions", []),
            "asset_positions": asset_positions.get("positions", []),
            "raw": {
                "address": address_raw,
                "asset_positions": asset_positions,
                "perpetual_positions": perpetual_positions,
            },
        }

    async def asset_positions(self) -> dict:
        wallet = self._require_wallet()
        return await self._get(
            "/assetPositions",
            {
                "address": wallet,
                "subaccountNumber": str(self.account.subaccount_number),
            },
        )

    async def open_positions(self) -> dict:
        wallet = self._require_wallet()
        return await self._get(
            "/perpetualPositions",
            {
                "address": wallet,
                "subaccountNumber": str(self.account.subaccount_number),
                "status": "OPEN",
            },
        )

    async def _get(self, path: str, params: dict[str, str] | None = None) -> dict:
        url = f"{self.base_url}{path}"
        if params:
            url = f"{url}?{parse.urlencode(params)}"
        return await asyncio.to_thread(request_json, url)

    def _require_wallet(self) -> str:
        if not self.account.wallet_address:
            raise ValueError("DYDX_WALLET_ADDRESS is not configured.")
        return self.account.wallet_address


def request_json(url: str) -> dict:
    req = request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "hyperliquid-research-platform/0.1 read-only connectivity check",
        },
        method="GET",
    )
    try:
        with request.urlopen(req, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (TimeoutError, OSError, error.URLError, error.HTTPError) as exc:
        raise RuntimeError(f"dYdX testnet request failed: {exc}") from exc
    if isinstance(payload, dict) and ("error" in payload or "errors" in payload):
        raise RuntimeError(str(payload))
    if not isinstance(payload, dict):
        raise RuntimeError("dYdX testnet returned a non-object response.")
    return payload


def normalize_market(symbol: str, raw: dict) -> dict:
    return {
        "symbol": symbol,
        "status": raw.get("status"),
        "price": raw.get("oraclePrice"),
        "volume_24h": raw.get("volume24H"),
        "open_interest": raw.get("openInterest"),
        "next_funding_rate": raw.get("nextFundingRate"),
        "trades_24h": raw.get("trades24H"),
        "initial_margin_fraction": raw.get("initialMarginFraction"),
        "maintenance_margin_fraction": raw.get("maintenanceMarginFraction"),
    }


def find_subaccount(raw: dict, subaccount_number: int) -> dict:
    subaccounts = raw.get("subaccounts", [])
    if not isinstance(subaccounts, list):
        return {}
    for subaccount in subaccounts:
        if not isinstance(subaccount, dict):
            continue
        number = subaccount.get("subaccountNumber")
        if str(number) == str(subaccount_number):
            return subaccount
    return subaccounts[0] if subaccounts and isinstance(subaccounts[0], dict) else {}


def extract_first_decimal(raw: dict, keys: list[str]) -> str | None:
    for key in keys:
        value = raw.get(key)
        if value is not None:
            return str(Decimal(str(value)))
    return None


def extract_balance(subaccount: dict, asset_positions: dict) -> str | None:
    balance = extract_first_decimal(subaccount, ["quoteBalance", "balance"])
    if balance is not None:
        return balance
    positions = asset_positions.get("positions", [])
    if not isinstance(positions, list):
        return None
    for position in positions:
        if not isinstance(position, dict):
            continue
        symbol = str(position.get("symbol") or position.get("assetId") or "").upper()
        if symbol in {"USDC", "0"}:
            value = position.get("size") or position.get("balance")
            return str(Decimal(str(value))) if value is not None else None
    return None
