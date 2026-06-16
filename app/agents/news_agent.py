from __future__ import annotations

from app.agents.gemini import GeminiClient
from app.core.config import settings
from app.schemas.domain import NewsAssessment


class NewsIntelligenceAgent:
    def __init__(self, gemini: GeminiClient | None = None) -> None:
        self.gemini = gemini or GeminiClient(model=settings.gemini_news_model)

    async def analyze(self, title: str, content: str | None = None) -> NewsAssessment:
        fallback = {
            "sentiment_score": 0.0,
            "impact_score": 0.2,
            "confidence_score": 0.35,
            "reasoning": (
                "Fallback neutral assessment because Gemini is unavailable "
                "or returned invalid JSON."
            ),
        }
        prompt = f"""
Analyze this crypto news item for trading research. Return strict JSON with keys:
sentiment_score (-1 to 1), impact_score (0 to 1), confidence_score (0 to 1), reasoning.
Title: {title}
Content: {content or ""}
"""
        result = await self.gemini.json_completion(prompt, fallback)
        return NewsAssessment.model_validate(result)
