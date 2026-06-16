from __future__ import annotations

from app.collectors.hyperliquid import (
    asset_contexts_by_symbol,
    enrich_with_asset_context,
    normalize_candle,
)
from app.collectors.news import dedupe_hash


def test_normalize_hyperliquid_candle() -> None:
    row = normalize_candle(
        "BTC",
        "1m",
        {"t": 1_718_323_200_000, "o": "100", "h": "110", "l": "90", "c": "105", "v": "12.5"},
    )

    assert row["symbol"] == "BTC"
    assert row["source"] == "hyperliquid"
    assert row["timeframe"] == "1m"
    assert str(row["close"]) == "105"
    assert str(row["volume"]) == "12.5"


def test_enrich_hyperliquid_candle_with_asset_context() -> None:
    row = normalize_candle(
        "ETH",
        "1m",
        {"t": 1_718_323_200_000, "o": "100", "h": "110", "l": "90", "c": "105", "v": "12.5"},
    )
    contexts = asset_contexts_by_symbol(
        [
            {"universe": [{"name": "BTC"}, {"name": "ETH"}]},
            [
                {"markPx": "60000", "dayNtlVlm": "100000", "funding": "0.0001"},
                {
                    "markPx": "3000",
                    "dayNtlVlm": "50000",
                    "openInterest": "1234.5",
                    "funding": "0.0002",
                },
            ],
        ]
    )

    enriched = enrich_with_asset_context(row, contexts["ETH"])

    assert str(enriched["close"]) == "3000"
    assert str(enriched["volume"]) == "50000"
    assert str(enriched["open_interest"]) == "1234.5"
    assert str(enriched["funding_rate"]) == "0.0002"


def test_news_dedupe_hash_is_stable() -> None:
    first = dedupe_hash(" Bitcoin ETF Flows ", "HTTPS://EXAMPLE.COM/A")
    second = dedupe_hash("bitcoin etf flows", "https://example.com/a")

    assert first == second
