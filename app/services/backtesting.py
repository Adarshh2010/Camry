from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import MarketData
from app.schemas.domain import BacktestReport, BacktestRequest


class BacktestingService:
    async def run(self, session: AsyncSession, request: BacktestRequest) -> BacktestReport:
        result = await session.execute(
            select(MarketData)
            .where(
                MarketData.symbol == request.symbol,
                MarketData.timestamp >= request.start,
                MarketData.timestamp <= request.end,
            )
            .order_by(MarketData.timestamp)
        )
        rows = list(result.scalars())
        if len(rows) < 3:
            return BacktestReport(
                symbol=request.symbol,
                strategy=request.strategy,
                trades=0,
                win_rate=0,
                profit_factor=0,
                max_drawdown=0,
                final_equity=request.initial_equity,
                notes=["Not enough historical candles for backtest."],
            )
        equity = request.initial_equity
        pnls: list[float] = []
        for previous, current in zip(rows, rows[1:], strict=False):
            prev_close = float(previous.close)
            current_close = float(current.close)
            if current_close > prev_close * 1.002:
                pnls.append((current_close - prev_close) / prev_close * equity * 0.1)
            elif current_close < prev_close * 0.998:
                pnls.append((prev_close - current_close) / prev_close * equity * 0.1)
            if pnls:
                equity += pnls[-1]
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p < 0]
        gross_loss = abs(sum(losses))
        return BacktestReport(
            symbol=request.symbol,
            strategy=request.strategy,
            trades=len(pnls),
            win_rate=len(wins) / len(pnls) if pnls else 0,
            profit_factor=sum(wins) / gross_loss if gross_loss else 0,
            max_drawdown=drawdown(pnls),
            final_equity=equity,
            notes=[
                "Simple baseline momentum strategy; use as a harness, not a production strategy."
            ],
        )


def drawdown(pnls: list[float]) -> float:
    total = 0.0
    peak = 0.0
    worst = 0.0
    for pnl in pnls:
        total += pnl
        peak = max(peak, total)
        worst = min(worst, total - peak)
    return worst
