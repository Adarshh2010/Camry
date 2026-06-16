# Local Development

## Python

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

## Local PostgreSQL

Set:

```bash
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/hyperliquid_research
```

Run:

```bash
alembic upgrade head
```

## Docker Compose

```bash
cp .env.example .env
docker compose up --build
```

The compose file starts PostgreSQL 16 and the API. If `.env` points to Supabase, the API uses that external database instead.

## Verification Commands

```bash
python -m ruff check .
python -m pytest -q
python -m alembic upgrade head
uvicorn app.main:app --reload
```

Endpoint smoke checks:

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/api/status
curl http://127.0.0.1:8000/api/signals/current
curl http://127.0.0.1:8000/api/positions/current
curl http://127.0.0.1:8000/api/trades
curl http://127.0.0.1:8000/api/analytics
```

