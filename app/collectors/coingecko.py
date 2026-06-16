from __future__ import annotations

from typing import Any

from app.core.config import settings
from app.core.http import http_client, request_json


class CoinGeckoClient:
    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = (base_url or str(settings.coingecko_base_url)).rstrip("/")

    async def simple_prices(self, coin_ids: list[str], vs_currency: str = "usd") -> dict[str, Any]:
        async with http_client() as client:
            return await request_json(
                client,
                "GET",
                f"{self.base_url}/simple/price",
                params={"ids": ",".join(coin_ids), "vs_currencies": vs_currency},
            )

    async def market_chart(
        self,
        coin_id: str,
        vs_currency: str = "usd",
        days: str = "1",
    ) -> dict[str, Any]:
        async with http_client() as client:
            return await request_json(
                client,
                "GET",
                f"{self.base_url}/coins/{coin_id}/market_chart",
                params={"vs_currency": vs_currency, "days": days},
            )
