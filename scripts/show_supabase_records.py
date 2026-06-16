from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import desc, func, select

from app.db.models import Log, MarketData, News, Sentiment, Signal, TradeReasoning
from app.db.session import SessionLocal


async def main() -> None:
    async with SessionLocal() as session:
        counts = {}
        for model in [MarketData, News, Sentiment, Signal, TradeReasoning, Log]:
            result = await session.execute(select(func.count(model.id)))
            counts[model.__tablename__] = result.scalar_one()

        latest_market = await session.execute(
            select(MarketData).order_by(desc(MarketData.created_at)).limit(5)
        )
        latest_news = await session.execute(select(News).order_by(desc(News.created_at)).limit(5))
        latest_signals = await session.execute(
            select(Signal).order_by(desc(Signal.created_at)).limit(3)
        )
        latest_reasoning = await session.execute(
            select(TradeReasoning).order_by(desc(TradeReasoning.created_at)).limit(5)
        )
        latest_logs = await session.execute(select(Log).order_by(desc(Log.created_at)).limit(5))

        print({"counts": counts})
        print(
            {
                "latest_market_data": [
                    {
                        "id": row.id,
                        "symbol": row.symbol,
                        "source": row.source,
                        "timestamp": row.timestamp.isoformat(),
                        "close": str(row.close),
                    }
                    for row in latest_market.scalars()
                ]
            }
        )
        print(
            {
                "latest_news": [
                    {"id": row.id, "source": row.source, "title": row.title[:120]}
                    for row in latest_news.scalars()
                ]
            }
        )
        print(
            {
                "latest_signals": [
                    {
                        "id": row.id,
                        "symbol": row.symbol,
                        "action": row.action.value,
                        "confidence": row.confidence,
                    }
                    for row in latest_signals.scalars()
                ]
            }
        )
        print(
            {
                "latest_trade_reasoning": [
                    {
                        "id": row.id,
                        "signal_id": row.signal_id,
                        "data_time": row.data_time.isoformat(),
                        "news_score": row.news_score,
                        "market_score": row.market_score,
                        "decision": row.decision.value,
                        "confidence": row.confidence,
                        "result": row.result,
                    }
                    for row in latest_reasoning.scalars()
                ]
            }
        )
        print(
            {
                "latest_logs": [
                    {"id": row.id, "event": row.event, "level": row.level}
                    for row in latest_logs.scalars()
                ]
            }
        )


if __name__ == "__main__":
    asyncio.run(main())
