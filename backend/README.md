# TrustVault backend

FastAPI + Python. Current surface:

- `GET /health`
- SQLAlchemy models and Alembic migrations for PostgreSQL schema
- Private Cloudflare R2 storage service (`app.storage`)
- Authentication: `POST /auth/login`, `GET /users/me`
- Development seed: `python -m app.cli.seed_demo_users`

Document upload/download endpoints and grant APIs are not implemented yet.

## Setup

```powershell
cd D:\TrustVault\backend
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
```

Required in `backend/.env`:

- `DATABASE_URL`
- `JWT_SECRET_KEY` (long random secret, ≥ 32 characters)

Optional JWT settings: `JWT_ALGORITHM=HS256`, `JWT_ISSUER`, `JWT_AUDIENCE`, `ACCESS_TOKEN_EXPIRE_MINUTES`.

## Run API

```powershell
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

## Apply migrations

```powershell
alembic upgrade head
```

Authentication reuses the existing `users` table. No additional auth migration was required.

## Seed demo users (dev only)

```powershell
# DEMO_ADMIN_PASSWORD, DEMO_OWNER_PASSWORD, DEMO_VIEWER_PASSWORD must be set
python -m app.cli.seed_demo_users
```

Never auto-seeded on startup. Passwords are never printed. Existing demo accounts are left unchanged on re-run; conflicting roles abort the seed.

## Tests

```powershell
pytest -v
pytest -v tests/test_auth.py tests/test_seed_demo_users.py
```

## Token logout note

Stateless JWT access tokens are not revoked by a logout call in this codebase. Tokens remain valid until expiry unless a revocation mechanism is added later.

## Railway

On the Railway **backend** service, set `DATABASE_URL` and `JWT_SECRET_KEY` (and related JWT vars). Do not commit secrets.
