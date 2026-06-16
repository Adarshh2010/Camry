from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.session import SessionLocal
from app.services.orchestrator import ResearchOrchestrator


async def main() -> None:
    async with SessionLocal() as session:
        result = await ResearchOrchestrator().collect_market(
            session,
            symbols=["BTC", "ETH", "SOL", "HYPE"],
            interval="1m",
            lookback_minutes=30,
        )
        print(result)


if __name__ == "__main__":
    asyncio.run(main())
