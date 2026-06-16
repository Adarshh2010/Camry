from __future__ import annotations

import json
import os
import subprocess
import time
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from urllib import request


ROOT = Path(__file__).resolve().parents[1]
PSQL = "/opt/homebrew/opt/postgresql@16/bin/psql"
HELPER = ROOT / "scripts" / "dydx_testnet_order.cjs"
INDEXER = "https://indexer.v4testnet.dydx.exchange/v4"
SYMBOL = "BTC-USD"


def load_env() -> dict[str, str]:
    values = dict(os.environ)
    for line in (ROOT / ".env").read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        values[key] = value.strip().strip('"').strip("'")
    return values


def get_json(url: str) -> dict:
    req = request.Request(
        url,
        headers={"Accept": "application/json", "User-Agent": "curl/8.0"},
        method="GET",
    )
    with request.urlopen(req, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def btc_price() -> Decimal:
    raw = get_json(f"{INDEXER}/perpetualMarkets?limit=100")
    return Decimal(str(raw["markets"][SYMBOL]["oraclePrice"]))


def open_position_size(wallet: str, subaccount: str) -> Decimal:
    raw = get_json(
        f"{INDEXER}/perpetualPositions?"
        f"address={wallet}&subaccountNumber={subaccount}&status=OPEN"
    )
    for position in raw.get("positions", []):
        if position.get("market") == SYMBOL:
            return Decimal(str(position.get("size", "0")))
    return Decimal("0")


def account_equity(wallet: str, subaccount: str) -> Decimal:
    raw = get_json(f"{INDEXER}/addresses/{wallet}")
    for account in raw.get("subaccounts", []):
        if str(account.get("subaccountNumber")) == subaccount:
            return Decimal(str(account["equity"]))
    raise RuntimeError("Configured dYdX subaccount was not found.")


def run_order(env: dict[str, str], side: str, size: Decimal, price: Decimal, reduce_only: bool) -> dict:
    payload = {
        "symbol": SYMBOL,
        "side": side,
        "size": str(size),
        "price": str(price),
        "reduce_only": reduce_only,
    }
    proc = subprocess.run(
        ["node", str(HELPER), json.dumps(payload)],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=180,
    )
    if proc.returncode:
        raise RuntimeError(proc.stderr.strip() or proc.stdout.strip() or "dYdX order failed.")
    return json.loads(proc.stdout)


def sql_quote(value: object) -> str:
    if value is None:
        return "NULL"
    return "'" + str(value).replace("'", "''") + "'"


def jsonb(value: object) -> str:
    return sql_quote(json.dumps(value, separators=(",", ":"))) + "::jsonb"


def insert_trade(env: dict[str, str], row: dict) -> None:
    database_url = env["DATABASE_URL"].replace("postgresql+asyncpg://", "postgresql://", 1)
    sql = f"""
insert into dydx_test_trades (
  order_id, close_order_id, symbol, side, size, entry_price, exit_price,
  realized_pnl, status, wallet_address, opened_at, closed_at, raw
) values (
  {sql_quote(row["order_id"])},
  {sql_quote(row["close_order_id"])},
  {sql_quote(SYMBOL)},
  {sql_quote(row["side"])},
  {sql_quote(row["size"])},
  {sql_quote(row["entry_price"])},
  {sql_quote(row["exit_price"])},
  {sql_quote(row["realized_pnl"])},
  'CLOSED',
  {sql_quote(row["wallet_address"])},
  {sql_quote(row["opened_at"])},
  {sql_quote(row["closed_at"])},
  {jsonb(row["raw"])}
)
on conflict (order_id) do update set
  close_order_id = excluded.close_order_id,
  exit_price = excluded.exit_price,
  realized_pnl = excluded.realized_pnl,
  status = excluded.status,
  closed_at = excluded.closed_at,
  raw = excluded.raw;
"""
    subprocess.run([PSQL, database_url, "-v", "ON_ERROR_STOP=1", "-c", sql], check=True)


def send_telegram(env: dict[str, str], text: str) -> bool:
    token = env.get("TELEGRAM_BOT_TOKEN")
    chat_id = env.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return False
    data = json.dumps({"chat_id": chat_id, "text": text}).encode("utf-8")
    req = request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with request.urlopen(req, timeout=10) as response:
        return 200 <= response.status < 300


def main() -> None:
    env = load_env()
    wallet = env["DYDX_WALLET_ADDRESS"]
    subaccount = env.get("DYDX_SUBACCOUNT_NUMBER", "0")
    if not env.get("DYDX_TEST_MNEMONIC"):
        raise RuntimeError("DYDX_TEST_MNEMONIC is not set.")
    size = Decimal(env.get("DYDX_FIXED_BTC_SIZE") or "0.0005")
    max_risk = Decimal(env.get("DYDX_MAX_ACCOUNT_RISK") or "0.0025")
    before_size = open_position_size(wallet, subaccount)
    equity = account_equity(wallet, subaccount)
    entry = btc_price()
    notional = entry * size
    if notional > equity * max_risk:
        raise RuntimeError(f"Trade notional {notional} exceeds risk cap {equity * max_risk}.")

    opened_at = datetime.now(UTC)
    open_order = run_order(env, "BUY", size, entry, False)
    send_telegram(
        env,
        "🚀 Test Position Opened\n\n"
        f"Symbol: {SYMBOL}\n"
        "Side: LONG\n"
        f"Size: {size}\n"
        f"Entry: {entry}",
    )
    time.sleep(8)
    after_open_size = open_position_size(wallet, subaccount)
    exit_price = btc_price()
    close_order = run_order(env, "SELL", size, exit_price, True)
    closed_at = datetime.now(UTC)
    time.sleep(8)
    after_close_size = open_position_size(wallet, subaccount)
    pnl = (exit_price - entry) * size
    duration = closed_at - opened_at
    row = {
        "order_id": open_order["order_id"],
        "close_order_id": close_order["order_id"],
        "side": "LONG",
        "size": str(size),
        "entry_price": str(entry),
        "exit_price": str(exit_price),
        "realized_pnl": str(pnl),
        "wallet_address": wallet,
        "opened_at": opened_at.isoformat(),
        "closed_at": closed_at.isoformat(),
        "raw": {
            "open": open_order,
            "close": close_order,
            "before_size": str(before_size),
            "after_open_size": str(after_open_size),
            "after_close_size": str(after_close_size),
        },
    }
    insert_trade(env, row)
    close_sent = send_telegram(
        env,
        "✅ Test Position Closed\n\n"
        f"Exit: {exit_price}\n"
        f"PnL: {pnl}\n"
        f"Duration: {duration}",
    )
    print(
        json.dumps(
            {
                "wallet": wallet,
                "symbol": SYMBOL,
                "size": str(size),
                "entry_price": str(entry),
                "exit_price": str(exit_price),
                "estimated_pnl": str(pnl),
                "duration": str(duration),
                "open_order_id": open_order["order_id"],
                "close_order_id": close_order["order_id"],
                "position_size_before": str(before_size),
                "position_size_after_open": str(after_open_size),
                "position_size_after_close": str(after_close_size),
                "stored_in_supabase": True,
                "telegram_close_sent": close_sent,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
