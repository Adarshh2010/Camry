from __future__ import annotations

import asyncio
import sys
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.collectors.coingecko import CoinGeckoClient
from app.db.repositories import log_event, upsert_market_data
from app.db.session import SessionLocal

COINS = {
    "bitcoin": "BTC",
    "ethereum": "ETH",
    "solana": "SOL",
    "hyperliquid": "HYPE",
}


async def main() -> None:
    client = CoinGeckoClient()
    raw = await client.simple_prices(list(COINS.keys()))
    timestamp = datetime.now(UTC).replace(microsecond=0)
    rows = []
    for coin_id, symbol in COINS.items():
        price = raw.get(coin_id, {}).get("usd")
        if price is None:
            continue
        value = Decimal(str(price))
        rows.append(
            {
                "symbol": symbol,
                "source": "coingecko",
                "timeframe": "spot",
                "timestamp": timestamp,
                "open": value,
                "high": value,
                "low": value,
                "close": value,
                "volume": None,
                "open_interest": None,
                "funding_rate": None,
                "liquidations": None,
                "raw": {"coin_id": coin_id, "payload": raw.get(coin_id)},
            }
        )
    async with SessionLocal() as session:
        written = await upsert_market_data(session, rows)
        await log_event(
            session,
            "INFO",
            "coingecko_raw_data",
            {"raw": raw, "rows_written": written},
        )
    print(
        {
            "collector": "coingecko",
            "rows_written": written,
            "symbols": [row["symbol"] for row in rows],
        }
    )


if __name__ == "__main__":
    asyncio.run(main())
