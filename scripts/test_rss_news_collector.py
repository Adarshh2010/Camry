from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.collectors.news import NewsCollector
from app.db.repositories import insert_news_ignore_duplicates, log_event
from app.db.session import SessionLocal


async def main() -> None:
    collector = NewsCollector()
    rows = await collector.collect_rss()
    sample = [
        {
            "source": row["source"],
            "title": row["title"],
            "url": row["url"],
            "published_at": row["published_at"].isoformat() if row["published_at"] else None,
            "raw": row["raw"],
        }
        for row in rows[:3]
    ]
    async with SessionLocal() as session:
        inserted = await insert_news_ignore_duplicates(session, rows)
        await log_event(
            session,
            "INFO",
            "rss_raw_data",
            {
                "collected": len(rows),
                "inserted": inserted,
                "sample": sample,
            },
        )
    print({"collector": "rss", "collected": len(rows), "inserted": inserted})


if __name__ == "__main__":
    asyncio.run(main())
