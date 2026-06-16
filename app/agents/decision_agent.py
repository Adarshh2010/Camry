from __future__ import annotations

from app.agents.gemini import GeminiClient
from app.core.config import settings
from app.core.logging import logger
from app.schemas.domain import (
    Decision,
    MarketAssessment,
    NewsAssessment,
    RiskAssessment,
    TradeAction,
)


class DecisionAgent:
    def __init__(self, gemini: GeminiClient | None = None) -> None:
        self.gemini = gemini or GeminiClient(model=settings.gemini_decision_model)

    async def decide(
        self,
        symbol: str,
        news: NewsAssessment,
        market: MarketAssessment,
        risk: RiskAssessment,
    ) -> Decision:
        fallback = deterministic_decision(symbol, news, market, risk)
        prompt = f"""
You are a cautious paper-trading decision agent. Risk management is more important than profit.
Return strict JSON with keys: symbol, action (LONG, SHORT, NO_TRADE), confidence, reasoning,
risk_reward, inputs.
News: {news.model_dump_json()}
Market: {market.model_dump_json()}
Risk: {risk.model_dump_json()}
"""
        result = await self.gemini.json_completion(prompt, fallback.model_dump())
        result["symbol"] = symbol
        if not risk.allowed:
            result["action"] = TradeAction.NO_TRADE.value
            result["reasoning"] = f"Risk gate blocked trade: {risk.reason}"
        result.setdefault("inputs", fallback.inputs)
        result.setdefault("confidence", fallback.confidence)
        result.setdefault("reasoning", fallback.reasoning)
        result.setdefault("risk_reward", fallback.risk_reward)
        if (
            not isinstance(result.get("risk_reward"), int | float)
            and result.get("risk_reward") is not None
        ):
            result["risk_reward"] = None
        try:
            return Decision.model_validate(result)
        except Exception as exc:
            logger.warning("decision_agent_output_invalid", error=str(exc), raw=result)
            return fallback


def deterministic_decision(
    symbol: str,
    news: NewsAssessment,
    market: MarketAssessment,
    risk: RiskAssessment,
) -> Decision:
    if not risk.allowed:
        action = TradeAction.NO_TRADE
        confidence = 1.0
        reasoning = f"No trade because risk engine blocked execution: {risk.reason}"
    elif market.bullish_score > 0.62 and news.sentiment_score > -0.25:
        action = TradeAction.LONG
        confidence = min(market.confidence_score, news.confidence_score + 0.2)
        reasoning = "Bullish market score with no strongly negative news."
    elif market.bearish_score > 0.62 and news.sentiment_score < 0.25:
        action = TradeAction.SHORT
        confidence = min(market.confidence_score, news.confidence_score + 0.2)
        reasoning = "Bearish market score with no strongly positive news."
    else:
        action = TradeAction.NO_TRADE
        confidence = 0.65
        reasoning = "Signal quality is not high enough for a risk-adjusted paper trade."
    return Decision(
        symbol=symbol,
        action=action,
        confidence=confidence,
        reasoning=reasoning,
        risk_reward=2.0 if action != TradeAction.NO_TRADE else None,
        inputs={
            "news": news.model_dump(),
            "market": market.model_dump(),
            "risk": risk.model_dump(),
        },
    )
