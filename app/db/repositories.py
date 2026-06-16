from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import desc, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    Analytics,
    DydxTestTrade,
    ExchangeSnapshot,
    Log,
    MarketData,
    News,
    Position,
    PositionStatus,
    RiskDecision,
    Signal,
    Trade,
)


async def upsert_market_data(session: AsyncSession, rows: list[dict]) -> int:
    if not rows:
        return 0
    stmt = insert(MarketData).values(rows)
    stmt = stmt.on_conflict_do_update(
        constraint="uq_market_data",
        set_={
            "open": stmt.excluded.open,
            "high": stmt.excluded.high,
            "low": stmt.excluded.low,
            "close": stmt.excluded.close,
            "volume": stmt.excluded.volume,
            "open_interest": stmt.excluded.open_interest,
            "funding_rate": stmt.excluded.funding_rate,
            "liquidations": stmt.excluded.liquidations,
            "raw": stmt.excluded.raw,
        },
    )
    result = await session.execute(stmt)
    await session.commit()
    return result.rowcount or 0


async def insert_news_ignore_duplicates(session: AsyncSession, rows: list[dict]) -> int:
    if not rows:
        return 0
    stmt = insert(News).values(rows).on_conflict_do_nothing(index_elements=["dedupe_hash"])
    result = await session.execute(stmt)
    await session.commit()
    return result.rowcount or 0


async def latest_market_rows(
    session: AsyncSession, symbol: str, limit: int = 100
) -> list[MarketData]:
    result = await session.execute(
        select(MarketData)
        .where(MarketData.symbol == symbol)
        .order_by(desc(MarketData.timestamp))
        .limit(limit)
    )
    return list(result.scalars())


async def latest_market_by_symbols(
    session: AsyncSession, symbols: list[str],
) -> list[MarketData]:
    if not symbols:
        return []
    ranked = (
        select(
            MarketData.id,
            func.row_number()
            .over(partition_by=MarketData.symbol, order_by=MarketData.timestamp.desc())
            .label("rank"),
        )
        .where(MarketData.symbol.in_(symbols))
        .subquery()
    )
    result = await session.execute(
        select(MarketData)
        .join(ranked, MarketData.id == ranked.c.id)
        .where(ranked.c.rank == 1)
        .order_by(MarketData.symbol)
    )
    return list(result.scalars())


async def latest_signals(session: AsyncSession, limit: int = 20) -> list[Signal]:
    result = await session.execute(select(Signal).order_by(desc(Signal.created_at)).limit(limit))
    return list(result.scalars())


async def current_positions(session: AsyncSession) -> list[Position]:
    result = await session.execute(
        select(Position)
        .where(Position.status == PositionStatus.OPEN)
        .order_by(desc(Position.opened_at))
    )
    return list(result.scalars())


async def trade_history(session: AsyncSession, limit: int = 100) -> list[Trade]:
    result = await session.execute(select(Trade).order_by(desc(Trade.opened_at)).limit(limit))
    return list(result.scalars())


async def daily_realized_pnl(session: AsyncSession) -> float:
    start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    result = await session.execute(
        select(func.coalesce(func.sum(Trade.realized_pnl), 0)).where(Trade.closed_at >= start)
    )
    return float(result.scalar_one() or 0)


async def count_open_positions(session: AsyncSession) -> int:
    result = await session.execute(
        select(func.count(Position.id)).where(Position.status == PositionStatus.OPEN)
    )
    return int(result.scalar_one())


async def recent_news(session: AsyncSession, hours: int = 24) -> list[News]:
    since = datetime.now(UTC) - timedelta(hours=hours)
    result = await session.execute(
        select(News).where(News.created_at >= since).order_by(desc(News.created_at)).limit(100)
    )
    return list(result.scalars())


async def latest_analytics(session: AsyncSession) -> dict | None:
    result = await session.execute(select(Analytics).order_by(desc(Analytics.created_at)).limit(1))
    row = result.scalar_one_or_none()
    return row.metrics if row else None


async def log_event(
    session: AsyncSession, level: str, event: str, payload: dict | None = None
) -> None:
    session.add(Log(level=level, event=event, payload=payload))
    await session.commit()


async def store_exchange_snapshot(
    session: AsyncSession,
    snapshot_type: str,
    status: str,
    payload: dict,
    wallet_address: str | None = None,
    exchange: str = "dydx",
    network: str = "testnet",
) -> ExchangeSnapshot:
    row = ExchangeSnapshot(
        exchange=exchange,
        network=network,
        wallet_address=wallet_address,
        snapshot_type=snapshot_type,
        status=status,
        payload=payload,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


async def insert_dydx_test_trade(
    session: AsyncSession,
    order_id: str,
    symbol: str,
    side: str,
    size: Decimal,
    entry_price: Decimal | None,
    status: str,
    wallet_address: str | None,
    raw: dict | None,
) -> DydxTestTrade:
    row = DydxTestTrade(
        order_id=order_id,
        symbol=symbol,
        side=side,
        size=size,
        entry_price=entry_price,
        status=status,
        wallet_address=wallet_address,
        raw=raw,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


async def latest_open_dydx_test_trade(session: AsyncSession) -> DydxTestTrade | None:
    result = await session.execute(
        select(DydxTestTrade)
        .where(DydxTestTrade.status == "OPEN")
        .order_by(desc(DydxTestTrade.opened_at))
        .limit(1)
    )
    return result.scalar_one_or_none()


async def close_dydx_test_trade(
    session: AsyncSession,
    trade: DydxTestTrade,
    close_order_id: str,
    exit_price: Decimal | None,
    realized_pnl: Decimal | None,
    raw: dict | None,
) -> DydxTestTrade:
    trade.close_order_id = close_order_id
    trade.exit_price = exit_price
    trade.realized_pnl = realized_pnl
    trade.status = "CLOSED"
    trade.closed_at = datetime.now(UTC)
    trade.raw = {**(trade.raw or {}), "close": raw}
    await session.commit()
    await session.refresh(trade)
    return trade


async def store_risk_decision(
    session: AsyncSession,
    symbol: str,
    decision: str,
    reason: str,
    daily_pnl: Decimal,
    open_positions: int,
    remaining_risk_budget: Decimal,
    trading_enabled: bool,
    payload: dict,
) -> RiskDecision:
    row = RiskDecision(
        symbol=symbol,
        decision=decision,
        reason=reason,
        daily_pnl=daily_pnl,
        open_positions=open_positions,
        remaining_risk_budget=remaining_risk_budget,
        trading_enabled=trading_enabled,
        payload=payload,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


async def daily_dydx_test_pnl(session: AsyncSession) -> Decimal:
    start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    result = await session.execute(
        select(func.coalesce(func.sum(DydxTestTrade.realized_pnl), 0)).where(
            DydxTestTrade.closed_at >= start
        )
    )
    return Decimal(str(result.scalar_one() or 0))


async def latest_dydx_loss(session: AsyncSession) -> DydxTestTrade | None:
    result = await session.execute(
        select(DydxTestTrade)
        .where(DydxTestTrade.realized_pnl < 0)
        .order_by(desc(DydxTestTrade.closed_at))
        .limit(1)
    )
    return result.scalar_one_or_none()
