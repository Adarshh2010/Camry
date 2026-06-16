# Camry AI Trading Agent

Personal AI-powered crypto trading research and paper-trading agent.

Camry is a portfolio project built to explore market-data collection, AI-assisted trade research, risk controls, Telegram alerts, and paper-trading analytics. The default mode is `paper`; the application is designed for simulated trading and research, not real-money execution.

## Features

- Async FastAPI backend
- SQLAlchemy async models and Alembic migrations for Supabase/PostgreSQL
- Crypto market-data collectors
- CoinGecko and Fear & Greed collectors
- RSS news collector with deduplication hashes
- Reddit community and Telegram bot-update news ingestion
- Gemini-powered news, market, and decision agents
- Hard-coded risk engine:
  - 1% max risk per trade
  - 3% max daily loss
  - 3x max leverage
  - 3 max simultaneous trades
  - emergency shutdown gate
- Paper trading engine with simulated fees, positions, PnL, and journal entries
- Analytics: win rate, profit factor, Sharpe ratio, drawdown, averages, daily and monthly PnL
- Backtesting module
- Telegram notifications for signals, executions, summaries, and alerts
- Structured JSON logging

## Quick Start

```bash
cp .env.example .env
docker compose up --build
```

For local development:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
alembic upgrade head
uvicorn app.main:app --reload
```

For personal Supabase initialization without running Alembic manually, set `AUTO_CREATE_TABLES=true` for the first startup, then switch it back to `false`.

Detailed setup instructions:

- [Setup guide](docs/SETUP.md)
- [Supabase setup](docs/SUPABASE.md)
- [Local development](docs/LOCAL_DEVELOPMENT.md)

## Required Environment

Use your Supabase PostgreSQL connection string as `DATABASE_URL`.

```bash
DATABASE_URL=postgresql+asyncpg://postgres:password@db.project.supabase.co:5432/postgres
AUTO_CREATE_TABLES=false
GEMINI_API_KEY=...
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
TRADING_MODE=paper
```

## API

- `GET /health`
- `GET /api/status`
- `GET /api/signals/current`
- `GET /api/positions/current`
- `GET /api/trades`
- `GET /api/analytics`
- `POST /api/backtests`
- `POST /api/collect/market`
- `POST /api/collect/news`
- `POST /api/run/decision-cycle`

## External API Notes

- Exchange and market-data integrations are used for research and paper-trading signals.
- CoinGecko provides REST market-data endpoints and paid websocket delivery.
- Alternative.me Fear & Greed Index uses `GET https://api.alternative.me/fng/`.

## Safety

This project prioritizes research and risk management. Paper trading is implemented; live real-money execution is not enabled. Every decision is persisted to `signals`, `trades`, and `logs` where applicable so decisions can be audited later.
