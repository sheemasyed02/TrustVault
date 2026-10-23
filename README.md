# TrustVault

Secure document-sharing web application for confidential company documents. Server-side document access control and an auditable activity trail are required before features are considered complete.

## Stack

| Layer | Technology |
| --- | --- |
| Frontend | Next.js (App Router), TypeScript, Tailwind CSS — **Vercel** |
| Backend | FastAPI, Python 3.12 — **Render** |
| Database | PostgreSQL — **Neon** (SQLAlchemy + Alembic) |
| Auth | Argon2id passwords (`pwdlib`), JWT access tokens (`PyJWT`) |
| File storage | Private Cloudflare **R2** (S3-compatible API; no public object URLs) |
| Backend tests | pytest |

Project rules: see [`AGENTS.md`](AGENTS.md).

## Current capabilities

- Login / logout (memory-only access token on the frontend; `Authorization: Bearer`)
- Role-aware navigation (ADMIN / OWNER / VIEWER) — **UI only**; API enforces authz
- Document upload (DOCX/PDF), list, details, search/filter, metadata edit, soft-delete
- Private R2 storage with opaque keys; downloads stream through the API after authz
- Per-document READ / EDIT grants with immediate revocation
- In-app DOCX preview/edit for owner and EDIT grantees
- Admin dashboard: user activate/deactivate, audit list/filters, hash-chain verify
- Durable audit hash chain (not DBA-proof; see [`THREATS.md`](THREATS.md))

## Repository layout

```
TrustVault/
  frontend/     Next.js app (Vercel)
  backend/      FastAPI app (Render)
  render.yaml   Render Blueprint (API only; secrets via dashboard)
  AGENTS.md     Product and agent rules
```

## Quick start (local)

### Backend

```powershell
cd D:\TrustVault\backend
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
# Set DATABASE_URL and JWT_SECRET_KEY in backend/.env (never commit secrets)
alembic upgrade head
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Health checks:

- Liveness: `GET http://127.0.0.1:8000/health`
- Readiness (DB): `GET http://127.0.0.1:8000/health/ready`

### Frontend

```powershell
cd D:\TrustVault\frontend
copy .env.example .env.local
# Set NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000
npm install
npm run dev
```

### Demo accounts (development only)

```powershell
cd D:\TrustVault\backend
.\.venv\Scripts\Activate.ps1
# DEMO_ADMIN_PASSWORD, DEMO_OWNER_PASSWORD, DEMO_VIEWER_PASSWORD in backend/.env
python -m app.cli.seed_demo_users
```

| Email | Role | Password env |
| --- | --- | --- |
| `snovasys@trustvault.demo` | ADMIN | `DEMO_ADMIN_PASSWORD` |
| `sheema@trustvault.demo` | OWNER | `DEMO_OWNER_PASSWORD` |
| `raj@trustvault.demo` | OWNER | `DEMO_OWNER_PASSWORD` |
| `priya@trustvault.demo` | OWNER | `DEMO_OWNER_PASSWORD` |
| `user@trustvault.demo` | VIEWER | `DEMO_VIEWER_PASSWORD` |
| `alex@trustvault.demo` | VIEWER | `DEMO_VIEWER_PASSWORD` |
| `jordan@trustvault.demo` | VIEWER | `DEMO_VIEWER_PASSWORD` |

Login never creates users. The API only authenticates existing rows. **Do not auto-seed on Render startup.** The seed CLI is idempotent for existing demo emails but will abort on role conflicts — check before running against a restored production database.

---

## Deployment architecture

```
Browser  →  Vercel (Next.js)
              │  NEXT_PUBLIC_API_BASE_URL
              ▼
            Render (FastAPI / uvicorn 0.0.0.0:$PORT)
              ├── Neon PostgreSQL (DATABASE_URL; optional DIRECT_URL for Alembic)
              └── Cloudflare R2 (private bucket; server-side only)
```

### Environment variables

#### Backend (Render)

| Name | Required | Purpose |
| --- | --- | --- |
| `DATABASE_URL` | Yes | App traffic (Neon pooled URL is fine) |
| `DIRECT_URL` | No | Neon **direct** (non-pooler) URL for Alembic only |
| `JWT_SECRET_KEY` | Yes | HS256 signing secret (≥ 32 random chars) |
| `JWT_ALGORITHM` | No | Must be `HS256` (default) |
| `JWT_ISSUER` / `JWT_AUDIENCE` | No | Token claims (defaults: `trustvault` / `trustvault-api`) |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | No | Default `30` |
| `CORS_ORIGINS` | Yes (prod) | Exact Vercel origin(s), comma-separated; **no `*`** |
| `R2_ACCOUNT_ID` | Yes | Cloudflare account id |
| `R2_ACCESS_KEY_ID` | Yes | R2 API token access key |
| `R2_SECRET_ACCESS_KEY` | Yes | R2 API token secret |
| `R2_BUCKET_NAME` | Yes | Private bucket name |
| `R2_ENDPOINT_URL` | Yes | `https://<ACCOUNT_ID>.r2.cloudflarestorage.com` |
| `APP_ENV` | No | e.g. `production` |
| `DEMO_*_PASSWORD` | No | Dev seed only — omit on production |

Never put database, JWT, or R2 secrets in the frontend or in git.

#### Frontend (Vercel)

| Name | Required | Purpose |
| --- | --- | --- |
| `NEXT_PUBLIC_API_BASE_URL` | Yes | Absolute API URL, e.g. `https://trustvault-api.onrender.com` |

### Render (backend)

Blueprint: [`render.yaml`](render.yaml) (no secrets embedded).

| Step | Command / setting |
| --- | --- |
| Root directory | `backend` |
| Runtime | Python `3.12.8` (`PYTHON_VERSION` / `runtime.txt`) |
| Build | `pip install -r requirements.txt` |
| Start | `uvicorn app.main:app --host 0.0.0.0 --port $PORT` |
| Health check path | `/health` |

Manual create (if not using Blueprint):

1. New **Web Service** → connect this repo → Root Directory `backend`.
2. Build / start commands as above.
3. Set every required env var in the Render dashboard.
4. Deploy, then open `https://<service>/health` and `/health/ready`.

**Do not** configure a start/release command that runs `alembic upgrade head` on every boot, seeds demo users, or drops/recreates the database.

### Vercel (frontend)

1. Import the repo; set **Root Directory** to `frontend`.
2. Framework preset: Next.js (default `npm run build` / `next start`).
3. Set `NEXT_PUBLIC_API_BASE_URL` to the Render HTTPS origin (Production + Preview as needed).
4. Deploy. Add the resulting `https://<project>.vercel.app` (and custom domain) to backend `CORS_ORIGINS`.

### Neon (PostgreSQL)

This environment could not resolve the Neon hostname at audit time. Before migrating production:

1. In Neon, copy the **pooled** connection string → Render `DATABASE_URL`.
2. Copy the **direct** connection string → Render/local `DIRECT_URL` (recommended for Alembic).
3. From a machine that can reach Neon:

```powershell
cd D:\TrustVault\backend
.\.venv\Scripts\Activate.ps1
# Temporarily point env at Neon DIRECT_URL (do not commit)
$env:DATABASE_URL = "<neon-direct-or-leave-as-app-url>"
$env:DIRECT_URL = "<neon-direct-url>"
alembic current
```

Expected head revision in this repo: **`c3d4e5f6a7b8`**.

#### Migration safety

- **Never** drop, recreate, or truncate the production database.
- **Never** run `python -m app.cli.seed_demo_users` against production without checking for existing users (the command is idempotent for known demo emails but aborts on role conflicts and is still a write).
- If `alembic current` already shows `c3d4e5f6a7b8` and tables exist (e.g. restored from pgAdmin), **do not** re-run a full schema create — you are done.
- If `alembic_version` is missing but tables were restored manually, stamp after verifying schema matches models:

```powershell
# Only after confirming tables/columns match the migration history
alembic stamp head
```

- If `alembic current` is behind `head` and you need additive migrations only:

```powershell
# Prefer DIRECT_URL for DDL on Neon
$env:DIRECT_URL = "<neon-direct-url>"
alembic upgrade head
alembic current
```

Verification query (read-only):

```sql
SELECT version_num FROM alembic_version;
SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY 1;
```

Application traffic continues to use `DATABASE_URL`. Alembic uses `DIRECT_URL` when set, otherwise `DATABASE_URL`.

### Cloudflare R2

- Keep the bucket **private** (no public access).
- Configure the five `R2_*` variables on Render only.
- Uploads/downloads go through authorized FastAPI routes; the browser never receives R2 secrets or long-lived public object URLs.

---

## Post-deploy smoke checks

Replace hosts with your real Vercel and Render URLs. Do not paste tokens into shared logs.

```powershell
# 1) Liveness / readiness
curl.exe -s https://<api-host>/health
curl.exe -s https://<api-host>/health/ready

# 2) Login + current user
curl.exe -s -X POST https://<api-host>/auth/login -H "Content-Type: application/json" -d "{\"email\":\"<user>\",\"password\":\"<password>\"}"
# Use access_token from the response:
curl.exe -s https://<api-host>/users/me -H "Authorization: Bearer <token>"

# 3) Authorized document list
curl.exe -s "https://<api-host>/documents?page=1&page_size=10" -H "Authorization: Bearer <token>"
```

Then in the browser (Vercel origin):

1. Login / logout
2. Upload a small DOCX/PDF; confirm list + detail
3. Download (bytes via API, not a public R2 URL)
4. Grant READ to another user; confirm they can open; revoke; confirm 404/deny
5. As ADMIN: audit list + integrity verify

Health JSON must never include connection strings, passwords, or document contents.

---

## Tests

### Backend (targeted / CI-friendly)

```powershell
cd D:\TrustVault\backend
.\.venv\Scripts\Activate.ps1
# Requires TEST_DATABASE_URL → local trustvault_test (see backend/.env.example)
pytest -q tests/test_health.py tests/test_database_url.py tests/test_test_database_config.py
```

### Backend (full suite — only when explicitly requested)

```powershell
pytest -q
```

### Frontend

```powershell
cd D:\TrustVault\frontend
npm test -- --run
npm run build
```

---

## Troubleshooting

| Symptom | Likely cause |
| --- | --- |
| Browser CORS error | Vercel origin missing from `CORS_ORIGINS` (exact scheme/host; no trailing slash mismatch) |
| `/health` OK but `/health/ready` 503 | `DATABASE_URL` wrong, Neon paused, or SSL params missing |
| Login 500 “Authentication is not configured” | `JWT_SECRET_KEY` missing/short |
| Upload/download 503 storage errors | Missing/invalid `R2_*` env vars or bucket permissions |
| Frontend “Unable to reach the TrustVault API” | Wrong `NEXT_PUBLIC_API_BASE_URL` or Render service asleep/failed |
| Alembic hangs / pooler DDL errors | Set `DIRECT_URL` to Neon’s non-pooler host for migrations |

## Documentation

- [`AGENTS.md`](AGENTS.md) — product and agent rules
- [`ACCEPTANCE.md`](ACCEPTANCE.md) — requirement → test → manual verification matrix
- [`PERMISSIONS.md`](PERMISSIONS.md) — role / resource / action matrix
- [`API_DOCUMENTATION.md`](API_DOCUMENTATION.md) — real HTTP routes
- [`THREATS.md`](THREATS.md) — threat model and residual risks
- [`PROMPTS.md`](PROMPTS.md) — dated AI assistance log
- [`backend/README.md`](backend/README.md) — backend-focused notes
- [`frontend/README.md`](frontend/README.md) — frontend-focused notes
