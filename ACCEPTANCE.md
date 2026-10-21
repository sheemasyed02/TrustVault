# TrustVault — Acceptance checklist

Evidence-based mapping of hackathon requirements to workflows, APIs, automated tests, and manual checks. Status values: **PASS**, **FAIL**, **NOT VERIFIED**. Statuses below reflect the acceptance run recorded in Task 20 (see `PROMPTS.md`).

Do not treat this document as a production-readiness certificate. Passing tests prove the checked behaviours under the test harness; residual risks remain in `THREATS.md`.

## How to re-run evidence

```powershell
cd D:\TrustVault\backend
.\.venv\Scripts\Activate.ps1
pytest -q tests/security/test_acceptance_journey.py tests/security/
pytest -q
alembic current

cd D:\TrustVault\frontend
npm test -- --run
npm run build
```

Security regression demo (do **not** commit the vulnerable edit): see README § “Security regression demonstration”.

Demo accounts (dev only): seed via `python -m app.cli.seed_demo_users`. Emails in README; passwords only from local `DEMO_*_PASSWORD` env (never commit).

---

## Requirement matrix

| # | Requirement | Frontend workflow | Backend control | Automated evidence | Manual steps | Status |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Login / logout with hashed passwords + expiring JWT | Login form → memory token; Sign out clears session | `POST /auth/login`, Argon2id, JWT; `GET /users/me` | `tests/test_auth.py`; frontend `auth-provider.test.tsx` | Sign in as demo OWNER; refresh page → must re-login; Sign out | PASS |
| 2 | Role-aware navigation + protected routes | Post-login: ADMIN `/admin`, OWNER `/dashboard`, VIEWER `/shared`; role nav | UI only; API still enforces | `frontend/src/lib/nav.test.ts` | Login each demo role; confirm landing + nav | PASS |
| 3 | Document upload (OWNER) | Upload form → detail | `POST /documents` OWNER-only; R2 + DB | `test_document_upload.py`; `test_acceptance_journey` | OWNER uploads DOCX; appears in My Documents | PASS |
| 4 | List / search / filter without leaking unauthorized metadata | My Documents / Shared / filters | `GET /documents` SQL visibility; `shared_only`; `your_access` | `test_document_access.py` search/filter; `test_acceptance_journey` search leak; `test_document_list_access.py` | Search private title as stranger → empty | PASS |
| 5 | Document details + download via backend stream | Detail + Download | `GET /documents/{id}`, `…/download` after `require_document_read` | `test_document_access.py`; acceptance journey | Open/download owned or shared doc | PASS |
| 6 | Metadata edit (owner or EDIT grant) | Metadata form | `PATCH /documents/{id}` | `test_document_mutations.py`; acceptance journey | EDIT grantee changes title; READ cannot | PASS |
| 7 | Content edit (owner or EDIT) | In-app DOCX preview | `PUT /documents/{id}/content` | `test_document_content_edit.py` | EDIT can save; READ view-only | PASS |
| 8 | Per-document READ/EDIT grant to named user | Sharing panel + user search | `POST …/permissions`; `GET /users/search` | `test_document_sharing.py`; `test_user_search.py`; acceptance journey | Owner grants READ to VIEWER | PASS |
| 9 | List current grants | Sharing panel | `GET …/permissions` owner-only | `test_document_sharing.py` | Owner sees recipients | PASS |
| 10 | Immediate revocation | Confirm revoke → list refresh | `DELETE …/permissions/{user_id}`; next request rechecks DB | Acceptance journey; `test_security_matrix` revoke; sharing tests | Revoke; recipient download denied with same token | PASS |
| 11 | Soft-delete owner-only | Confirm delete | `DELETE /documents/{id}` | `test_document_mutations.py` | Owner deletes; list empty; grantee 404 | PASS |
| 12 | Unauthorized access denied (IDOR) | Error state, no metadata leak | 404 for no relationship | `test_unauthorized_download_returns_no_bytes`; matrix unrelated user | Guess UUID as stranger | PASS |
| 13 | ADMIN cannot read content by role alone | Admin UI has no document browser for all files | Document authz ignores ADMIN role | Acceptance journey; matrix admin; `test_role_permission_separation` | ADMIN open unshared doc id → 404 | PASS |
| 14 | Platform role ≠ document grant | Detail/list access labels | `your_access` vs `users.role` | `test_role_permission_separation.py` | Grant EDIT; `/users/me` still VIEWER | PASS |
| 15 | Disabled accounts blocked | 401 → logout | `get_current_user` checks `is_active` | Acceptance journey; `test_admin_users.py`; matrix deactivate | Deactivate user; next `/users/me` 401 | PASS |
| 16 | Upload validation (type/size/content) | Client hints + server errors | `file_validation`; DOCX-only 10 MiB | `test_document_upload.py` | Try PDF/empty/oversize → rejected | PASS |
| 17 | Private R2; no public/presigned download URLs | Download via API only | Stream after authz; no presign helpers | `test_r2_storage.py`; `test_security_gaps.py` | Confirm response is API stream, not R2 redirect | PASS |
| 18 | Audit events for security-relevant actions | Admin audit log | Durable hash chain + hooks | `test_audit_trail.py`; acceptance hook assertions | Filter audit for LOGIN / DOWNLOAD DENIED | PASS |
| 19 | Audit integrity verification | Admin Verify chain (`valid` field only) | `GET /admin/audit/integrity` | `test_audit_trail.py`; acceptance journey | Click Verify; trust `valid` boolean | PASS |
| 20 | Admin user management | Users activate/deactivate | `GET/PATCH /admin/users` | `test_admin_users.py` | Deactivate/reactivate VIEWER | PASS |
| 21 | Client cannot mass-assign role/owner/storage | Forms reject extras; server ignores | `extra=forbid`; server owner/key | Matrix mass-assignment; upload tests | Send forged `owner_id`/`role` → 422/ignored | PASS |
| 22 | Documentation set | — | Repo docs | Files present: AGENTS, PERMISSIONS, THREATS, API_DOCUMENTATION, PROMPTS, README, ACCEPTANCE | Spot-check API docs vs OpenAPI routes | PASS |
| 23 | Automated unauthorized-access tests | — | pytest security suite | `tests/security/` | — | PASS |
| 24 | Authz-removal regression demo | — | Download requires `require_document_read` | Procedure in README / THREATS; re-run Task 20 | Local only; never commit vulnerable edit | PASS |

---

## Accepted limitations (not FAIL)

| Item | Notes |
| --- | --- |
| Logout does not revoke JWT server-side | Documented; token valid until expiry if stolen and account still active |
| Same-DB audit hash chain | Not DBA-proof / no external anchor (`THREATS.md`) |
| No app-layer login rate limiting | Accepted residual; rely on edge controls |
| Orphan R2 after failed delete cleanup | Soft-delete first; 503 if R2 fails; no sweeper yet |
| Mammoth HTML preview | Semi-trusted rendering; not a full sanitizer product |

---

## Manual five-minute demo (clean local stack)

1. Start Postgres, `alembic upgrade head`, seed demo users, uvicorn, `npm run dev`.
2. OWNER login → Upload DOCX → My Documents → share READ to VIEWER email via search.
3. VIEWER login → Shared with me shows READ → download OK → metadata form absent/disabled.
4. OWNER revoke → VIEWER refresh/detail → access denied.
5. OWNER grant EDIT → VIEWER can PATCH title only → cannot Delete/Share.
6. ADMIN login → Users / Audit / Verify chain → cannot download OWNER’s unshared file by guessing UUID.
7. ADMIN deactivate VIEWER → VIEWER token fails `/users/me`.

---

## Task 20 evidence log

| Check | Command / action | Result |
| --- | --- | --- |
| Acceptance journey | `pytest -q tests/security/test_acceptance_journey.py` | **2 passed** |
| Security suite (+ IDOR after restore) | `pytest …test_unauthorized… tests/security/` | **34 passed** |
| Full backend | `pytest -q` | **251 passed**, 1 warning |
| Frontend | `npm test -- --run` | **59 passed** (16 files) |
| Production build | `npm run build` | **succeeded** (Next.js 16.4.2) |
| Alembic | `alembic current` | `b2c3d4e5f6a7 (head)` |
| Authz-removal demo | Baseline pass → remove check → fail (`200 == 404`) → restore → pass | Vulnerable edit **not** committed |
| `git diff --check` | Whitespace | Cleaned before commit |
| Secrets in git | `.env` gitignored; no secret values in docs | Verified before commit |
