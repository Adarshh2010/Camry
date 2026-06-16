from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models import Position, PositionSide, PositionStatus
from app.db.repositories import (
    current_positions,
    latest_analytics,
    latest_market_by_symbols,
    latest_market_rows,
    latest_signals,
)
from app.db.session import get_session
from app.schemas.domain import (
    BacktestRequest,
    PaperTradeCloseRequest,
    PaperTradeOpenRequest,
    TradeAction,
)
from app.services.analytics import AnalyticsService
from app.services.backtesting import BacktestingService
from app.services.orchestrator import ResearchOrchestrator
from app.services.paper_trading import PaperTradingEngine
from app.services.paper_trade_monitor import close_reason_text
from app.services.signal_reports import SignalReportService
from app.services.telegram import TelegramNotifier

router = APIRouter()


@router.get("/signals/current")
async def get_current_signals(session: AsyncSession = Depends(get_session)) -> list[dict]:
    return [serialize_signal(signal) for signal in await latest_signals(session)]


@router.get("/signals/daily-report")
async def get_daily_signal_report(session: AsyncSession = Depends(get_session)) -> dict:
    return await SignalReportService().daily_report(session, send_telegram=False, store=False)


@router.post("/signals/daily-report/send")
async def send_daily_signal_report(session: AsyncSession = Depends(get_session)) -> dict:
    report = await SignalReportService().daily_report(session, send_telegram=True)
    return {"sent": bool(report.get("telegram_sent")), "report": report}


@router.get("/positions/current")
async def get_current_positions(session: AsyncSession = Depends(get_session)) -> list[dict]:
    return [serialize_position(position) for position in await current_positions(session)]


@router.get("/market/latest")
async def get_latest_market_data(
    symbols: list[str] | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
) -> dict:
    tracked = symbols or settings.tracked_symbols
    rows = await latest_market_by_symbols(session, tracked)
    return {
        "source": "hyperliquid-testnet",
        "paper_trading": settings.is_paper_trading,
        "symbols": tracked,
        "data": [serialize_market_data(row) for row in rows],
    }


@router.get("/trades")
async def get_trades(
    limit: int = Query(default=100, ge=1, le=500),
    session: AsyncSession = Depends(get_session),
) -> dict:
    open_positions = await positions_by_status(session, PositionStatus.OPEN, limit)
    closed_positions = await positions_by_status(session, PositionStatus.CLOSED, limit)
    return trade_dashboard(open_positions, closed_positions)


@router.post("/trades/open")
async def open_paper_trade(
    request: PaperTradeOpenRequest,
    session: AsyncSession = Depends(get_session),
) -> dict:
    if not settings.is_paper_trading:
        raise HTTPException(status_code=403, detail="Only paper trading is enabled.")
    if request.side == TradeAction.NO_TRADE:
        raise HTTPException(status_code=400, detail="Use LONG or SHORT for paper positions.")
    position = await PaperTradingEngine().open_position(
        session=session,
        symbol=request.symbol,
        side=PositionSide(request.side.value),
        entry_price=request.entry_price,
        quantity=request.quantity,
        leverage=request.leverage,
        stop_loss=request.stop_loss,
        take_profit=request.take_profit,
        notes=request.notes,
        metadata={"source": "manual_paper_endpoint"},
    )
    if position is None:
        raise HTTPException(status_code=403, detail="Paper trading is disabled.")
    await TelegramNotifier().paper_trade_opened(
        position.symbol,
        position.side.value,
        str(position.quantity),
        str(position.entry_price),
        str(position.stop_loss),
        str(position.take_profit),
        str((position.extra or {}).get("risk_reward") or 0),
    )
    return serialize_position(position)


@router.post("/trades/{position_id}/close")
async def close_paper_trade(
    position_id: int,
    request: PaperTradeCloseRequest,
    session: AsyncSession = Depends(get_session),
) -> dict:
    position = await session.get(Position, position_id)
    if position is None:
        raise HTTPException(status_code=404, detail="Position not found.")
    closed = await PaperTradingEngine().close_position(
        session,
        position,
        request.exit_price,
        request.notes,
    )
    await TelegramNotifier().paper_trade_closed(
        closed.symbol,
        closed.side.value,
        str(closed.exit_price),
        str(closed.realized_pnl),
        request.notes,
    )
    return serialize_position(closed)


@router.post("/trades/evaluate")
async def evaluate_paper_stops(session: AsyncSession = Depends(get_session)) -> dict:
    open_positions = await current_positions(session)
    prices: dict[str, float] = {}
    for position in open_positions:
        rows = await latest_market_rows(session, position.symbol, limit=1)
        if rows:
            prices[position.symbol] = float(rows[0].close)
    closed = await PaperTradingEngine().evaluate_stops(session, prices)
    for position in closed:
        await TelegramNotifier().paper_trade_closed(
            position.symbol,
            position.side.value,
            str(position.exit_price),
            str(position.realized_pnl),
            close_reason_text(position),
        )
    return {"evaluated": len(open_positions), "closed": [serialize_position(row) for row in closed]}


@router.post("/trades/daily-summary")
async def send_daily_trade_summary(
    limit: int = Query(default=500, ge=1, le=1000),
    session: AsyncSession = Depends(get_session),
) -> dict:
    open_positions = await positions_by_status(session, PositionStatus.OPEN, limit)
    closed_positions = await positions_by_status(session, PositionStatus.CLOSED, limit)
    dashboard = trade_dashboard(open_positions, closed_positions)
    sent = await TelegramNotifier().daily_summary(
        dashboard["total_pnl"],
        dashboard["win_rate"],
        len(open_positions),
        len(closed_positions),
    )
    return {"sent": sent, "summary": dashboard}


@router.get("/analytics")
async def get_analytics(session: AsyncSession = Depends(get_session)) -> dict:
    cached = await latest_analytics(session)
    if cached:
        return cached
    return await AnalyticsService().compute_and_store(session)


@router.post("/backtests")
async def run_backtest(
    request: BacktestRequest,
    session: AsyncSession = Depends(get_session),
) -> dict:
    return (await BacktestingService().run(session, request)).model_dump()


@router.post("/collect/market")
async def collect_market(
    symbols: list[str] | None = None,
    session: AsyncSession = Depends(get_session),
) -> dict:
    return await ResearchOrchestrator().collect_market(session, symbols or settings.tracked_symbols)


@router.post("/collect/news")
async def collect_news(session: AsyncSession = Depends(get_session)) -> dict:
    return await ResearchOrchestrator().collect_news(session)


@router.post("/run/decision-cycle")
async def run_decision_cycle(
    symbol: str = Query(default="BTC"),
    session: AsyncSession = Depends(get_session),
) -> dict:
    return await ResearchOrchestrator().run_decision_cycle(session, symbol)


def serialize_signal(signal) -> dict:
    return {
        "id": signal.id,
        "symbol": signal.symbol,
        "action": signal.action.value,
        "confidence": signal.confidence,
        "bullish_score": signal.bullish_score,
        "bearish_score": signal.bearish_score,
        "risk_reward": signal.risk_reward,
        "reasoning": signal.reasoning,
        "created_at": signal.created_at,
    }


def serialize_position(position) -> dict:
    return {
        "id": position.id,
        "symbol": position.symbol,
        "side": position.side.value,
        "status": position.status.value,
        "entry_price": position.entry_price,
        "exit_price": position.exit_price,
        "quantity": position.quantity,
        "leverage": position.leverage,
        "stop_loss": position.stop_loss,
        "take_profit": position.take_profit,
        "realized_pnl": position.realized_pnl,
        "fees": position.fees,
        "opened_at": position.opened_at,
        "closed_at": position.closed_at,
    }


def serialize_market_data(row) -> dict:
    return {
        "id": row.id,
        "symbol": row.symbol,
        "source": row.source,
        "timeframe": row.timeframe,
        "timestamp": row.timestamp,
        "price": row.close,
        "open": row.open,
        "high": row.high,
        "low": row.low,
        "volume": row.volume,
        "funding_rate": row.funding_rate,
        "open_interest": row.open_interest,
        "raw": row.raw,
    }


async def positions_by_status(
    session: AsyncSession,
    status: PositionStatus,
    limit: int,
) -> list[Position]:
    result = await session.execute(
        select(Position)
        .where(Position.status == status)
        .order_by(desc(Position.opened_at))
        .limit(limit)
    )
    return list(result.scalars())


def trade_dashboard(open_positions: list[Position], closed_positions: list[Position]) -> dict:
    realized = [float(position.realized_pnl or 0) for position in closed_positions]
    wins = [pnl for pnl in realized if pnl > 0]
    trade_history_rows = sorted(
        [*open_positions, *closed_positions],
        key=lambda position: position.opened_at,
        reverse=True,
    )
    return {
        "open_positions": [serialize_position(position) for position in open_positions],
        "closed_positions": [serialize_position(position) for position in closed_positions],
        "total_pnl": sum(realized),
        "win_rate": len(wins) / len(realized) if realized else 0,
        "trade_history": [serialize_position(position) for position in trade_history_rows],
    }


def serialize_trade(trade) -> dict:
    return {
        "id": trade.id,
        "position_id": trade.position_id,
        "signal_id": trade.signal_id,
        "symbol": trade.symbol,
        "side": trade.side.value,
        "entry_price": trade.entry_price,
        "exit_price": trade.exit_price,
        "quantity": trade.quantity,
        "realized_pnl": trade.realized_pnl,
        "fees": trade.fees,
        "opened_at": trade.opened_at,
        "closed_at": trade.closed_at,
        "notes": trade.notes,
    }
