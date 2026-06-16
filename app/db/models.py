from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import DateTime, Enum, ForeignKey, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class SignalAction(StrEnum):
    LONG = "LONG"
    SHORT = "SHORT"
    NO_TRADE = "NO_TRADE"


class PositionSide(StrEnum):
    LONG = "LONG"
    SHORT = "SHORT"


class PositionStatus(StrEnum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    CANCELLED = "CANCELLED"


class MarketData(Base):
    __tablename__ = "market_data"
    __table_args__ = (
        UniqueConstraint("symbol", "source", "timeframe", "timestamp", name="uq_market_data"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    source: Mapped[str] = mapped_column(String(64))
    timeframe: Mapped[str] = mapped_column(String(16))
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    open: Mapped[Decimal | None] = mapped_column(Numeric(24, 10))
    high: Mapped[Decimal | None] = mapped_column(Numeric(24, 10))
    low: Mapped[Decimal | None] = mapped_column(Numeric(24, 10))
    close: Mapped[Decimal] = mapped_column(Numeric(24, 10))
    volume: Mapped[Decimal | None] = mapped_column(Numeric(30, 10))
    open_interest: Mapped[Decimal | None] = mapped_column(Numeric(30, 10))
    funding_rate: Mapped[Decimal | None] = mapped_column(Numeric(18, 10))
    liquidations: Mapped[dict | None] = mapped_column(JSONB)
    raw: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class News(Base):
    __tablename__ = "news"

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(128))
    title: Mapped[str] = mapped_column(String(512))
    url: Mapped[str] = mapped_column(String(1024), unique=True)
    content: Mapped[str | None] = mapped_column(Text)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    dedupe_hash: Mapped[str] = mapped_column(String(64), unique=True)
    raw: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    sentiments: Mapped[list[Sentiment]] = relationship(back_populates="news")


class Sentiment(Base):
    __tablename__ = "sentiment"

    id: Mapped[int] = mapped_column(primary_key=True)
    news_id: Mapped[int | None] = mapped_column(ForeignKey("news.id", ondelete="CASCADE"))
    symbol: Mapped[str | None] = mapped_column(String(32), index=True)
    sentiment_score: Mapped[float]
    impact_score: Mapped[float]
    confidence_score: Mapped[float]
    reasoning: Mapped[str] = mapped_column(Text)
    model: Mapped[str] = mapped_column(String(128))
    raw: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    news: Mapped[News | None] = relationship(back_populates="sentiments")


class Signal(Base):
    __tablename__ = "signals"

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    action: Mapped[SignalAction] = mapped_column(Enum(SignalAction, name="signal_action"))
    confidence: Mapped[float]
    bullish_score: Mapped[float | None]
    bearish_score: Mapped[float | None]
    risk_reward: Mapped[float | None]
    reasoning: Mapped[str] = mapped_column(Text)
    inputs: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )


class TradeReasoning(Base):
    __tablename__ = "trade_reasoning"

    id: Mapped[int] = mapped_column(primary_key=True)
    signal_id: Mapped[int | None] = mapped_column(ForeignKey("signals.id", ondelete="SET NULL"))
    data_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    news_score: Mapped[float]
    market_score: Mapped[float]
    decision: Mapped[SignalAction] = mapped_column(Enum(SignalAction, name="signal_action"))
    confidence: Mapped[float]
    result: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Position(Base):
    __tablename__ = "positions"

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    side: Mapped[PositionSide] = mapped_column(Enum(PositionSide, name="position_side"))
    status: Mapped[PositionStatus] = mapped_column(Enum(PositionStatus, name="position_status"))
    entry_price: Mapped[Decimal] = mapped_column(Numeric(24, 10))
    exit_price: Mapped[Decimal | None] = mapped_column(Numeric(24, 10))
    quantity: Mapped[Decimal] = mapped_column(Numeric(30, 10))
    leverage: Mapped[float]
    stop_loss: Mapped[Decimal | None] = mapped_column(Numeric(24, 10))
    take_profit: Mapped[Decimal | None] = mapped_column(Numeric(24, 10))
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    realized_pnl: Mapped[Decimal | None] = mapped_column(Numeric(30, 10))
    fees: Mapped[Decimal] = mapped_column(Numeric(30, 10), default=Decimal("0"))
    extra: Mapped[dict | None] = mapped_column("metadata", JSONB)


class Trade(Base):
    __tablename__ = "trades"

    id: Mapped[int] = mapped_column(primary_key=True)
    position_id: Mapped[int | None] = mapped_column(ForeignKey("positions.id", ondelete="SET NULL"))
    signal_id: Mapped[int | None] = mapped_column(ForeignKey("signals.id", ondelete="SET NULL"))
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    side: Mapped[PositionSide] = mapped_column(Enum(PositionSide, name="position_side"))
    entry_price: Mapped[Decimal] = mapped_column(Numeric(24, 10))
    exit_price: Mapped[Decimal | None] = mapped_column(Numeric(24, 10))
    quantity: Mapped[Decimal] = mapped_column(Numeric(30, 10))
    realized_pnl: Mapped[Decimal | None] = mapped_column(Numeric(30, 10))
    fees: Mapped[Decimal] = mapped_column(Numeric(30, 10), default=Decimal("0"))
    notes: Mapped[str | None] = mapped_column(Text)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Analytics(Base):
    __tablename__ = "analytics"

    id: Mapped[int] = mapped_column(primary_key=True)
    period: Mapped[str] = mapped_column(String(32))
    metrics: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ExchangeSnapshot(Base):
    __tablename__ = "exchange_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    exchange: Mapped[str] = mapped_column(String(64), index=True)
    network: Mapped[str] = mapped_column(String(64))
    wallet_address: Mapped[str | None] = mapped_column(String(128), index=True)
    snapshot_type: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(32))
    payload: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )


class DydxTestTrade(Base):
    __tablename__ = "dydx_test_trades"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    close_order_id: Mapped[str | None] = mapped_column(String(128), unique=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    side: Mapped[str] = mapped_column(String(16))
    size: Mapped[Decimal] = mapped_column(Numeric(30, 10))
    entry_price: Mapped[Decimal | None] = mapped_column(Numeric(24, 10))
    exit_price: Mapped[Decimal | None] = mapped_column(Numeric(24, 10))
    realized_pnl: Mapped[Decimal | None] = mapped_column(Numeric(30, 10))
    status: Mapped[str] = mapped_column(String(32), index=True)
    wallet_address: Mapped[str | None] = mapped_column(String(128), index=True)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    raw: Mapped[dict | None] = mapped_column(JSONB)


class RiskDecision(Base):
    __tablename__ = "risk_decisions"

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    decision: Mapped[str] = mapped_column(String(32), index=True)
    reason: Mapped[str] = mapped_column(Text)
    daily_pnl: Mapped[Decimal] = mapped_column(Numeric(30, 10))
    open_positions: Mapped[int]
    remaining_risk_budget: Mapped[Decimal] = mapped_column(Numeric(30, 10))
    trading_enabled: Mapped[bool]
    payload: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )


class Log(Base):
    __tablename__ = "logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    level: Mapped[str] = mapped_column(String(16))
    event: Mapped[str] = mapped_column(String(256))
    payload: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
