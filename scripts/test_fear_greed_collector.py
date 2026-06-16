from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.collectors.fear_greed import FearGreedClient
from app.db.repositories import log_event
from app.db.session import SessionLocal


async def main() -> None:
    raw = await FearGreedClient().latest()
    async with SessionLocal() as session:
        await log_event(session, "INFO", "fear_greed_raw_data", raw)
    latest = raw.get("data", [{}])[0]
    print(
        {
            "collector": "fear_greed",
            "value": latest.get("value"),
            "classification": latest.get("value_classification"),
        }
    )


if __name__ == "__main__":
    asyncio.run(main())
