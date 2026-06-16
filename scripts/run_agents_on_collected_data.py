from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import desc, select

from app.db.models import MarketData, News, Sentiment, Signal
from app.db.repositories import log_event
from app.db.session import SessionLocal
from app.services.orchestrator import ResearchOrchestrator


async def main() -> None:
    async with SessionLocal() as session:
        raw_market = await session.execute(
            select(MarketData)
            .where(MarketData.symbol == "BTC")
            .order_by(desc(MarketData.timestamp))
            .limit(3)
        )
        raw_news = await session.execute(select(News).order_by(desc(News.created_at)).limit(3))
        result = await ResearchOrchestrator().run_decision_cycle(session, "BTC")
        signal = await session.get(Signal, result["signal_id"])
        sentiment_rows = await session.execute(
            select(Sentiment).order_by(desc(Sentiment.created_at)).limit(10)
        )
        pipeline = {
            "raw_data": {
                "market_data": [
                    {
                        "symbol": row.symbol,
                        "source": row.source,
                        "timeframe": row.timeframe,
                        "timestamp": row.timestamp.isoformat(),
                        "close": str(row.close),
                        "volume": str(row.volume) if row.volume is not None else None,
                    }
                    for row in raw_market.scalars()
                ],
                "news": [
                    {
                        "id": row.id,
                        "source": row.source,
                        "title": row.title,
                        "published_at": row.published_at.isoformat()
                        if row.published_at
                        else None,
                    }
                    for row in raw_news.scalars()
                ],
            },
            "news_agent_output": result["news"],
            "market_agent_output": result["market"],
            "decision_agent_output": result["decision"],
            "stored_outputs": {
                "signal_id": signal.id if signal else None,
                "sentiment_ids": [row.id for row in sentiment_rows.scalars()],
            },
        }
        await log_event(session, "INFO", "agent_pipeline_trace", pipeline)
    print(
        {
            "pipeline": (
                "Raw Data -> News Agent Output -> "
                "Market Agent Output -> Decision Agent Output"
            ),
            "signal_id": result["signal_id"],
            "decision": result["decision"]["action"],
        }
    )


if __name__ == "__main__":
    asyncio.run(main())
