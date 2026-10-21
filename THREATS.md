# TrustVault — Threat Model

This document separates **planned** mitigations from mitigations that are **implemented and tested**. Update it when security behaviour changes.

## Assets

- Confidential document bytes stored in private Cloudflare R2
- Document metadata and permission grants in PostgreSQL
- User credentials and access tokens
- Audit event history (durable hash chain planned; not yet written by app APIs)

## Actors

- Authenticated ADMIN, OWNER, and VIEWER users
- Disabled or revoked users
- Unauthenticated outsiders
- Insiders with database or hosting console access

## Threats and mitigations

| ID | Threat | Planned mitigation | Implemented and tested |
| --- | --- | --- | --- |
| T1 | Unauthorized document read/download (IDOR) | Server-side permission check on every protected request; stream downloads only after authz | Yes: `require_document_read` on metadata/download; list SQL visibility; access tests |
| T2 | Privilege escalation via client-supplied role/owner claims | Ignore client role/owner/permission fields; derive identity from signed token and DB | Yes: authz + PATCH `extra=forbid` / protected fields; sharing ignores client `granted_by` |
| T3 | Access after permission revocation | Re-check current grants on each request; no long-lived public/presigned download URLs | Yes: same-token revoke-then-download/edit tests |
| T4 | Public exposure of R2 objects | Private bucket; opaque server-generated keys; backend-mediated download | Yes: no public/presigned URL helpers; download streams via API |
| T5 | Credential theft / weak auth | Hashed passwords; signed, expiring tokens; no secrets in logs or browser bundles | Partial: Argon2id + JWT; logout/token revocation not implemented |
| T6 | Disabled account still acting | Reject protected actions when account is inactive | Yes: `get_current_user` + authz inactive checks |
| T7 | Metadata leakage in search/list | Return only authorized documents; generic denial responses | Yes: SQL access filter; 404 enumeration-resistant denials |
| T8 | Audit log tampering via app APIs | Append-only application writes; no edit/delete audit endpoints for normal APIs | Partial: no audit mutation routes exist; durable writer not implemented |
| T9 | Undetected audit history alteration | Hash chain with verification endpoint and tests | No: durable audit writer not implemented |
| T10 | Secret leakage via Git or frontend | `.env` ignored; placeholders only; no secrets in client code | Partial: ignore rules / examples; no secret-scanning suite |
| T11 | Upload abuse | Size, type, and content validation; handle storage/DB partial failures | Yes: validation + R2/DB compensation on upload |
| T12 | CORS misuse | Allowed origins loaded from configuration | Partial: middleware configured; not hostile-origin tested |
| T13 | Partial delete leaves accessible content or false success | Soft-delete before R2 delete; deny serve when `deleted_at` set; do not return 200 if R2 cleanup fails | Yes: soft-delete-first; 503 on R2 failure while catalog stays unservable; orphan R2 residual documented |
| T14 | Mass assignment of ownership/storage via metadata edit | Explicit PATCH schema; reject protected fields | Yes: mutation tests for owner_id/storage_key/size/checksum/MIME |
| T15 | EDIT grantee deletes or re-shares | Owner-only delete and permission routes | Yes: EDIT gets 403 on delete/grant |

## Delete consistency (T13) — actual strategy

PostgreSQL and R2 are not one atomic transaction.

1. Owner authorization (`require_document_delete`)
2. Set `deleted_at` (document immediately unlistable / unreadable / undownloadable)
3. Delete R2 object by server-side key
4. Return success only if R2 delete succeeds or the object is already absent
5. On R2 failure: keep soft-delete, return **503**, audit `STORAGE_DELETE_FAILED`

**Residual risk:** a private R2 object may remain after a failed cleanup until an operator or future retry job deletes it. The application will not serve that document while soft-deleted.

## Honest limits

- A hash chain stored in the same PostgreSQL database is **not** proof against a privileged DBA who can rewrite events and hashes.
- Soft-delete + R2 delete is best-effort across two systems; orphaned private objects are possible after cleanup failure.
- `FOR UPDATE` on edit reduces the revoke-vs-edit race but does not eliminate all READ COMMITTED races between final authz check and commit.
- Already-downloaded local copies cannot be remotely wiped.

## Current API exposure (backend)

Implemented authenticated document APIs include upload, list/search, metadata get/patch, download, permission list/grant/revoke, and owner soft-delete. Admin audit integrity APIs and durable audit writes are not implemented.
