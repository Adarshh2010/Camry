from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Analytics, Signal, SignalAction
from app.services.telegram import TelegramNotifier


class SignalReportService:
    async def daily_report(
        self,
        session: AsyncSession,
        *,
        now: datetime | None = None,
        send_telegram: bool = False,
        store: bool = True,
    ) -> dict:
        current_time = now or datetime.now(UTC)
        since = current_time - timedelta(days=1)
        result = await session.execute(
            select(Signal)
            .where(Signal.created_at >= since)
            .order_by(Signal.created_at.desc())
        )
        signals = list(result.scalars())
        confidences = [float(signal.confidence) for signal in signals]
        report = {
            "period": "last_24h",
            "generated_at": current_time.isoformat(),
            "since": since.isoformat(),
            "total_signals": len(signals),
            "long_count": count_action(signals, SignalAction.LONG),
            "short_count": count_action(signals, SignalAction.SHORT),
            "no_trade_count": count_action(signals, SignalAction.NO_TRADE),
            "average_confidence": (
                sum(confidences) / len(confidences) if confidences else 0.0
            ),
            "top_reasoning_patterns": top_reasoning_patterns(signals),
            "human_approval_only": True,
            "auto_execute": False,
        }
        if store:
            session.add(Analytics(period="signals_daily", metrics=report))
            await session.commit()
        if send_telegram:
            report["telegram_sent"] = await TelegramNotifier().signal_daily_report(report)
        return report


def count_action(signals: list[Signal], action: SignalAction) -> int:
    return sum(1 for signal in signals if signal.action == action)


def top_reasoning_patterns(signals: list[Signal], limit: int = 5) -> list[dict]:
    counts: Counter[str] = Counter()
    for signal in signals:
        pattern = reasoning_pattern(signal.reasoning)
        if pattern:
            counts[pattern] += 1
    return [
        {"pattern": pattern, "count": count}
        for pattern, count in counts.most_common(limit)
    ]


def reasoning_pattern(reasoning: str) -> str:
    normalized = " ".join(reasoning.strip().split())
    if not normalized:
        return ""
    first_sentence = normalized.split(". ", 1)[0].strip(".")
    return first_sentence[:140]
