from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, Field


class TradeAction(StrEnum):
    LONG = "LONG"
    SHORT = "SHORT"
    NO_TRADE = "NO_TRADE"


class MarketSnapshot(BaseModel):
    symbol: str
    price: float
    trend: float = 0.0
    volatility: float = 0.0
    volume_change: float = 0.0
    momentum: float = 0.0
    funding_rate: float | None = None
    open_interest: float | None = None


class NewsAssessment(BaseModel):
    sentiment_score: float = Field(ge=-1, le=1)
    impact_score: float = Field(ge=0, le=1)
    confidence_score: float = Field(ge=0, le=1)
    reasoning: str


class MarketAssessment(BaseModel):
    bullish_score: float = Field(ge=0, le=1)
    bearish_score: float = Field(ge=0, le=1)
    confidence_score: float = Field(ge=0, le=1)
    explanation: str


class RiskAssessment(BaseModel):
    allowed: bool
    reason: str
    equity: float
    max_position_notional: float
    suggested_quantity: float
    stop_loss: float | None
    take_profit: float | None
    leverage: float


class Decision(BaseModel):
    symbol: str
    action: TradeAction
    confidence: float = Field(ge=0, le=1)
    reasoning: str
    risk_reward: float | None = None
    inputs: dict


class BacktestRequest(BaseModel):
    symbol: str
    start: datetime
    end: datetime
    strategy: str = "momentum_v1"
    initial_equity: float = 10_000.0


class BacktestReport(BaseModel):
    symbol: str
    strategy: str
    trades: int
    win_rate: float
    profit_factor: float
    max_drawdown: float
    final_equity: float
    notes: list[str]


class PositionSizeRequest(BaseModel):
    equity: float
    entry_price: float
    stop_loss: float
    leverage: float = 1


class PositionSizeResult(BaseModel):
    risk_amount: float
    quantity: float
    notional: float
    leverage: float


class PaperTradeOpenRequest(BaseModel):
    symbol: str
    side: TradeAction
    entry_price: float
    quantity: float
    leverage: float = Field(default=1, ge=1, le=3)
    stop_loss: float | None = None
    take_profit: float | None = None
    notes: str = "Manual paper trade."


class PaperTradeCloseRequest(BaseModel):
    exit_price: float
    notes: str = "Manual paper close."


class SerializedPosition(BaseModel):
    id: int
    symbol: str
    side: str
    status: str
    entry_price: Decimal
    exit_price: Decimal | None
    quantity: Decimal
    leverage: float
    stop_loss: Decimal | None
    take_profit: Decimal | None
    realized_pnl: Decimal | None
    fees: Decimal

    model_config = {"from_attributes": True}
