from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories import store_exchange_snapshot
from app.db.session import get_session
from app.services.dydx import DydxTestnetClient
from app.services.dydx_execution import DydxExecutionError, DydxTestnetExecutionService
from app.services.telegram import TelegramNotifier

router = APIRouter()


@router.get("/exchange/status")
async def exchange_status(session: AsyncSession = Depends(get_session)) -> dict:
    client = DydxTestnetClient()
    payload = await client.status()
    status = payload["connection_status"]
    await store_exchange_snapshot(
        session,
        snapshot_type="status",
        status=status,
        payload=payload,
        wallet_address=payload.get("wallet_address"),
    )
    if status == "Connected":
        await TelegramNotifier().send(
            "dYdX testnet connected\n"
            f"Wallet: {payload.get('wallet_address') or 'not configured'}\n"
            "Mode: READ ONLY"
        )
    return payload


@router.get("/exchange/balance")
async def exchange_balance(session: AsyncSession = Depends(get_session)) -> dict:
    client = DydxTestnetClient()
    try:
        payload = await client.account_summary()
    except ValueError as exc:
        result = {
            "connection_status": "Disconnected",
            "reason": str(exc),
            "wallet_address": client.account.wallet_address,
            "subaccount_number": client.account.subaccount_number,
            "balance": None,
            "equity": None,
            "available_margin": None,
        }
        await store_exchange_snapshot(
            session,
            snapshot_type="balance",
            status="Disconnected",
            payload=result,
            wallet_address=client.account.wallet_address,
        )
        return result
    result = {
        "wallet_address": payload["wallet_address"],
        "subaccount_number": payload["subaccount_number"],
        "balance": payload["balance"],
        "equity": payload["equity"],
        "available_margin": payload["available_margin"],
    }
    await store_exchange_snapshot(
        session,
        snapshot_type="balance",
        status="Connected",
        payload=result | {"raw": payload["raw"]},
        wallet_address=payload["wallet_address"],
    )
    return result


@router.get("/exchange/positions")
async def exchange_positions(session: AsyncSession = Depends(get_session)) -> dict:
    client = DydxTestnetClient()
    try:
        payload = await client.open_positions()
    except ValueError as exc:
        result = {
            "connection_status": "Disconnected",
            "reason": str(exc),
            "wallet_address": client.account.wallet_address,
            "subaccount_number": client.account.subaccount_number,
            "positions": [],
        }
        await store_exchange_snapshot(
            session,
            snapshot_type="positions",
            status="Disconnected",
            payload=result,
            wallet_address=client.account.wallet_address,
        )
        return result
    result = {
        "wallet_address": client.account.wallet_address,
        "subaccount_number": client.account.subaccount_number,
        "positions": payload.get("positions", []),
    }
    await store_exchange_snapshot(
        session,
        snapshot_type="positions",
        status="Connected",
        payload=result,
        wallet_address=client.account.wallet_address,
    )
    return result


@router.get("/exchange/markets")
async def exchange_markets(session: AsyncSession = Depends(get_session)) -> dict:
    payload = await DydxTestnetClient().markets()
    result = {
        "exchange": "dydx",
        "network": "testnet",
        "markets": payload["markets"],
    }
    await store_exchange_snapshot(
        session,
        snapshot_type="markets",
        status="Connected",
        payload=result | {"raw": payload["raw"]},
    )
    return result


@router.post("/test-long")
async def open_test_long(session: AsyncSession = Depends(get_session)) -> dict:
    try:
        return await DydxTestnetExecutionService().open_long(session)
    except DydxExecutionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/test-short")
async def open_test_short(session: AsyncSession = Depends(get_session)) -> dict:
    try:
        return await DydxTestnetExecutionService().open_short(session)
    except DydxExecutionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/test-close")
async def close_test_position(session: AsyncSession = Depends(get_session)) -> dict:
    try:
        return await DydxTestnetExecutionService().close_active(session)
    except DydxExecutionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
