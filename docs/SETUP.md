# Setup Guide

## Prerequisites

- Python 3.12
- PostgreSQL-compatible database, either Supabase PostgreSQL or local PostgreSQL
- Gemini API key for live AI model calls
- Telegram bot token and chat ID if notifications are needed

## Configure Environment

```bash
cp .env.example .env
```

Edit `.env` and keep:

```bash
TRADING_MODE=paper
AUTO_CREATE_TABLES=false
```

Run migrations before starting the app:

```bash
alembic upgrade head
```

## Start API

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

## Required Checks

```bash
python -m ruff check .
python -m pytest -q
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/api/status
```

## Safety Defaults

The default mode is paper trading. Do not set `TRADING_MODE=live` unless a separate live execution layer is intentionally implemented and reviewed.

