# TrustVault

Secure document-sharing web application for confidential company documents. Server-side document access control and an auditable activity trail are required before features are considered complete.

## Planned stack

| Layer | Technology |
| --- | --- |
| Frontend | Next.js 16 (App Router), TypeScript, Tailwind CSS |
| Backend | FastAPI, Python 3.12 |
| Database | PostgreSQL, SQLAlchemy, Alembic |
| File storage | Private Cloudflare R2 (S3-compatible API) |
| Backend tests | pytest |
| Hosting | Vercel (frontend), Railway (API + PostgreSQL) |

Project rules: see [`AGENTS.md`](AGENTS.md).

## Current status

Scaffold only:

- `frontend/` — Next.js app shell with a TrustVault landing/login entry page. No real authentication.
- `backend/` — FastAPI app with configuration, CORS, centralized errors, and `GET /health`. No auth, documents, grants, or database tables yet.

## Repository layout

```
frontend/   Next.js client
backend/    FastAPI API
AGENTS.md   Agent and product rules
```

## Quick start

### Backend

```bash
cd backend
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Health check: http://127.0.0.1:8000/health

### Frontend

```bash
cd frontend
copy .env.example .env.local
npm install
npm run dev
```

App: http://localhost:3000

### Backend tests

```bash
cd backend
.\.venv\Scripts\Activate.ps1
pytest -v
```

## Documentation

- [`PROMPTS.md`](PROMPTS.md) — dated AI task log
- [`THREATS.md`](THREATS.md) — threat model (planned vs implemented)
- [`API_DOCUMENTATION.md`](API_DOCUMENTATION.md) — API surface
- [`PERMISSIONS.md`](PERMISSIONS.md) — roles and grants

Never commit `.env` files or real secrets. Use the `.env.example` placeholders only.
