from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Literal

from dotenv import load_dotenv

load_dotenv()


def _bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _float_env(name: str, default: float) -> float:
    value = os.getenv(name)
    return default if value is None or value == "" else float(value)


def _int_env(name: str, default: int) -> int:
    value = os.getenv(name)
    return default if value is None or value == "" else int(value)


def _list_env(name: str, default: list[str]) -> list[str]:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    stripped = value.strip()
    if stripped.startswith("[") and stripped.endswith("]"):
        return [
            item.strip().strip('"').strip("'")
            for item in stripped[1:-1].split(",")
            if item.strip()
        ]
    return [item.strip() for item in stripped.split(",") if item.strip()]


@dataclass(frozen=True)
class Settings:
    app_name: str = field(default_factory=lambda: os.getenv("APP_NAME", "Hyperliquid Research Platform"))
    environment: str = field(default_factory=lambda: os.getenv("ENVIRONMENT", "development"))
    database_url: str = field(default_factory=lambda: os.environ["DATABASE_URL"])
    auto_create_tables: bool = field(default_factory=lambda: _bool_env("AUTO_CREATE_TABLES", False))
    paper_trading: bool = field(default_factory=lambda: _bool_env("PAPER_TRADING", True))
    trading_mode: Literal["paper", "live"] = field(
        default_factory=lambda: os.getenv("TRADING_MODE", "paper")  # type: ignore[return-value]
    )
    initial_equity: float = field(default_factory=lambda: _float_env("INITIAL_EQUITY", 10_000.0))
    max_risk_per_trade: float = field(default_factory=lambda: _float_env("MAX_RISK_PER_TRADE", 0.01))
    max_daily_loss: float = field(default_factory=lambda: _float_env("MAX_DAILY_LOSS", 0.03))
    max_leverage: int = field(default_factory=lambda: _int_env("MAX_LEVERAGE", 3))
    max_simultaneous_trades: int = field(default_factory=lambda: _int_env("MAX_SIMULTANEOUS_TRADES", 3))
    paper_fee_rate: float = field(default_factory=lambda: _float_env("PAPER_FEE_RATE", 0.00045))
    hyperliquid_base_url: str = field(
        default_factory=lambda: os.getenv(
            "HYPERLIQUID_BASE_URL", "https://api.hyperliquid-testnet.xyz"
        )
    )
    hyperliquid_ws_url: str = field(
        default_factory=lambda: os.getenv(
            "HYPERLIQUID_WS_URL", "wss://api.hyperliquid-testnet.xyz/ws"
        )
    )
    coingecko_base_url: str = field(
        default_factory=lambda: os.getenv("COINGECKO_BASE_URL", "https://api.coingecko.com/api/v3")
    )
    fear_greed_url: str = field(
        default_factory=lambda: os.getenv("FEAR_GREED_URL", "https://api.alternative.me/fng/")
    )
    dydx_indexer_url: str = field(
        default_factory=lambda: os.getenv(
            "DYDX_INDEXER_URL", "https://indexer.v4testnet.dydx.exchange/v4"
        )
    )
    dydx_wallet_address: str | None = field(default_factory=lambda: os.getenv("DYDX_WALLET_ADDRESS"))
    dydx_subaccount_number: int = field(default_factory=lambda: _int_env("DYDX_SUBACCOUNT_NUMBER", 0))
    dydx_enable_testnet_execution: bool = field(
        default_factory=lambda: _bool_env("DYDX_ENABLE_TESTNET_EXECUTION", False)
    )
    dydx_test_mnemonic: str | None = field(default_factory=lambda: os.getenv("DYDX_TEST_MNEMONIC"))
    dydx_fixed_btc_size: float = field(default_factory=lambda: _float_env("DYDX_FIXED_BTC_SIZE", 0.0005))
    dydx_max_account_risk: float = field(default_factory=lambda: _float_env("DYDX_MAX_ACCOUNT_RISK", 0.0025))
    gemini_api_key: str | None = field(default_factory=lambda: os.getenv("GEMINI_API_KEY"))
    gemini_model: str = field(default_factory=lambda: os.getenv("GEMINI_MODEL", "gemini-3.5-flash"))
    gemini_news_model: str | None = field(
        default_factory=lambda: os.getenv("GEMINI_NEWS_MODEL", "gemini-3.1-flash-lite")
    )
    gemini_market_model: str | None = field(
        default_factory=lambda: os.getenv("GEMINI_MARKET_MODEL", "gemini-3.5-flash")
    )
    gemini_decision_model: str | None = field(
        default_factory=lambda: os.getenv("GEMINI_DECISION_MODEL", "gemini-3.5-flash")
    )
    decision_scheduler_enabled: bool = field(
        default_factory=lambda: _bool_env("DECISION_SCHEDULER_ENABLED", True)
    )
    decision_scheduler_symbol: str = field(
        default_factory=lambda: os.getenv("DECISION_SCHEDULER_SYMBOL", "BTC")
    )
    decision_scheduler_interval_seconds: int = field(
        default_factory=lambda: _int_env("DECISION_SCHEDULER_INTERVAL_SECONDS", 900)
    )
    paper_trade_monitor_enabled: bool = field(
        default_factory=lambda: _bool_env("PAPER_TRADE_MONITOR_ENABLED", True)
    )
    paper_trade_monitor_interval_seconds: int = field(
        default_factory=lambda: _int_env("PAPER_TRADE_MONITOR_INTERVAL_SECONDS", 60)
    )
    telegram_bot_token: str | None = field(default_factory=lambda: os.getenv("TELEGRAM_BOT_TOKEN"))
    telegram_chat_id: str | None = field(default_factory=lambda: os.getenv("TELEGRAM_CHAT_ID"))
    telegram_command_polling_enabled: bool = field(
        default_factory=lambda: _bool_env("TELEGRAM_COMMAND_POLLING_ENABLED", True)
    )
    telegram_command_polling_interval_seconds: int = field(
        default_factory=lambda: _int_env("TELEGRAM_COMMAND_POLLING_INTERVAL_SECONDS", 3)
    )
    telegram_webhook_url: str | None = field(default_factory=lambda: os.getenv("TELEGRAM_WEBHOOK_URL"))
    log_level: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO"))
    tracked_symbols: list[str] = field(
        default_factory=lambda: _list_env("TRACKED_SYMBOLS", ["BTC", "ETH", "SOL", "HYPE"])
    )
    rss_feeds: list[str] = field(
        default_factory=lambda: _list_env(
            "RSS_FEEDS",
            [
                "https://www.coindesk.com/arc/outboundfeeds/rss/",
                "https://cointelegraph.com/rss",
                "https://www.theblock.co/rss.xml",
            ],
        )
    )
    reddit_communities: list[str] = field(
        default_factory=lambda: _list_env(
            "REDDIT_COMMUNITIES", ["CryptoCurrency", "Bitcoin", "ethereum", "CryptoMarkets"]
        )
    )
    telegram_channel_usernames: list[str] = field(
        default_factory=lambda: _list_env("TELEGRAM_CHANNEL_USERNAMES", [])
    )

    @property
    def is_paper_trading(self) -> bool:
        return self.paper_trading and self.trading_mode == "paper"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
