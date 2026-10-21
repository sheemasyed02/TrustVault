# TrustVault

Secure document-sharing web application for confidential company documents. Server-side document access control and an auditable activity trail are required before features are considered complete.

## Planned stack

| Layer | Technology |
| --- | --- |
| Frontend | Next.js 16 (App Router), TypeScript, Tailwind CSS |
| Backend | FastAPI, Python 3.12 |
| Database | PostgreSQL, SQLAlchemy, Alembic |
| Auth | Argon2id passwords (`pwdlib`), JWT access tokens (`PyJWT`) |
| File storage | Private Cloudflare R2 (S3-compatible API) |
| Backend tests | pytest |
| Hosting | Vercel (frontend), Railway (API + PostgreSQL) |

Project rules: see [`AGENTS.md`](AGENTS.md).

## Current status

- `frontend/` — landing/login shell only (not wired to real auth APIs yet).
- `backend/` — `GET /health`, PostgreSQL schema, private R2 service, secure auth, document authorization service, and:
  - `POST /auth/login`
  - `GET /users/me`
  - `POST /documents` (OWNER upload to private R2)
- Document list/download/sharing/deletion APIs are not implemented yet.

## Quick start

### Backend

```powershell
cd D:\TrustVault\backend
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
# Set DATABASE_URL and JWT_SECRET_KEY in backend/.env (never commit secrets)
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

- Health: http://127.0.0.1:8000/health
- Login: `POST http://127.0.0.1:8000/auth/login`
- Current user: `GET http://127.0.0.1:8000/users/me` with `Authorization: Bearer <token>`

### Database migrations

No new migration was required for authentication (existing `users` table is reused).

```powershell
cd D:\TrustVault\backend
.\.venv\Scripts\Activate.ps1
alembic upgrade head
```

### Demo accounts (development only)

Demo users are **not** created on app startup. Seed them explicitly:

```powershell
cd D:\TrustVault\backend
.\.venv\Scripts\Activate.ps1
# Set DEMO_ADMIN_PASSWORD, DEMO_OWNER_PASSWORD, DEMO_VIEWER_PASSWORD in backend/.env
python -m app.cli.seed_demo_users
```

| Email | Role |
| --- | --- |
| `snovasys@trustvault.demo` | ADMIN |
| `sheema@trustvault.demo` | OWNER |
| `user@trustvault.demo` | VIEWER |

These are local/demo identities only. Do not use them as production accounts. Re-running the seed does not silently change an existing demo user's password or role.

### Auth tests

```powershell
cd D:\TrustVault\backend
.\.venv\Scripts\Activate.ps1
pytest -v tests/test_auth.py tests/test_seed_demo_users.py
# or full suite:
pytest -v
```

### Frontend

```powershell
cd D:\TrustVault\frontend
copy .env.example .env.local
npm install
npm run dev
```

App: http://localhost:3000

## Documentation

- [`PROMPTS.md`](PROMPTS.md) — dated AI task log
- [`THREATS.md`](THREATS.md) — threat model (planned vs implemented)
- [`API_DOCUMENTATION.md`](API_DOCUMENTATION.md) — API surface
- [`PERMISSIONS.md`](PERMISSIONS.md) — roles and grants

Never commit `.env` files or real secrets. Use the `.env.example` placeholders only.
