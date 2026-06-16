# Supabase Setup

## 1. Create Project

Create a Supabase project and copy the PostgreSQL connection string from Project Settings.

Use the pooled or direct connection string in async SQLAlchemy format:

```bash
DATABASE_URL=postgresql+asyncpg://postgres:<password>@<host>:5432/postgres
```

If Supabase requires SSL, append:

```bash
?ssl=require
```

## 2. Apply Schema

Preferred:

```bash
alembic upgrade head
```

Personal bootstrap alternative:

```bash
AUTO_CREATE_TABLES=true uvicorn app.main:app
```

After the first successful startup, set:

```bash
AUTO_CREATE_TABLES=false
```

## 3. Expected Tables

- `market_data`
- `news`
- `sentiment`
- `signals`
- `trades`
- `positions`
- `analytics`
- `logs`
- `alembic_version`

## 4. Verify

```bash
curl http://127.0.0.1:8000/api/status
curl -X POST http://127.0.0.1:8000/api/collect/market
curl -X POST http://127.0.0.1:8000/api/collect/news
```

Then inspect Supabase Table Editor for inserted rows.

