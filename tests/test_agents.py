from __future__ import annotations

from app.agents.decision_agent import deterministic_decision
from app.schemas.domain import MarketAssessment, NewsAssessment, RiskAssessment, TradeAction


def test_decision_agent_prioritizes_risk_block() -> None:
    decision = deterministic_decision(
        "BTC",
        NewsAssessment(sentiment_score=1, impact_score=1, confidence_score=1, reasoning="bullish"),
        MarketAssessment(
            bullish_score=1,
            bearish_score=0,
            confidence_score=1,
            explanation="strong trend",
        ),
        RiskAssessment(
            allowed=False,
            reason="Max daily loss reached.",
            equity=10_000,
            max_position_notional=0,
            suggested_quantity=0,
            stop_loss=None,
            take_profit=None,
            leverage=1,
        ),
    )

    assert decision.action == TradeAction.NO_TRADE
    assert decision.confidence == 1


def test_decision_agent_returns_long_for_aligned_bullish_inputs() -> None:
    decision = deterministic_decision(
        "ETH",
        NewsAssessment(
            sentiment_score=0.2, impact_score=0.4, confidence_score=0.6, reasoning="neutral"
        ),
        MarketAssessment(
            bullish_score=0.7,
            bearish_score=0.3,
            confidence_score=0.8,
            explanation="trend",
        ),
        RiskAssessment(
            allowed=True,
            reason="ok",
            equity=10_000,
            max_position_notional=1_000,
            suggested_quantity=1,
            stop_loss=99,
            take_profit=102,
            leverage=1,
        ),
    )

    assert decision.action == TradeAction.LONG
