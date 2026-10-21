# TrustVault — How I used AI (PROMPTS.md)

This is my working log. I used Cursor to help write code, but I gave the rules, checked the output, and fixed things when the tool was wrong.

**Counting note:** Early setup (reading `AGENTS.md` / `.gitignore` only) is **not** part of the counted tasks. Counted tasks below run scaffold → frontend login → document dashboard. (Course labels sometimes say “Task 13” for the dashboard; here it is counted task 11.)

I did **not** invent bugs, fake test results, or fake “AI mistakes.” Only real things that happened.

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

No commit yet for this task (not requested).

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

I still review diffs, run tests myself, and refuse fake “all green” claims when a run actually failed.
