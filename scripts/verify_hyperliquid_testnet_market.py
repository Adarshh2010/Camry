from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib import error, request


ROOT = Path(__file__).resolve().parents[1]
PSQL = "/opt/homebrew/opt/postgresql@16/bin/psql"
HYPERLIQUID_URL = "https://api.hyperliquid-testnet.xyz/info"
SYMBOLS = ["BTC", "ETH"]


def load_env() -> dict[str, str]:
    values: dict[str, str] = {}
    for line in (ROOT / ".env").read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        values[key] = value.strip().strip('"').strip("'")
    return values


def post_hyperliquid(payload: dict) -> object:
    data = json.dumps(payload).encode("utf-8")
    req = request.Request(
        HYPERLIQUID_URL,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with request.urlopen(req, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def sql_quote(value: object) -> str:
    if value is None:
        return "NULL"
    return "'" + str(value).replace("'", "''") + "'"


def jsonb(value: object) -> str:
    return sql_quote(json.dumps(value, separators=(",", ":"))) + "::jsonb"


def asset_contexts_by_symbol(raw: object) -> dict[str, dict]:
    if not isinstance(raw, list) or len(raw) < 2:
        return {}
    meta, contexts = raw[0], raw[1]
    universe = meta.get("universe", []) if isinstance(meta, dict) else []
    if not isinstance(universe, list) or not isinstance(contexts, list):
        return {}
    mapped: dict[str, dict] = {}
    for asset, context in zip(universe, contexts, strict=False):
        if isinstance(asset, dict) and isinstance(context, dict) and isinstance(asset.get("name"), str):
            mapped[asset["name"]] = context
    return mapped


def latest_candle(symbol: str) -> dict:
    end = datetime.now(UTC)
    start = end - timedelta(minutes=5)
    candles = post_hyperliquid(
        {
            "type": "candleSnapshot",
            "req": {
                "coin": symbol,
                "interval": "1m",
                "startTime": int(start.timestamp() * 1000),
                "endTime": int(end.timestamp() * 1000),
            },
        }
    )
    if not isinstance(candles, list) or not candles:
        raise RuntimeError(f"No candles returned for {symbol}")
    return candles[-1]


def build_insert_sql(rows: list[dict]) -> str:
    values = []
    for row in rows:
        values.append(
            "("
            + ",".join(
                [
                    sql_quote(row["symbol"]),
                    sql_quote("hyperliquid"),
                    sql_quote("1m"),
                    sql_quote(row["timestamp"]),
                    sql_quote(row["open"]),
                    sql_quote(row["high"]),
                    sql_quote(row["low"]),
                    sql_quote(row["close"]),
                    sql_quote(row["volume"]),
                    sql_quote(row["open_interest"]),
                    sql_quote(row["funding_rate"]),
                    "NULL",
                    jsonb(row["raw"]),
                ]
            )
            + ")"
        )
    return f"""
insert into market_data (
  symbol, source, timeframe, timestamp, open, high, low, close, volume,
  open_interest, funding_rate, liquidations, raw
) values
{",".join(values)}
on conflict on constraint uq_market_data do update set
  open = excluded.open,
  high = excluded.high,
  low = excluded.low,
  close = excluded.close,
  volume = excluded.volume,
  open_interest = excluded.open_interest,
  funding_rate = excluded.funding_rate,
  liquidations = excluded.liquidations,
  raw = excluded.raw;
"""


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
    try:
        with request.urlopen(req, timeout=10) as response:
            return 200 <= response.status < 300
    except (TimeoutError, OSError, error.URLError, error.HTTPError):
        return False


def main() -> None:
    env = load_env()
    database_url = env["DATABASE_URL"].replace("postgresql+asyncpg://", "postgresql://", 1)
    mids = post_hyperliquid({"type": "allMids"})
    contexts = asset_contexts_by_symbol(post_hyperliquid({"type": "metaAndAssetCtxs"}))
    rows: list[dict] = []
    for symbol in SYMBOLS:
        candle = latest_candle(symbol)
        context = contexts.get(symbol, {})
        timestamp_ms = int(candle.get("t") or candle.get("T"))
        rows.append(
            {
                "symbol": symbol,
                "timestamp": datetime.fromtimestamp(timestamp_ms / 1000, tz=UTC).isoformat(),
                "open": candle.get("o"),
                "high": candle.get("h"),
                "low": candle.get("l"),
                "close": context.get("markPx") or mids[symbol] if isinstance(mids, dict) else candle.get("c"),
                "volume": context.get("dayNtlVlm") or candle.get("v"),
                "open_interest": context.get("openInterest"),
                "funding_rate": context.get("funding"),
                "raw": {"candle": candle, "asset_context": context},
            }
        )

    sql = build_insert_sql(rows)
    subprocess.run([PSQL, database_url, "-v", "ON_ERROR_STOP=1", "-c", sql], check=True)
    sent = send_telegram(
        env,
        "Hyperliquid testnet connected\n"
        "BTC/ETH market data stored in Supabase\n"
        "Mode: PAPER",
    )
    print(json.dumps({"stored": len(rows), "telegram_sent": sent, "rows": rows}, indent=2))


if __name__ == "__main__":
    main()
