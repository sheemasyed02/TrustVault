# TrustVault — How I used AI (PROMPTS.md)

This is my working log. I used Cursor to help write code, but I gave the rules, checked the output, and fixed things when the tool was wrong.

---

## Task 1 — Scaffold (frontend + backend shell)

**What I asked for:** Next.js shell + FastAPI health API. Keep `AGENTS.md` and `.gitignore`. No fake login, no fake documents, no database yet.

**What went wrong / what I fixed:**
1. `create-next-app` pulled a Next.js version with a known CVE. I had it upgraded to **16.4.2**.
2. After the upgrade, ESLint broke (circular JSON with FlatCompat). I made it use the Next 16 flat config instead.
3. Login form had an `aria-disabled` lint warning. Removed it; form stayed disabled on purpose for the scaffold.
4. Frontend `.gitignore` was hiding `.env.example`. Added an exception so the example file can be committed.

**How I checked:** backend `pytest` (health tests passed); frontend `lint` + `build` after the ESLint fix.

---

## Task 2 — PostgreSQL schema (Alembic)

**What I asked for:** Real tables for users, documents, permissions, audit events. Use `DATABASE_URL` only. No SQLite fallback.

**What I caught:**
- Railway’s `postgres.railway.internal` host does **not** work from my laptop. Migrations had to run against local Postgres (or a public URL).
- I told the tool not to invent tables by hand in a dashboard — generate migrations and give the apply command.

**How I checked:** `alembic upgrade head`, schema verify script, pytest for constraints/indexes.

---

## Task 3 — Private R2 storage service

**What I asked for:** boto3 helper for private R2 only. No public URLs. No document HTTP APIs yet. Tests with mocks.

**What I directed:** Do not add presigned download helpers. Keep secrets out of logs. Fail clearly if R2 env vars are missing.

**How I checked:** pytest with mocked boto3 (not a live Cloudflare bucket in CI).

---

## Task 4 — Login + JWT + demo seed

**What I asked for:** Argon2id passwords, JWT login, `/users/me`, demo user seed from env passwords. No document permission APIs yet.

**What I directed:**
- Login errors must be **generic** (do not say “email not found”).
- Role must come from the **database**, not from the JWT payload as proof.
- Seed must not silently reset passwords every run.

**How I checked:** auth + seed pytest suite.

---

## Task 5 — Centralized document authorization

**What I asked for:** One shared policy for owner / READ / EDIT / ADMIN / inactive / revoked. FastAPI deps for later routes. No upload/download yet.

**What I caught:** Seed tests failed when real demo users already existed in my local DB. Isolation was fixed so tests clear those emails inside the rolled-back transaction.

**How I checked:** dedicated authorization tests (owner, grants, revoke, ADMIN without grant, soft-delete, guessed IDs).

---

## Task 6 — Secure upload (`POST /documents`)

**What I asked for:** OWNER-only upload to R2 + Postgres metadata. Validate type/size. Clean up R2 if DB insert fails.

**What I caught:**
- `python-multipart` was missing — uploads would not work until it was added.
- Client must not be allowed to set `owner_id` or `storage_key`.

**How I checked:** upload pytest suite with mocked R2; full backend suite after.

---

## Task 7 — List, metadata, download

**What I asked for:** `GET /documents`, `GET /documents/{id}`, `GET /documents/{id}/download`. Filter in SQL. Stream from R2 only after authz. No frontend.

**What I caught (AI / code was wrong or unsafe until fixed):**
1. Storage error mocks used a wrong constructor (`operation=`). Fixed to match real exception classes.
2. Download filenames needed stronger sanitizing (CR/LF / quotes) so headers stay safe.
3. Owner-email filter + `joinedload` risked messy joins; switched to a subquery.

**How I checked:** access tests prove unauthorized downloads never call R2; revoke then same token is denied.

---

## Task 8 — Sharing (grant / revoke)

**What I asked for:** Owner list/grant/revoke READ|EDIT. Immediate revoke. Tests with same JWT before and after revoke.

**What I caught:**
- Using full `session.rollback()` after an audit failure wiped the whole test/request transaction. Fixed to only undo the grant/revoke change.
- Regrant must create a **new** row, not silently clear `revoked_at` on the old one.

**How I checked:** sharing tests + full suite; same-token revoke tests for metadata/download.

---

## Task 9 — Metadata edit + soft-delete

**What I asked for:** `PATCH` for title/category/description only. Owner-only `DELETE` with soft-delete + R2 cleanup. Honest failure if R2 cleanup fails.

**What I directed / fixed:**
1. Soft-delete **first**, then R2 delete — so the file stops being served even if R2 cleanup fails (return 503, not fake success).
2. Full pytest hit Postgres **“too many clients”**. Fixed test DB engine to use `NullPool` under pytest so connections do not pile up.

**How I checked:** mutation tests for mass-assignment, revoke-then-edit, R2 failure honesty; full suite **170 passed** after the pool fix.

---

## Task 10 — Connect Next.js login to FastAPI

**What I asked for:** Real login against the backend. Token in **memory only**. Protected dashboard shell. No document screens yet.

**What I directed:**
- Read the real API docs first (JSON login, not form data).
- Do not store JWT in localStorage/sessionStorage.
- Do not claim logout revokes the server JWT (backend has no revocation yet).
- CORS must allow both `localhost:3000` and `127.0.0.1:3000` if we open either URL.

**What I caught:** Vitest left old DOM nodes between tests (“multiple Login buttons”). Added proper `cleanup()` so tests stay isolated.

**How I checked:** `npm test` (17 passed), `npm run lint`, `npm run build` (Next.js 16.4.2 succeeded).

---

## Task 11 — Document dashboard + search (2026-10-21)

**What I asked for:** Real dashboard / My Documents / Shared With Me against `GET /documents`. No fake rows. No upload/edit/share forms yet. Server-side search + pagination only.

**What the backend actually supports (verified, not invented):**
- `GET /documents` with `title`, `owner_id`, `owner_email`, `category`, `created_from`, `created_to`, `page`, `page_size` (≤100), plus `total` / `total_pages`.
- Owner summary on each list item; no grant level (READ/EDIT) on the list response.
- No dedicated Shared With Me endpoint and no activity-feed endpoint.
- Detail / download / delete exist; metadata edit + permission management APIs exist but this task only wires list + open + download + owner delete (no forms).

**What went wrong / what I fixed:**
1. Build failed because pages imported `toApiDateBound` while the helper was named `toApiDateStart` — renamed the export.
2. Stale `.next` types still pointed at the old `/dashboard` path after the route group move — cleared `.next` and rebuilt.
3. React Compiler ESLint blocked `setState` inside effects / ref writes during render in the list hook and filters — rewrote to adjust state when filters change and to set loading inside async work.

**How Shared With Me works without a dedicated API:** call authorized `GET /documents`, then show rows where `owner.id !== me`. Dashboard “shared” count is `accessible total − owned total` and is labeled as an estimate. READ/EDIT badges are omitted (API gap).

**How I checked (frontend):**
- `npm test` — **23 passed** (6 files)
- `npm run lint` — **0 errors** (1 existing custom-font warning in root layout)
- `npm run build` — **succeeded** (Next.js 16.4.2)

---

## Task 12 — Document upload / details / edit / download / sharing UI (2026-10-21)

**What I asked for:** Wire the real document lifecycle to FastAPI — upload, details, download, metadata PATCH, grant/revoke, owner delete. No admin/audit UI. No fake users or fake success.

**Actual APIs used:**
- `POST /documents` (multipart: file, title, category, description)
- `GET /documents/{id}`, `PATCH /documents/{id}`, `DELETE /documents/{id}`, `GET …/download`
- `GET/POST /documents/{id}/permissions`, `DELETE …/permissions/{user_id}`

**Gaps I did not invent around:**
- No user search/list endpoint — grant UI takes a registered **user UUID** and states the missing API.
- Detail response has no effective READ/EDIT field — non-owners may attempt metadata edit; server 403 hides the form afterward. READ vs EDIT badges only appear on the owner’s grant list.

**What went wrong / fixed:**
1. Lifecycle UI test used an invalid UUID variant nibble, so client validation blocked the grant (looked like a grant bug). Fixed the fixture UUID.
2. React Compiler lint flagged sync `setState` from the permissions `useEffect` — moved loading state into the async path.

**How I checked (frontend):**
- `npm test` — **42 passed** (11 files)
- `npm run lint` — **0 errors** (1 existing font warning)
- `npm run build` — **succeeded**

---

## Task 13 — Owner/EDIT in-app edit; READ view-only (2026-10-21)

**What I asked for:** On the document view page, owners can edit. Viewers with READ only read; viewers with EDIT can edit content/metadata like the owner (still no share/delete).

**What was built:**
- Detail API returns `your_access` (`OWNER` | `EDIT` | `READ`) from PostgreSQL.
- `PUT /documents/{id}/content` rebuilds DOCX for owner/EDIT; READ gets 403.
- Detail UI gates preview editor + metadata form on `your_access`; sharing/delete remain owner-only.

**How I checked:** backend content-edit tests + frontend access/API tests (see task completion report).

---

## Task 16 — Security matrix, threat model, authz-removal demo (2026-10-21)

**What I asked for:** Inspect routes/authz/tests/docs; add a dedicated security regression matrix; close documentation gaps in THREATS/PERMISSIONS/README; demonstrate that removing download authorization fails a real IDOR test; do not invent controls.

**Actual AI assistance:** Cursor drafted `tests/security/` fixtures and matrix cases, expanded THREATS.md, and refreshed README test/demo instructions. I corrected invalid `@security.test` emails (Pydantic rejected reserved TLD), grant status **201**, and over-strict filename assertions (CR/LF neutralization is the real header-injection control).

**Authz-removal demo (not committed):**
1. `pytest tests/test_document_access.py::test_unauthorized_download_returns_no_bytes` → **passed** (404).
2. Temporarily skipped `require_document_read` on download → same test **failed** (`200 == 404`).
3. Restored secure code → test + `tests/security/` → **passed**.

**How I checked:** `pytest tests/security/` (18 passed after fixes); authz demo as above; full suite run recorded in the completion report. Commit: see git log for Task 16 message.

---

## Task 15 — Administrator dashboard UI (2026-10-21)

**What I asked for:** Role-protected admin dashboard wired to real admin APIs — summary counts, audit log filters/pagination/verify, user activate/deactivate with confirmation, last-active-admin protection, no document content bypass.

**What was built:**
- Backend: `GET /admin/summary`; last-active-admin + self-deactivation policy; `try_append_audit_event_committed` for non-blocking inactive-access audit; tests in `test_admin_users.py`.
- Frontend: `/admin`, `/admin/users`, `/admin/audit` with `RequireAdmin`; nav items for ADMIN only; API client helpers; Vitest coverage for nav, gate, users confirmation, audit verify/filters.

**What needed correction:**
1. Last-admin test failed against seed admins still active in the shared DB — deactivate other admins in-session before asserting.
2. Deactivate-then-`/users/me` could deadlock on the audit advisory lock in the long test transaction — inactive-access audit now uses try-lock and never blocks the 401.

**How I checked:** backend `pytest tests/test_admin_users.py` (+ related); frontend `npm test` / `npm run build` (see completion report).

---

## Task 14 — Durable audit hash chain + admin APIs (2026-10-21)

**What I asked for:** Tamper-evident audit trail with ADMIN-only listing and integrity verification; record login/document/permission/admin actions; concurrency-safe appends; honest THREATS.md limits.

**What was built:**
- `app.services.audit_trail` — SHA-256 canonical hashing, `pg_advisory_xact_lock`, monotonic timestamps, verify/list helpers.
- `DurableAuditHook` replaces null hooks on document routes; DENIED commits independently; SUCCESS fail-closed where required.
- Admin routes: `GET/PATCH /admin/users`, `GET /admin/audit/events`, `GET /admin/audit/integrity`.
- Migration `b2c3d4e5f6a7` drops audit FK constraints so denials can record unknown document/user IDs.
- Docs: API_DOCUMENTATION, PERMISSIONS, THREATS, this entry.

**What needed correction:**
1. Concurrent appends with identical `created_at` broke verification order (UUIDv4 not insertion-ordered) — fixed with monotonic timestamps under the lock.
2. Login SUCCESS + DENIED in one long test transaction deadlocked on the advisory lock — split tests; document the lock lifetime.
3. Restored PERMISSIONS.md after an over-broad rewrite and patched only audit/admin sections.

**How I checked:**
- `alembic upgrade head` — applied `b2c3d4e5f6a7`
- `pytest tests/test_audit_trail.py` — **14 passed**
- `pytest tests/test_auth.py tests/test_audit_trail.py tests/test_document_mutations.py tests/test_document_sharing.py` — **73 passed**

---

## Bugfix — upload vanished + R2 env loading (2026-10-21)

**Symptoms:** Owner upload looked successful then the document disappeared; R2 seemed broken depending on how the API was started.

**Root causes (verified in code):**
1. `get_db()` in `backend/app/db/session.py` flushed inserts but never committed. Closing the session rolled the transaction back after HTTP 201 — no DELETE was involved.
2. `Settings` used cwd-relative `env_file=".env"`. Starting uvicorn outside `backend/` skipped `backend/.env`, so configured R2 variables were not loaded.

**Fixes:** commit on successful requests; load `backend/.env` via an absolute path; commit soft-delete tombstones before certain 503 paths; regression tests for commit/rollback and cwd-independent settings. Live R2 put/get/delete smoke succeeded with existing backend credentials (values not logged).

**Checks:** backend pytest **176 passed**; frontend **43 passed**, lint (font warning only), build OK. 

---

## Short summary for markers

| Counted task | Topic | Example of me directing / correcting the tool |
| --- | --- | --- |
| 1 | Scaffold | Forced Next upgrade + ESLint fix after CVE / broken config |
| 2 | Schema | Blocked unreachable Railway internal host for local migrate |
| 3 | R2 service | No public/presigned URL helpers |
| 4 | Auth | Generic login errors; role from DB not token |
| 5 | Authz layer | Fixed seed test pollution from local demo users |
| 6 | Upload | Added missing `python-multipart`; ignore client owner/key |
| 7 | List/download | Fixed bad storage mocks + filename safety |
| 8 | Sharing | Stopped blanket rollback; regrant = new row |
| 9 | Edit/delete | Soft-delete-first; NullPool after connection exhaustion |
| 10 | Frontend login | Memory-only token; Vitest cleanup; honest logout limits |
| 11 | Document dashboard | Real list API only; Shared With Me without inventing an endpoint; fixed build/lint |
| 12 | Document lifecycle UI | Multipart upload; UUID grant (no user search); confirm delete/revoke |
| 13 | Owner/EDIT content edit | Server `your_access`; READ view-only; PUT content |
| 14 | Durable audit + admin APIs | Hash chain; advisory lock; ADMIN list/verify |
| 15 | Admin dashboard UI | Real summary/users/audit; last-admin lockout guard |
| 16 | Security matrix + THREATS | IDOR demo fails when authz removed; docs honesty |

I still review diffs, run tests myself, and refuse fake “all green” claims when a run actually failed.
