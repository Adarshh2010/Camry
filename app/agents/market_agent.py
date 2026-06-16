from __future__ import annotations

from app.agents.gemini import GeminiClient
from app.core.config import settings
from app.schemas.domain import MarketAssessment, MarketSnapshot


class MarketIntelligenceAgent:
    def __init__(self, gemini: GeminiClient | None = None) -> None:
        self.gemini = gemini or GeminiClient(model=settings.gemini_market_model)

    async def analyze(self, snapshot: MarketSnapshot) -> MarketAssessment:
        deterministic = deterministic_market_score(snapshot)
        prompt = f"""
Analyze this Hyperliquid market snapshot for research. Return strict JSON with keys:
bullish_score (0 to 1), bearish_score (0 to 1), confidence_score (0 to 1), explanation.
Snapshot: {snapshot.model_dump_json()}
"""
        result = await self.gemini.json_completion(prompt, deterministic.model_dump())
        return MarketAssessment.model_validate(result)


def deterministic_market_score(snapshot: MarketSnapshot) -> MarketAssessment:
    bullish = 0.5
    bullish += min(max(snapshot.trend, -1), 1) * 0.2
    bullish += min(max(snapshot.momentum, -1), 1) * 0.2
    bullish += min(max(snapshot.volume_change, -1), 1) * 0.1
    if snapshot.funding_rate and snapshot.funding_rate > 0.02:
        bullish -= 0.1
    bullish = min(max(bullish, 0), 1)
    bearish = 1 - bullish
    confidence = min(0.75, 0.35 + abs(bullish - bearish))
    return MarketAssessment(
        bullish_score=bullish,
        bearish_score=bearish,
        confidence_score=confidence,
        explanation="Deterministic fallback based on trend, momentum, volume, and funding.",
    )
