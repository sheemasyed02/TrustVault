# TrustVault backend

FastAPI + Python. Current surface:

- `GET /health`
- SQLAlchemy models and Alembic migrations for PostgreSQL schema

Authentication, document APIs, grants, and R2 are not implemented yet.

## Setup

```powershell
cd D:\TrustVault\backend
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
```

Set `DATABASE_URL` in `backend/.env` to your local PostgreSQL database (for example `trustvault_db`). Prefer:

```text
postgresql+psycopg://USER:PASSWORD@localhost:5432/trustvault_db
```

`postgresql+asyncpg://...` is accepted and remapped to psycopg for sync SQLAlchemy/Alembic.

## Run API

```powershell
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

## Apply migrations

Directory: `D:\TrustVault\backend`

```powershell
.\.venv\Scripts\Activate.ps1
alembic upgrade head
```

Read-only verification:

```powershell
python scripts\verify_schema.py
```

Or in psql / pgAdmin:

```sql
SELECT table_name
FROM information_schema.tables
WHERE table_schema = 'public'
  AND table_name IN ('users', 'documents', 'document_permissions', 'audit_events')
ORDER BY table_name;
```

## Tests

```powershell
pytest -v
```

## Railway

On the Railway **backend** service, set `DATABASE_URL` from the Railway PostgreSQL plugin variable of the same name (or reference `${{Postgres.DATABASE_URL}}`).

- From inside Railway, the private URL (`postgres.railway.internal`) is correct.
- From your laptop, that private host **cannot** be resolved. Use the public URL instead.

### Create tables on Railway from your laptop

1. In Railway → your **Postgres** service → **Variables** (or Connect), copy `DATABASE_PUBLIC_URL`  
   (host looks like `*.proxy.rlwy.net`, not `postgres.railway.internal`).
2. Put that value into `backend/.env` as:

```text
RAILWAY_DATABASE_URL=postgresql://...proxy.rlwy.net:.../railway
```

3. Run:

```powershell
cd D:\TrustVault\backend
.\.venv\Scripts\Activate.ps1
python scripts\migrate_with_url_env.py RAILWAY_DATABASE_URL
python scripts\verify_schema.py
```

For step 3 verification against Railway, temporarily point `DATABASE_URL` at the same public URL, or re-run verify after setting it. Do not commit `.env` or paste passwords into chat.
