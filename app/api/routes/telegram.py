from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import logger
from app.db.session import get_session
from app.services.telegram import TelegramNotifier
from app.services.telegram_commands import TelegramCommandService

router = APIRouter()


@router.post("/telegram/webhook")
async def telegram_webhook(
    update: dict,
    session: AsyncSession = Depends(get_session),
) -> dict:
    logger.info(
        "telegram_webhook_request_received",
        update_id=update.get("update_id"),
        has_message=bool(update.get("message") or update.get("edited_message")),
    )
    try:
        result = await TelegramCommandService().handle_update(session, update)
        logger.info("telegram_webhook_request_complete", result=result)
        return result
    except Exception as exc:
        logger.exception("telegram_webhook_request_failed", error=str(exc))
        raise


@router.post("/telegram/commands/register")
async def register_telegram_commands() -> dict:
    sent = await TelegramNotifier().set_commands()
    return {"registered": sent}


@router.get("/telegram/webhook-info")
async def telegram_webhook_info() -> dict:
    return await TelegramNotifier().get_webhook_info()
