# TrustVault backend

FastAPI + Python 3.12. Deployed on **Render**; database on **Neon**; private files on **Cloudflare R2**.

## Surface (high level)

- `GET /health` — liveness (no DB)
- `GET /health/ready` — readiness (`SELECT 1`; no secrets in body)
- Auth: `POST /auth/login`, `GET /users/me`, register/profile/password routes
- Documents: upload, list, detail, metadata, content, download (R2 stream), soft-delete
- Permissions: grant / revoke / list
- Admin: users, promotions, audit list, integrity verify
- Dev-only seed: `python -m app.cli.seed_demo_users` (never on startup)

Full route list: [`../API_DOCUMENTATION.md`](../API_DOCUMENTATION.md).

## Setup

```powershell
cd D:\TrustVault\backend
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
```

Required in `backend/.env` (or Render env):

- `DATABASE_URL`
- `JWT_SECRET_KEY` (≥ 32 random characters)
- R2 variables for upload/download (`R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET_NAME`, `R2_ENDPOINT_URL`)
- `CORS_ORIGINS` including every browser origin (local + Vercel)

Optional: `DIRECT_URL` (Neon direct host for Alembic), JWT issuer/audience/expiry.

## Run API (local)

```powershell
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

## Run API (Render)

Documented in the root [`../README.md`](../README.md) and [`../render.yaml`](../render.yaml):

```text
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

Startup validates JWT configuration and rejects CORS wildcards. It does **not** seed users, run migrations, or reset schema.

## Apply migrations

Alembic uses `DIRECT_URL` when set, otherwise `DATABASE_URL`. Prefer Neon’s **direct** string for DDL.

```powershell
alembic current
alembic upgrade head
```

Current head: `c3d4e5f6a7b8`.

If production was restored from pgAdmin and already matches this schema, inspect `alembic_version` before upgrading. Use `alembic stamp head` only when the schema already matches and the version table is missing/wrong — never drop/recreate the database.

Verify connectivity (redacts passwords):

```powershell
.\.venv\Scripts\python.exe scripts\check_database_connection.py
```

## Seed demo users (dev only)

```powershell
python -m app.cli.seed_demo_users
```

Never auto-seeded on startup. Passwords are never printed. Existing demo accounts are left unchanged on re-run; conflicting roles abort the seed. Do not run against a populated production DB without checking for duplicates/conflicts.

## Tests

Pytest requires `TEST_DATABASE_URL` (local DB whose name contains `test`). It never falls back to `DATABASE_URL`.

```powershell
psql -h 127.0.0.1 -p 5432 -U postgres -c "CREATE DATABASE trustvault_test;"
# Set TEST_DATABASE_URL in backend/.env
$env:DATABASE_URL = $env:TEST_DATABASE_URL
alembic upgrade head
pytest -q
```

## Auth transport note

Clients send `Authorization: Bearer <access_token>`. Tokens are not revoked server-side on logout; they remain valid until expiry. The Next.js app keeps the token in memory only.

## CORS

`CORS_ORIGINS` is a comma-separated allow-list. Do not use `*`. Include the deployed Vercel origin exactly (https, no path).
