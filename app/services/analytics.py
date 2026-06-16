from __future__ import annotations

import math
from collections import defaultdict
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Analytics, Trade


class AnalyticsService:
    async def compute_and_store(self, session: AsyncSession) -> dict:
        result = await session.execute(select(Trade).where(Trade.realized_pnl.is_not(None)))
        trades = list(result.scalars())
        metrics = compute_trade_metrics(trades)
        session.add(Analytics(period="all", metrics=metrics))
        await session.commit()
        return metrics


def compute_trade_metrics(trades: list[Trade]) -> dict:
    pnls = [float(t.realized_pnl or Decimal("0")) for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    equity_curve = []
    total = 0.0
    for pnl in pnls:
        total += pnl
        equity_curve.append(total)
    return {
        "trades": len(pnls),
        "closed_trades": len(pnls),
        "total_pnl": total,
        "win_rate": len(wins) / len(pnls) if pnls else 0,
        "average_win": sum(wins) / len(wins) if wins else 0,
        "average_loss": sum(losses) / len(losses) if losses else 0,
        "profit_factor": gross_profit / gross_loss
        if gross_loss
        else (gross_profit if gross_profit else 0),
        "sharpe_ratio": sharpe(pnls),
        "max_drawdown": max_drawdown(equity_curve),
        "average_trade": sum(pnls) / len(pnls) if pnls else 0,
        "daily_performance": grouped_performance(trades, "%Y-%m-%d"),
        "monthly_performance": grouped_performance(trades, "%Y-%m"),
    }


def sharpe(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    variance = sum((value - mean) ** 2 for value in values) / (len(values) - 1)
    std = math.sqrt(variance)
    return 0.0 if std == 0 else mean / std * math.sqrt(len(values))


def max_drawdown(curve: list[float]) -> float:
    peak = 0.0
    drawdown = 0.0
    for value in curve:
        peak = max(peak, value)
        drawdown = min(drawdown, value - peak)
    return drawdown


def grouped_performance(trades: list[Trade], fmt: str) -> dict[str, float]:
    buckets: defaultdict[str, float] = defaultdict(float)
    for trade in trades:
        if trade.closed_at and trade.realized_pnl is not None:
            buckets[trade.closed_at.strftime(fmt)] += float(trade.realized_pnl)
    return dict(buckets)
