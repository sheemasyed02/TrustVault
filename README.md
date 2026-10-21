# TrustVault

Secure document-sharing web application for confidential company documents. Server-side document access control and an auditable activity trail are required before features are considered complete.

## Stack

| Layer | Technology |
| --- | --- |
| Frontend | Next.js (App Router), TypeScript, Tailwind CSS |
| Backend | FastAPI, Python 3.12 |
| Database | PostgreSQL, SQLAlchemy, Alembic |
| Auth | Argon2id passwords (`pwdlib`), JWT access tokens (`PyJWT`) |
| File storage | Private Cloudflare R2 (S3-compatible API) |
| Backend tests | pytest |
| Hosting | Vercel (frontend), Railway (API + PostgreSQL) |

Project rules: see [`AGENTS.md`](AGENTS.md).

## Current capabilities

- Login / logout (memory-only access token on the frontend)
- Role-aware navigation (ADMIN / OWNER / VIEWER) — **UI only**; API enforces authz
- Document upload (DOCX), list, details, search/filter, metadata edit, soft-delete
- Private R2 storage with opaque keys; downloads stream through the API
- Per-document READ / EDIT grants with immediate revocation
- In-app DOCX preview/edit for owner and EDIT grantees
- Admin dashboard: user activate/deactivate, audit list/filters, hash-chain verify
- Durable audit hash chain (not DBA-proof; see [`THREATS.md`](THREATS.md))

## Quick start

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

| Email | Role |
| --- | --- |
| `snovasys@trustvault.demo` | ADMIN |
| `sheema@trustvault.demo` | OWNER |
| `user@trustvault.demo` | VIEWER |

## Tests

### Backend (full suite)

```powershell
cd D:\TrustVault\backend
.\.venv\Scripts\Activate.ps1
pytest -q
```

### Security matrix (isolated regression cases)

```powershell
cd D:\TrustVault\backend
.\.venv\Scripts\Activate.ps1
pytest -q tests/security/
```

Documented cases cover owner / READ / EDIT / unrelated / ADMIN, revocation, deactivation, IDOR, and audit gates. See test docstrings in `tests/security/test_security_matrix.py`.

### Frontend

```powershell
cd D:\TrustVault\frontend
npm test -- --run
npm run build
```

### Alembic

```powershell
cd D:\TrustVault\backend
.\.venv\Scripts\Activate.ps1
alembic upgrade head
alembic current
```

## Security regression demonstration (authorization removal)

Interview evaluators may temporarily remove an authorization check. Reproduce detection locally (do **not** commit the vulnerable change):

1. Run the baseline IDOR download test (must pass with **404**):

```powershell
cd D:\TrustVault\backend
.\.venv\Scripts\Activate.ps1
pytest tests/test_document_access.py::test_unauthorized_download_returns_no_bytes -q
```

2. In a disposable edit only, remove the `require_document_read(...)` call from `GET /documents/{document_id}/download` in `app/api/documents.py` and load the document without an access check.

3. Re-run the same test — it must **fail** (unauthorized caller gets **200** and file bytes).

4. Restore the original `require_document_read` block immediately.

5. Re-run the same test and `pytest -q tests/security/` — both must pass.

This demonstration was executed during Task 16; the vulnerable edit was never committed. Details: [`THREATS.md`](THREATS.md).

## Documentation

- [`AGENTS.md`](AGENTS.md) — product and agent rules
- [`ACCEPTANCE.md`](ACCEPTANCE.md) — requirement → test → manual verification matrix
- [`PERMISSIONS.md`](PERMISSIONS.md) — role / resource / action matrix
- [`API_DOCUMENTATION.md`](API_DOCUMENTATION.md) — real HTTP routes
- [`THREATS.md`](THREATS.md) — threat model and residual risks
- [`PROMPTS.md`](PROMPTS.md) — dated AI assistance log
