# TrustVault — Threat model (implemented vs residual)

This document describes **actual** mitigations in the current codebase and honest residual risks. Items marked *not implemented* are not claimed as controls.

Tests cited below are real modules under `backend/tests/` (including `tests/security/`).

---

## What we protect

- Private document bytes in Cloudflare R2
- Document metadata and per-document grants in PostgreSQL
- Password hashes and short-lived JWTs
- Durable audit hash-chain events (ADMIN inspection)

---

## Threat catalog

### 1. Insecure direct object reference (IDOR)

| | |
| --- | --- |
| **Impact** | Guess UUID → read/download another user’s document or metadata |
| **Mitigation** | Every document route uses `document_authorization` against DB ownership/grants. Missing / no-access → generic **404** |
| **Tests** | `tests/security/test_security_matrix.py` (unrelated user); `test_document_access.py::test_unauthorized_download_returns_no_bytes`, `test_forged_document_id_does_not_bypass`; `test_document_authorization.py` |
| **Residual** | UUIDs are not secrets; rate limiting of probing is **not** implemented |

### 2. Unauthorized document downloads

| | |
| --- | --- |
| **Impact** | Bytes leave the system without a current grant |
| **Mitigation** | Download streams through FastAPI **after** `require_document_read`. Object key from PostgreSQL only. No public/presigned URLs |
| **Tests** | Matrix + `test_document_access.py` (unauthorized / admin without grant / R2 not called); `test_r2_storage.py` (no public URL helpers) |
| **Residual** | Local copies kept after a legitimate download cannot be revoked |

### 3. Revoked permissions and disabled accounts

| | |
| --- | --- |
| **Impact** | Old JWT or UI state continues to grant access |
| **Mitigation** | Each request reloads grants (`revoked_at IS NULL`) and `users.is_active`. JWT is not a permission cache |
| **Tests** | Matrix revoke READ/EDIT + deactivate; `test_document_sharing.py` / `test_document_access.py` same-token-after-revoke; `test_admin_users.py` deactivate blocks next `/users/me` |
| **Residual** | No server-side token revocation list; stolen JWT works until expiry if account stays active |

### 4. Role escalation and mass assignment

| | |
| --- | --- |
| **Impact** | Client sets `role=ADMIN`, `owner_id`, `storage_key`, `granted_by` |
| **Mitigation** | Actor from validated JWT `sub` + DB user. Schemas use `extra=forbid`. Upload ignores client owner/key |
| **Tests** | Matrix role/owner body rejected; `test_document_upload.py::test_client_owner_id_and_storage_key_ignored`; mutation/sharing mass-assignment tests; `test_admin_users.py::test_role_not_mass_assignable` |
| **Residual** | None claimed beyond schema coverage of each route |

### 5. Public object storage or leaked download URLs

| | |
| --- | --- |
| **Impact** | Anyone with a URL reads confidential files forever |
| **Mitigation** | Private R2 bucket; API streaming only; storage service has no presign/public URL helpers |
| **Tests** | `tests/security/test_security_gaps.py::test_r2_storage_service_has_no_public_or_presigned_url_helpers`; download path tests |
| **Residual** | Misconfigured bucket ACL outside the app is an ops risk |

### 6. Malicious and oversized uploads

| | |
| --- | --- |
| **Impact** | Malware, zip bombs, DoS via huge bodies |
| **Mitigation** | DOCX-only, size cap (10 MiB), ZIP/DOCX structure checks, reject empty/spoofed types. Not a malware scanner |
| **Tests** | `test_document_upload.py` (empty/oversize/bad type/exe/spoof); security gaps filename strip |
| **Residual** | No antivirus; crafted DOCX may still be harmful when opened locally |

### 7. Path traversal and filename handling

| | |
| --- | --- |
| **Impact** | `../` in upload names or Content-Disposition header injection |
| **Mitigation** | Upload uses final path segment only; download filename strips CR/LF/quotes and sanitizes characters; DOCX zip members with `..` rejected |
| **Tests** | `test_security_gaps.py` (normalize_extension, safe_download_filename); matrix path-traversal disposition; `file_validation` DOCX member checks |
| **Residual** | Sanitized names may still contain previously injected tokens as underscores (no header break) |

### 8. SQL injection / unsafe queries

| | |
| --- | --- |
| **Impact** | Attacker runs arbitrary SQL via filters |
| **Mitigation** | SQLAlchemy parameterized queries; no raw string-concatenated user SQL for document filters |
| **Tests** | Filter/pagination validation tests; ORM usage throughout |
| **Residual** | Future raw SQL must stay parameterized |

### 9. Cross-site scripting (XSS)

| | |
| --- | --- |
| **Impact** | Stored script in title/description executes in another user’s browser |
| **Mitigation** | React text rendering (default escaping). Content-Disposition sanitization for downloads. In-browser DOCX preview uses mammoth HTML — treat as limited trust |
| **Tests** | Filename header sanitization tests; no dedicated XSS browser suite |
| **Residual** | Mammoth HTML preview is **not** a full HTML sanitizer product; admins/owners should treat preview as semi-trusted |

### 10. CORS mistakes

| | |
| --- | --- |
| **Impact** | Malicious origin reads API responses with victim cookies/tokens |
| **Mitigation** | Explicit `CORS_ORIGINS` list (default localhost only). Credentials allowed only for listed origins. Not `*` |
| **Tests** | `test_security_gaps.py::test_cors_does_not_allow_wildcard_by_default` |
| **Residual** | Mis-set production `CORS_ORIGINS` could widen access |

### 11. Brute-force login / rate limiting

| | |
| --- | --- |
| **Impact** | Password guessing |
| **Mitigation** | Generic login errors; Argon2id cost. **No** application-level rate limit or lockout |
| **Tests** | Auth generic failure tests; login audit without password echo |
| **Residual** | **Accepted gap** — rely on reverse-proxy / WAF rate limits in production |

### 12. Token theft and session security

| | |
| --- | --- |
| **Impact** | XSS or malware steals bearer token |
| **Mitigation** | Frontend keeps access token in **memory only** (not localStorage/sessionStorage). Short TTL. HTTPS expected in production |
| **Tests** | Frontend `auth-provider` Vitest |
| **Residual** | No refresh-token rotation; no logout revocation store |

### 13. Audit tampering and database compromise

| | |
| --- | --- |
| **Impact** | Attacker hides tracks by editing `audit_events` |
| **Mitigation** | SHA-256 hash chain + `pg_advisory_xact_lock`; ADMIN integrity verify. No app API to edit/delete history |
| **Tests** | `test_audit_trail.py`; matrix non-admin audit 403 |
| **Residual** | Same-DB chain is **not** tamper-proof against a DBA who rewrites the whole table or truncates the tail without an external anchor |

### 14. Audit-write failures

| | |
| --- | --- |
| **Impact** | Sensitive action succeeds without a record; or denial is lost on rollback |
| **Mitigation** | SUCCESS for sensitive ops fail-closed when audit cannot write (same txn). DENIED uses separate commit (or try-lock for inactive access so 401 never blocks) |
| **Tests** | Audit trail denial survival; mutation fail-closed hooks; inactive try-lock behavior |
| **Residual** | Best-effort inactive-access audit may skip if lock busy |

### 15. Concurrent audit writes

| | |
| --- | --- |
| **Impact** | Broken previous_hash links under parallel writers |
| **Mitigation** | Advisory transaction lock + monotonic timestamps |
| **Tests** | `test_audit_trail.py::test_concurrent_appends_keep_valid_chain` |
| **Residual** | Lock contention under extreme load |

### 16. Partial failure between storage and database

| | |
| --- | --- |
| **Impact** | Orphan R2 objects or DB rows pointing at missing objects |
| **Mitigation** | Upload: cleanup R2 if DB fails after put. Delete: soft-delete first, then R2; R2 failure → 503 with tombstone kept |
| **Tests** | `test_document_upload.py` cleanup; `test_document_mutations.py` R2 delete failure |
| **Residual** | Orphan private objects until manual/ops cleanup (**no** automated sweeper yet) |

### 17. Administrator abuse

| | |
| --- | --- |
| **Impact** | ADMIN role used to read all files |
| **Mitigation** | ADMIN gets user/audit APIs only. Document content still requires ownership or grant. Last-active-admin cannot be deactivated |
| **Tests** | Matrix admin audit without content; `test_admin_users.py`; `test_document_view_counts.py` |
| **Residual** | Malicious ADMIN can still deactivate users / inspect audit metadata |

### 17b. Document view-count interpretation

| | |
| --- | --- |
| **Impact** | Inflated or misleading “who read this” claims |
| **Mitigation** | Only `GET /documents/{id}/download?disposition=inline` after server-side `require_document_read` records `DOCUMENT_VIEW` SUCCESS. Metadata/list GETs and attachment downloads do not count as views. Same actor+document within 45s is deduped. UI states counts are authorised preview requests, not proof of reading |
| **Tests** | `test_document_view_counts.py`; owner/admin dashboards |
| **Residual** | Dedupe can under-count rapid legitimate re-opens; hash-chain audit rows remain editable by a privileged DBA (see §13) |

### 18. Secret exposure (Git, logs, frontend)

| | |
| --- | --- |
| **Impact** | JWT secret or R2 keys leak |
| **Mitigation** | `.env` gitignored; example placeholders; no `NEXT_PUBLIC_` secrets for signing/R2; audit/logging policy excludes passwords/tokens/bytes |
| **Tests** | Login failure does not echo password; audit sanitize metadata |
| **Residual** | Developers may still paste secrets into tickets; dependency on correct deploy config |

### 19. Dependency vulnerabilities, backups, retention, DoS

| | |
| --- | --- |
| **Impact** | Supply-chain CVE; lost backups; resource exhaustion |
| **Mitigation** | Pinned requirements/lockfiles in repo practice; upload size limits |
| **Tests** | Size-limit upload tests only |
| **Residual** | **Not implemented** as product features: automated CVE scanning gate, backup/retention policy UI, application-layer DoS protection beyond size limits |

---

## Authorization-check regression demonstration (performed)

Evaluators may remove an authorization check. We verified detection as follows (local only; vulnerable code **not** committed):

1. Baseline: `pytest tests/test_document_access.py::test_unauthorized_download_returns_no_bytes` → **passed** (404).
2. Temporarily removed `require_document_read` from `GET /documents/{id}/download` (direct `session.get(Document)`).
3. Re-ran the same test → **failed** (`assert 200 == 404`) — unauthorized caller received bytes.
4. Restored `require_document_read` immediately.
5. Re-ran the same test + `tests/security/` → **passed**.

Re-executed in **Task 20** with the same outcome (baseline pass → vulnerable fail `200 == 404` → restore → **34 passed** for IDOR + `tests/security/`). Vulnerable edit was never committed.

Command used:

```powershell
cd D:\TrustVault\backend
.\.venv\Scripts\python.exe -m pytest tests/test_document_access.py::test_unauthorized_download_returns_no_bytes -q
```

---

## Quick map

| Threat | Primary tests |
| --- | --- |
| IDOR / unauthorized download | `tests/security/`, `test_document_access.py` |
| Revoke / deactivate | matrix + sharing/access/admin tests |
| Mass assignment | upload/mutations/sharing/admin |
| Private R2 | `test_r2_storage.py`, security gaps |
| Upload abuse | `test_document_upload.py` |
| Audit chain | `test_audit_trail.py` |
| Admin without content | matrix + `test_admin_users.py` |
