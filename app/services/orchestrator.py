from __future__ import annotations

from datetime import UTC, datetime, timedelta
from statistics import mean, pstdev

from sqlalchemy.ext.asyncio import AsyncSession

from app.collectors.hyperliquid import (
    HyperliquidClient,
    asset_contexts_by_symbol,
    enrich_with_asset_context,
    normalize_candle,
)
from app.core.config import settings
from app.db.models import PositionSide, Sentiment, Signal, SignalAction, TradeReasoning
from app.db.repositories import (
    count_open_positions,
    daily_realized_pnl,
    insert_news_ignore_duplicates,
    latest_market_rows,
    log_event,
    recent_news,
    upsert_market_data,
)
from app.services.telegram import TelegramNotifier


class ResearchOrchestrator:
    def __init__(self) -> None:
        self.hyperliquid = HyperliquidClient()
        self.telegram = TelegramNotifier()

    async def collect_market(
        self,
        session: AsyncSession,
        symbols: list[str] | None = None,
        interval: str = "1m",
        lookback_minutes: int = 120,
    ) -> dict:
        symbols = symbols or settings.tracked_symbols
        end = datetime.now(UTC)
        start = end - timedelta(minutes=lookback_minutes)
        rows: list[dict] = []
        contexts = asset_contexts_by_symbol(await self.hyperliquid.meta_and_asset_contexts())
        for symbol in symbols:
            candles = await self.hyperliquid.candle_snapshot(
                symbol,
                interval,
                int(start.timestamp() * 1000),
                int(end.timestamp() * 1000),
            )
            normalized = [normalize_candle(symbol, interval, candle) for candle in candles]
            if normalized:
                normalized[-1] = enrich_with_asset_context(normalized[-1], contexts.get(symbol))
            rows.extend(normalized)
        count = await upsert_market_data(session, rows)
        await log_event(
            session, "INFO", "market_collection_complete", {"rows": count, "symbols": symbols}
        )
        await self.telegram.send(
            "Hyperliquid testnet connected\n"
            f"Symbols: {', '.join(symbols)}\n"
            f"Stored rows: {count}\n"
            "Mode: PAPER"
        )
        return {"inserted_or_updated": count, "symbols": symbols}

    async def collect_news(self, session: AsyncSession) -> dict:
        from app.collectors.news import NewsCollector

        rows = await NewsCollector().collect_all()
        count = await insert_news_ignore_duplicates(session, rows)
        await log_event(session, "INFO", "news_collection_complete", {"rows": count})
        return {"inserted": count}

    async def analyze_recent_news(self, session: AsyncSession, symbol: str):
        from app.schemas.domain import NewsAssessment

        items = await recent_news(session, hours=24)
        if not items:
            return NewsAssessment(
                sentiment_score=0,
                impact_score=0,
                confidence_score=0.35,
                reasoning="No recent news available.",
            )
        assessments: list[NewsAssessment] = []
        from app.agents.news_agent import NewsIntelligenceAgent

        news_agent = NewsIntelligenceAgent()
        for item in items[:10]:
            assessment = await news_agent.analyze(item.title, item.content)
            session.add(
                Sentiment(
                    news_id=item.id,
                    symbol=symbol,
                    sentiment_score=assessment.sentiment_score,
                    impact_score=assessment.impact_score,
                    confidence_score=assessment.confidence_score,
                    reasoning=assessment.reasoning,
                    model=settings.gemini_news_model or settings.gemini_model,
                    raw=assessment.model_dump(),
                )
            )
            assessments.append(assessment)
        await session.commit()
        return aggregate_news(assessments)

    async def run_decision_cycle(self, session: AsyncSession, symbol: str) -> dict:
        try:
            market_rows = await latest_market_rows(session, symbol, limit=100)
            if not market_rows:
                await log_event(
                    session,
                    "WARN",
                    "decision_cycle_skipped",
                    {"symbol": symbol, "reason": "no_market_data"},
                )
                return {
                    "symbol": symbol,
                    "status": "skipped",
                    "reason": "No market data for symbol.",
                }
            snapshot = market_snapshot(symbol, market_rows)
            from app.agents.decision_agent import DecisionAgent
            from app.agents.market_agent import MarketIntelligenceAgent

            market_agent = MarketIntelligenceAgent()
            decision_agent = DecisionAgent()
            from app.schemas.domain import TradeAction
            from app.services.paper_trading import PaperTradingEngine, calculate_risk_reward_ratio
            from app.services.risk import RiskEngine

            market = await market_agent.analyze(snapshot)
            news = await self.analyze_recent_news(session, symbol)
            daily_pnl = await daily_realized_pnl(session)
            open_count = await count_open_positions(session)
            side_hint = "LONG" if market.bullish_score >= market.bearish_score else "SHORT"
            risk = RiskEngine().assess(
                equity=settings.initial_equity + daily_pnl,
                daily_pnl=daily_pnl,
                open_positions=open_count,
                entry_price=snapshot.price,
                side=side_hint,
                leverage=settings.max_leverage,
            )
            decision = await decision_agent.decide(symbol, news, market, risk)
            paper_risk_reward = calculate_risk_reward_ratio(
                snapshot.price,
                risk.stop_loss,
                risk.take_profit,
                PositionSide(decision.action.value)
                if decision.action != TradeAction.NO_TRADE
                else PositionSide.LONG,
            )
            decision_inputs = {
                **decision.inputs,
                "market_snapshot": snapshot.model_dump(),
                "news_summary": news.model_dump(),
                "market_agent_output": market.model_dump(),
                "risk_engine_output": risk.model_dump(),
                "paper_trade_required": decision.action != TradeAction.NO_TRADE,
                "paper_trade_only": True,
                "auto_execute": "paper_only",
            }
            signal = Signal(
                symbol=symbol,
                action=SignalAction(decision.action.value),
                confidence=decision.confidence,
                bullish_score=market.bullish_score,
                bearish_score=market.bearish_score,
                risk_reward=paper_risk_reward if paper_risk_reward is not None else decision.risk_reward,
                reasoning=decision.reasoning,
                inputs=decision_inputs,
            )
            session.add(signal)
            await session.flush()
            session.add(
                TradeReasoning(
                    signal_id=signal.id,
                    data_time=datetime.now(UTC),
                    news_score=news.sentiment_score,
                    market_score=market.bullish_score - market.bearish_score,
                    decision=SignalAction(decision.action.value),
                    confidence=decision.confidence,
                    result=(
                        "NO_TRADE"
                        if decision.action == TradeAction.NO_TRADE
                        else "PAPER_TRADE_OPENED"
                    ),
                )
            )
            position = None
            if decision.action != TradeAction.NO_TRADE and risk.allowed:
                position = await PaperTradingEngine().execute_signal(
                    session=session,
                    signal=signal,
                    decision=decision,
                    price=snapshot.price,
                    quantity=risk.suggested_quantity,
                    leverage=risk.leverage,
                    stop_loss=risk.stop_loss,
                    take_profit=risk.take_profit,
                )
            else:
                await session.commit()
            await self.telegram.signal_detected(
                symbol,
                decision.action.value,
                decision.confidence,
                decision.reasoning,
            )
            if position is not None:
                await self.telegram.paper_trade_opened(
                    position.symbol,
                    position.side.value,
                    str(position.quantity),
                    str(position.entry_price),
                    str(position.stop_loss),
                    str(position.take_profit),
                    str((position.extra or {}).get("risk_reward") or 0),
                )
            await log_event(
                session,
                "INFO",
                "decision_cycle_complete",
                {
                    "symbol": symbol,
                    "action": decision.action.value,
                    "confidence": decision.confidence,
                    "paper_position_id": position.id if position else None,
                    "paper_trade_only": True,
                },
            )
            return {
                "symbol": symbol,
                "signal_id": signal.id,
                "position_id": position.id if position else None,
                "paper_trade_only": True,
                "auto_execute": "paper_only",
                "decision": decision.model_dump(mode="json"),
                "risk": risk.model_dump(),
                "market_snapshot": snapshot.model_dump(),
                "market": market.model_dump(),
                "news_summary": news.model_dump(),
                "news": news.model_dump(),
            }
        except Exception as exc:
            await self.telegram.error_alert("decision_cycle", str(exc))
            raise


def market_snapshot(symbol: str, rows: list):
    from app.schemas.domain import MarketSnapshot

    ordered = list(reversed(rows))
    closes = [float(row.close) for row in ordered]
    volumes = [float(row.volume or 0) for row in ordered]
    price = closes[-1]
    first = closes[0]
    trend = 0 if first == 0 else (price - first) / first
    returns = [(b - a) / a for a, b in zip(closes, closes[1:], strict=False) if a]
    volatility = pstdev(returns) if len(returns) > 1 else 0.0
    momentum = 0 if len(closes) < 10 or closes[-10] == 0 else (price - closes[-10]) / closes[-10]
    recent_volume = mean(volumes[-10:]) if len(volumes) >= 10 else mean(volumes) if volumes else 0
    prior_volume = mean(volumes[:-10]) if len(volumes) > 10 else recent_volume
    volume_change = 0 if prior_volume == 0 else (recent_volume - prior_volume) / prior_volume
    latest = ordered[-1]
    return MarketSnapshot(
        symbol=symbol,
        price=price,
        trend=trend,
        volatility=volatility,
        volume_change=volume_change,
        momentum=momentum,
        funding_rate=float(latest.funding_rate) if latest.funding_rate is not None else None,
        open_interest=float(latest.open_interest) if latest.open_interest is not None else None,
    )


def aggregate_news(items: list):
    from app.schemas.domain import NewsAssessment

    if not items:
        return NewsAssessment(
            sentiment_score=0, impact_score=0, confidence_score=0.35, reasoning="No news."
        )
    weights = [max(item.impact_score * item.confidence_score, 0.01) for item in items]
    total_weight = sum(weights)
    sentiment = (
        sum(item.sentiment_score * weight for item, weight in zip(items, weights, strict=True))
        / total_weight
    )
    impact = sum(item.impact_score for item in items) / len(items)
    confidence = sum(item.confidence_score for item in items) / len(items)
    return NewsAssessment(
        sentiment_score=sentiment,
        impact_score=impact,
        confidence_score=confidence,
        reasoning=f"Aggregate of {len(items)} recent news assessments.",
    )
