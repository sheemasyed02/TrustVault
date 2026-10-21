# TrustVault — Threats I thought about while building

This is written in plain English. It is about **real risks** we hit or designed for while building the app so far (through the 10 counted tasks: scaffold → frontend login). It is **not** a fake list of threats we never handled.

I also say which tests cover the threat. If something is still weak, I say that honestly.

---

## What we are protecting

- Private document files in Cloudflare R2
- Metadata and who can access what (Postgres)
- Passwords and login tokens
- Later: audit history (table exists; durable “hash chain writer” is **not** finished yet)

---

## Threats we cared about (and what we did)

### 1. Someone guesses a document ID and reads or downloads it

**Worry:** UUID in the URL is not a secret.

**What we did:** Every metadata/download check goes through the server authorization code. No grant / not owner → generic **404**, not “you are forbidden but it exists.”

**Tests:** Unauthorized download returns no file bytes; R2 is **not** called. Forged IDs fail. Covered in document access / authorization tests.

---

### 2. The browser sends a fake role or owner id

**Worry:** Client says `role=ADMIN` or `owner_id=me` and the API believes it.

**What we did:** Identity comes from the JWT `sub` + user row in Postgres. Ownership and grants come from the database. PATCH/share bodies reject extra fields like `owner_id`, `storage_key`, `granted_by`.

**Tests:** Mass-assignment tests; sharing ignores client `granted_by`; authz tests ignore client-supplied owner/role fields.

---

### 3. Access after someone was revoked

**Worry:** Old JWT or cached “you may download” keeps working after revoke.

**What we did:** Each protected request reloads grants (`revoked_at IS NULL`). No public or long-lived download links. Frontend menus are **not** the security control.

**Tests:** Same token works before revoke, fails after, for download/metadata/edit. Sharing tests cover this on purpose.

---

### 4. Files become public on the internet

**Worry:** Presigned or public R2 URLs leak after share is removed.

**What we did:** Private bucket only. Downloads stream through FastAPI after authz. Storage helpers do not create public/presigned download URLs.

**Tests:** R2 unit tests assert those helpers are not present; download tests use mocked private get.

---

### 5. Weak passwords / tokens leaking

**Worry:** Plaintext passwords, tokens in logs, secrets in the frontend bundle.

**What we did:** Argon2id hashes. Short-lived JWT. Frontend keeps the token in **memory** only (refresh = sign in again). Env examples are placeholders. Do not log passwords/tokens/file bytes.

**Still open:** Server-side logout does **not** revoke JWTs yet. Token is valid until it expires if someone copied it.

**Tests:** Auth tests for hash storage and failed-login logging safety; frontend tests that token is not written to localStorage/sessionStorage.

---

### 6. Disabled user still acts

**Worry:** Account turned off but old token still works.

**What we did:** `get_current_user` and authz reject inactive users.

**Tests:** Inactive user denied on `/users/me` and document routes.

---

### 7. Search/list leaks other people’s titles

**Worry:** Search for a secret title returns a hit even when you cannot open the file.

**What we did:** List query only includes owned docs or active grants, **then** applies filters. Unauthorized search returns empty, not a teaser.

**Tests:** Search-for-inaccessible-title returns zero rows.

---

### 8. ADMIN sees every confidential file by role alone

**Worry:** Admin role = automatic document access.

**What we did:** ADMIN without a grant cannot list/read/download like an owner. Admin product features (user admin / audit UI) are separate and mostly not built yet.

**Tests:** ADMIN without grant cannot download; empty list for unrelated docs.

---

### 9. Bad or huge uploads

**Worry:** Wrong file types, huge files, spoofed extensions.

**What we did:** Size limit, allowed types, basic content checks. If DB save fails after R2 put, try to delete the R2 object.

**Still open:** This is not a full malware scanner.

**Tests:** Upload suite for empty/oversize/bad type/spoof; R2 cleanup on DB failure.

---

### 10. Delete says “success” but file still downloadable — or opposite mess

**Worry:** Postgres and R2 are two systems. One can succeed and the other fail.

**What we did:** Soft-delete in Postgres **first** (file stops being listed/read/downloaded), then delete from R2. If R2 fails → keep soft-delete, return **503**, do not claim full success. Orphan private object may remain until cleanup later.

**Tests:** R2 failure after delete keeps document unreadable; repeated delete returns 404; success path calls storage delete.

---

### 11. EDIT user deletes or re-shares

**Worry:** Someone with EDIT acts like the owner.

**What we did:** EDIT can change title/category/description only. Grant/revoke/delete are owner-only.

**Tests:** EDIT cannot grant, revoke, or delete; READ cannot edit.

---

### 12. Frontend “security”

**Worry:** Hiding a nav link feels like protection.

**What we did:** Role-aware menus for UX only. Real checks stay on the API. Docs and UI text say this clearly.

**Tests:** Frontend role nav tests; backend still denies wrong roles even if UI were changed.

---

### 13. Audit trail is not solid yet

**Worry:** We log allow/deny in hooks, but events are **not** durably written with a hash chain yet.

**What we did:** Hooks exist; tests record `persisted=false`. No normal API to edit/delete audit rows. Full integrity verification is **future work**.

**Honest limit:** Do not claim tamper-proof audit today.

---

## Limits I still accept

- Someone who already downloaded a file can keep their **local copy**. We only control later server access.
- A DBA with full Postgres access can change data; a same-DB hash chain would not stop that alone.
- Soft-delete + R2 delete can leave a private orphan object if cleanup fails.
- JWT logout/revocation store is not built yet.

---

## Quick map: threat → tests (real ones)

| Threat | Main tests |
| --- | --- |
| IDOR read/download | `test_document_access.py`, `test_document_authorization.py` |
| Fake owner/role fields | authz + mutation + sharing tests |
| Revoke must stick | sharing + access “same token after revoke” tests |
| No public R2 URLs | `test_r2_storage.py` |
| Inactive users | auth + access tests |
| List/search leak | access list/search tests |
| ADMIN without grant | access + sharing tests |
| Upload abuse / cleanup | `test_document_upload.py` |
| Delete / R2 partial failure | `test_document_mutations.py` |
| Token not in browser storage | frontend `auth-provider` Vitest |

If a threat above says “still open,” we did **not** pretend the tests fully close it.
