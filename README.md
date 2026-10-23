# TrustVault

Secure document-sharing for confidential company files. Access decisions are enforced **on the server** against PostgreSQL; private file bytes stay in Cloudflare R2 and are streamed only after authorization. An append-only audit hash chain records security-relevant successes and denials for administrator review.

This is not a static dashboard or client-only ACL demo. Hiding a button in the UI is not authorization.

## Problem

Teams need to share sensitive documents without:

- Guessable public download links that outlive permission changes
- Trusting the browser for role or owner claims
- Losing visibility into who attempted access (including denials)

TrustVault addresses that with JWT authentication, document-level grants, private object storage, and a durable audit trail.

## Features (implemented)

- Login / logout with Argon2id password hashes and short-lived JWT access tokens (frontend keeps the token **in memory only**)
- Platform roles: `ADMIN`, `OWNER`, `VIEWER` (navigation hints only — API re-loads role/`is_active` from PostgreSQL)
- Document-level access: ownership (`documents.owner_id`) plus `READ` / `EDIT` grants
- OWNER upload (**DOCX only**, size/type/content checks), list/search/filter, metadata edit, soft-delete
- In-app DOCX preview; content edit for owner or active EDIT grantee
- Authorized download streamed through FastAPI (no public/presigned R2 URLs)
- Grant / revoke with **immediate** effect on the next protected request
- ADMIN user activate/deactivate, audit event list/filters, hash-chain integrity verify
- Owner promotion requests (VIEWER → OWNER) with admin review
- Health: `GET /health` (liveness), `GET /health/ready` (DB readiness)

Details: [`PERMISSIONS.md`](PERMISSIONS.md), [`API_DOCUMENTATION.md`](API_DOCUMENTATION.md), [`THREATS.md`](THREATS.md).

## Architecture overview

```
Browser (Next.js / Vercel)
   │  Authorization: Bearer <access_token>
   │  NEXT_PUBLIC_API_BASE_URL → API origin only
   ▼
FastAPI (Render) ── validates JWT + loads active user from PostgreSQL
   │
   ├─ document_authorization  ← ownership + active grants (revoked_at IS NULL)
   ├─ private Cloudflare R2   ← opaque storage_key from DB only
   └─ audit_events hash chain ← SUCCESS / DENIED metadata (not file bytes)
              │
              ▼
         Neon PostgreSQL
```

### Request flow (actual)

1. User signs in via `POST /auth/login` → JWT (`sub` = user id). Role is **not** authorization proof.
2. Protected routes call `get_current_user`: verify signature/exp/iss/aud, load user from DB, reject inactive accounts.
3. Document routes call `document_authorization` against **current** ownership/grants (not client fields, not cached JWT permissions).
4. Allowed uploads/downloads/edits use the private R2 service with server-generated keys.
5. Relevant successes and denials append to `audit_events` (hash chain + advisory lock).
6. `GET /admin/audit/integrity` re-hashes the chain and reports `valid` / reason codes. A DBA who can rewrite the whole table can still forge a consistent chain — see limitations below.

### Why these choices

| Choice | Reason |
| --- | --- |
| PostgreSQL (Neon) | Relational integrity for users, grants, soft-delete, and concurrent audit locking |
| FastAPI | Explicit deps for authn/authz; streaming downloads; clear HTTP status mapping |
| Next.js | App Router UI with role-aware navigation that still calls the real API |
| Private R2 | Bytes never exposed as long-lived public URLs; revoke works on the next API check |
| Server-side authorization | Prevents IDOR and UI bypass; every protected action re-checks DB state |

### Trade-offs and residual limits

- **Free-tier / cold starts:** Render free web services may sleep; first request after idle can be slow or time out. Neon free projects may pause and need wake-up before `/health/ready` succeeds.
- **Audit chain:** Detects many single-row / link tampers; **does not** defeat an attacker who rewrites the database and recalculates the entire chain (no external anchor).
- **No app-level login rate limit** — rely on host/WAF if needed.
- **No server-side JWT revocation list** — logout clears browser memory; token valid until expiry if the account stays active.
- **R2/DB partial failures:** Upload compensates with R2 delete if DB insert fails; delete soft-deletes first then removes R2 (503 + tombstone if R2 fails). Orphan private objects may remain until ops cleanup.
- **Monitoring / backups:** Not productized in-app; use Neon/Render/R2 provider tooling.

## Technology stack

| Layer | Technology |
| --- | --- |
| Frontend | Next.js (App Router), TypeScript, Tailwind CSS — intended host **Vercel** |
| Backend | FastAPI, Python 3.12, uvicorn — intended host **Render** |
| Database | PostgreSQL via SQLAlchemy 2 + Alembic — intended host **Neon** |
| Auth | Argon2id (`pwdlib`), JWT HS256 (`PyJWT`) |
| Files | Private Cloudflare R2 (S3-compatible, boto3) |
| Tests | pytest (backend), Vitest (frontend) |

Rules: [`AGENTS.md`](AGENTS.md).

## Repository layout

```
TrustVault/
  frontend/              Next.js app
  backend/               FastAPI app + Alembic + pytest
  render.yaml            Render Blueprint (no secrets)
  AGENTS.md              Product / agent rules
  THREATS.md             Threat model
  PERMISSIONS.md         Authz matrix
  API_DOCUMENTATION.md   HTTP routes
  PROMPTS.md             AI assistance log
  DEMO.md                Five-minute demo script
  INTERVIEW_PREP.md      Interview Q&A
  ACCEPTANCE.md          Acceptance evidence matrix
```

## Deployed URLs

**Not verified in this workspace.** Local frontend env points at `http://127.0.0.1:8000` only. Do not treat placeholder hosts (for example `*.onrender.com` / `*.vercel.app` in setup docs) as live until you open them and confirm `/health` and the UI.

When you deploy, record the real URLs here after testing:

| Surface | URL | Verified |
| --- | --- | --- |
| Frontend (Vercel) | _add after deploy_ | No |
| Backend (Render) | _add after deploy_ | No |

Local API docs (when `APP_ENV` is not `production`): `http://127.0.0.1:8000/docs`  
Route reference in-repo: [`API_DOCUMENTATION.md`](API_DOCUMENTATION.md)  
In production (`APP_ENV=production`), `/docs`, `/redoc`, and `/openapi.json` are disabled.

## Local setup

### Backend

```powershell
cd D:\TrustVault\backend
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
# Set DATABASE_URL, JWT_SECRET_KEY, R2_*, CORS_ORIGINS (placeholders only in git)
alembic upgrade head
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

- Liveness: `GET http://127.0.0.1:8000/health`
- Readiness: `GET http://127.0.0.1:8000/health/ready`

### Frontend

```powershell
cd D:\TrustVault\frontend
copy .env.example .env.local
# NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000
npm install
npm run dev
```

Open `http://localhost:3000`.

### PostgreSQL / Neon and safe migrations

**Local**

```powershell
# Example: create app + test databases
psql -h 127.0.0.1 -p 5432 -U postgres -c "CREATE DATABASE trustvault_db;"
psql -h 127.0.0.1 -p 5432 -U postgres -c "CREATE DATABASE trustvault_test;"
```

Set `DATABASE_URL` / `TEST_DATABASE_URL` in `backend/.env` (never commit real passwords).

**Neon (production-intended)**

1. Pooled connection string → application `DATABASE_URL` (keep `sslmode=require` query params).
2. Direct (non-pooler) string → optional `DIRECT_URL` for Alembic DDL.
3. From a network that can reach Neon:

```powershell
cd D:\TrustVault\backend
.\.venv\Scripts\Activate.ps1
$env:DIRECT_URL = "<neon-direct-url-placeholder>"
alembic current
```

Repo head revision: **`c3d4e5f6a7b8`**.

**Safety**

- Never drop, recreate, or truncate production data for “convenience.”
- Do not auto-run migrations or seed on every web-service start.
- If schema was restored from pgAdmin and already matches head, prefer `alembic stamp head` only after verifying tables — not a blind `upgrade` that you do not understand.
- If behind head with additive migrations only: `alembic upgrade head` then `alembic current`.

Read-only verification:

```sql
SELECT version_num FROM alembic_version;
SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY 1;
```

### Required environment variables (names + placeholders)

See `backend/.env.example` and `frontend/.env.example`.

**Backend:** `DATABASE_URL`, optional `DIRECT_URL`, `JWT_SECRET_KEY`, `JWT_ALGORITHM`, `JWT_ISSUER`, `JWT_AUDIENCE`, `ACCESS_TOKEN_EXPIRE_MINUTES`, `CORS_ORIGINS`, `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET_NAME`, `R2_ENDPOINT_URL`, `APP_ENV`, optional `DEMO_*_PASSWORD`, `TEST_DATABASE_URL` (pytest only).

**Frontend:** `NEXT_PUBLIC_API_BASE_URL` only.

Never put DB passwords, JWT secrets, or R2 secrets in frontend env, README values, or git.

### Private Cloudflare R2

1. Create a bucket; leave it **private** (no public access).
2. Create an API token with object read/write on that bucket.
3. Set the five `R2_*` variables on the backend host.
4. Endpoint form: `https://<ACCOUNT_ID>.r2.cloudflarestorage.com`
5. Confirm downloads never return a public object URL — only streamed API responses after authz.

### Demo accounts (development seed only)

```powershell
cd D:\TrustVault\backend
.\.venv\Scripts\Activate.ps1
# Set DEMO_ADMIN_PASSWORD, DEMO_OWNER_PASSWORD, DEMO_VIEWER_PASSWORD in backend/.env
python -m app.cli.seed_demo_users
```

| Email | Role | Password comes from |
| --- | --- | --- |
| `snovasys@trustvault.demo` | ADMIN | `DEMO_ADMIN_PASSWORD` |
| `sheema@trustvault.demo` | OWNER | `DEMO_OWNER_PASSWORD` |
| `raj@trustvault.demo` | OWNER | `DEMO_OWNER_PASSWORD` |
| `priya@trustvault.demo` | OWNER | `DEMO_OWNER_PASSWORD` |
| `user@trustvault.demo` | VIEWER | `DEMO_VIEWER_PASSWORD` |
| `alex@trustvault.demo` | VIEWER | `DEMO_VIEWER_PASSWORD` |
| `jordan@trustvault.demo` | VIEWER | `DEMO_VIEWER_PASSWORD` |

Passwords are **not** printed by the seed command and must not be pasted into this README. Login never creates users. Do not auto-seed on Render startup.

## Tests

Requires isolated `TEST_DATABASE_URL` (name must contain `test`; never production `neondb`).

```powershell
cd D:\TrustVault\backend
.\.venv\Scripts\Activate.ps1
pytest -q
```

```powershell
cd D:\TrustVault\frontend
npm test -- --run
npm run build
```

Security matrix: `pytest -q tests/security/`

Authz-removal demonstration procedure (local, disposable edit — **do not commit**): see [`THREATS.md`](THREATS.md) and [`DEMO.md`](DEMO.md). It has been performed in earlier tasks; vulnerable code was restored and never left committed.

## Security decisions (summary)

- Every protected document/admin route authenticates then authorizes server-side.
- Ownership and grants come from PostgreSQL; client `owner_id` / `storage_key` / role claims are ignored or rejected.
- READ cannot edit metadata; EDIT cannot grant or delete; ADMIN cannot download content without an explicit grant.
- Soft-deleted documents are unservable (404).
- Audit APIs are ADMIN-only and return metadata, not file bytes.
- CORS is an explicit origin list (no `*` with credentials).

Full model: [`THREATS.md`](THREATS.md), [`PERMISSIONS.md`](PERMISSIONS.md).

## Known limitations / unfinished work

- Live production URL verification depends on your deployed hosts (blank table above until tested)
- Application-layer rate limiting / lockout not implemented
- No refresh-token rotation or server logout revocation store
- No automated orphan-R2 sweeper
- Audit chain not externally anchored
- DOCX→PDF download conversion quality depends on LibreOffice availability (fallback is limited)
- Mammoth HTML preview is not a full XSS sanitizer product

## Five-minute demo and interview prep

- Live demo script: [`DEMO.md`](DEMO.md)
- Interview Q&A: [`INTERVIEW_PREP.md`](INTERVIEW_PREP.md)

## Deployment (Render / Vercel / Neon / R2)

Blueprint: [`render.yaml`](render.yaml).

| Backend | Value |
| --- | --- |
| Root | `backend` |
| Build | `pip install -r requirements.txt` |
| Start | `uvicorn app.main:app --host 0.0.0.0 --port $PORT` |
| Health | `/health` |

Frontend root: `frontend`. Set `NEXT_PUBLIC_API_BASE_URL` to the Render HTTPS origin; add that Vercel origin to `CORS_ORIGINS`.

Do not run destructive DB commands or auto-seed on service boot.

## Troubleshooting

| Symptom | Likely cause |
| --- | --- |
| Browser CORS error | Vercel origin missing from `CORS_ORIGINS` |
| `/health` OK, `/health/ready` 503 | Bad `DATABASE_URL`, Neon paused, or SSL params missing |
| Login misconfigured | `JWT_SECRET_KEY` missing/short |
| Upload/download storage errors | Missing/invalid `R2_*` or private bucket policy |
| Frontend cannot reach API | Wrong `NEXT_PUBLIC_API_BASE_URL` or cold/stopped API |
| Alembic issues on Neon pooler | Use `DIRECT_URL` (non-pooler) for migrations |

## Documentation index

- [`AGENTS.md`](AGENTS.md) — product and agent rules  
- [`ACCEPTANCE.md`](ACCEPTANCE.md) — requirement → test matrix  
- [`PERMISSIONS.md`](PERMISSIONS.md) — role / grant matrix  
- [`API_DOCUMENTATION.md`](API_DOCUMENTATION.md) — HTTP routes  
- [`THREATS.md`](THREATS.md) — threats and residuals  
- [`PROMPTS.md`](PROMPTS.md) — AI assistance log  
- [`DEMO.md`](DEMO.md) — five-minute demo  
- [`INTERVIEW_PREP.md`](INTERVIEW_PREP.md) — interview answers  
- [`backend/README.md`](backend/README.md) · [`frontend/README.md`](frontend/README.md)
