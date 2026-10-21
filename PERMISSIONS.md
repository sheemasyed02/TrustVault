# TrustVault — Permissions Model

Status: **Authorization service implemented**. Document **upload**, **list/search**, **metadata**, **download**, **grant/revoke**, **metadata PATCH**, and **owner soft-delete** are implemented.

## Authentication vs authorization

- **Authentication** (`get_current_user`): proves who the caller is (valid bearer token + active user in PostgreSQL).
- **Authorization** (`app.services.document_authorization`): decides whether that user may perform a specific action on a specific document, using current database ownership and grants.

Token role claims and client-supplied owner/permission fields are never treated as authorization.

## Permission matrix

| Principal | List / discover | Read metadata / download | Edit metadata | Edit DOCX content (`PUT …/content`) | Grant / revoke | Soft-delete | Admin APIs |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Document owner | Yes | Yes | Yes | Yes | Yes | Yes | No (unless role ADMIN) |
| Active READ grant | Yes (that doc) | Yes | No | No | No | No | No |
| Active EDIT grant | Yes (that doc) | Yes | Yes (title/category/description) | Yes | No | No | No |
| No active grant | No | No | No | No | No | No | No |
| ADMIN without grant | No | No | No | No | No | No | Yes (users/audit only) |
| Inactive account | No protected actions | | | | | | |

Denial policy: inaccessible documents → **404**; insufficient action with a visible relationship → **403**; unauthenticated/inactive → **401**.

Security regression matrix: `backend/tests/security/`.

### Owner vs EDIT grantee (metadata)

- **Owner:** may PATCH `title`, `category`, `description`; may grant/revoke; may DELETE (soft-delete).
- **EDIT grantee:** may PATCH the same three fields only. Cannot change `owner_id`, `storage_key`, size/checksum/MIME, deletion state, or permissions. Cannot DELETE or share.

### Metadata PATCH

- Route: `PATCH /documents/{document_id}`
- Service: `update_document_metadata` → `evaluate_document_access(EDIT_METADATA)` after `SELECT … FOR UPDATE`
- Forbidden fields rejected via schema `extra=forbid` and `reject_protected_metadata_fields`
- Revoked EDIT grant denied on the next PATCH (same JWT still valid)

### Soft-delete

- Route: `DELETE /documents/{document_id}` — owner only (`require_document_delete`)
- Sets `documents.deleted_at`; retains permission rows and audit history
- Then deletes the private R2 object (server key only)
- Soft-deleted documents are excluded from list and fail read/download/edit/share with **404**
- Repeated DELETE → **404** (does not claim success)

### Storage / DB consistency (delete)

1. Authorize owner  
2. Soft-delete in PostgreSQL (document immediately unservable)  
3. Delete R2 object  
4. Success only if R2 delete succeeds or object already absent  
5. If R2 fails: keep soft-delete, return **503**, audit `STORAGE_DELETE_FAILED`  

Residual: orphaned private R2 object until retry. No distributed transaction with R2.

### Immediate revocation

Every protected check reloads grant state from PostgreSQL. JWTs are not permission caches. No public/presigned download URLs.

### Listing and search visibility

`accessible_documents_query`: non-deleted AND (owner OR active READ/EDIT grant). ADMIN alone does not expand visibility.

### Denial response policy

- Missing / soft-deleted / no-access → **404** `"Document not found"`
- Insufficient action (e.g. READ editing, EDIT deleting) → **403** `"Forbidden"`
- Unauthenticated / inactive → **401**
- Authz/query failure → **503**

### Concurrency (edit vs revoke)

Document (and non-owner grant) rows are locked with `FOR UPDATE`, then edit authorization is re-checked. A revoke committed before that check denies the edit. Under READ COMMITTED, a residual race between the final check and commit is **not** claimed as fully eliminated; tests cover revoke-then-edit on the same token.

## User search for sharing

- Route: `GET /users/search?q=…`
- Service: `app.services.user_search.search_users`
- Any **authenticated active** user may search. Results are limited to other **active** users matched by name/email.
- Search returns `id` / `name` / `email` only. It does **not** grant document access.
- Sharing still requires document ownership via `POST/DELETE /documents/{id}/permissions`.
- Empty / tiny queries are rejected to reduce unlimited directory enumeration.

## Code entry points

- `app.services.document_authorization.*`
- `app.services.document_metadata.update_document_metadata`
- `app.services.document_deletion.soft_delete_document`
- `app.services.document_sharing.*`
- `app.services.user_search.search_users`
- `app.api.documents` (upload/list/get/patch/delete/download)
- `app.api.document_permissions` (list/grant/revoke)
- `app.api.users` (`/me`, `/search`)
- `app.api.admin` (user status + audit list/integrity)
- `app.services.audit_trail` / `DurableAuditHook`

## Admin (not document content)

| Capability | Who | Notes |
| --- | --- | --- |
| `GET /admin/summary` | ADMIN | Accurate user + audit outcome counts |
| List users / set `is_active` | ADMIN | Audited; no role mass-assignment |
| List audit events / verify chain | ADMIN | Metadata only; no file bytes |
| Read/download arbitrary documents | Nobody by role alone | Still requires ownership or grant |

Account-status policy: cannot deactivate the last active administrator; cannot deactivate your own account when other admins remain; inactive users are rejected on the next protected request even with a valid JWT.

## Audit

Durable SHA-256 hash chain in `audit_events` (`app.services.audit_trail`):

- Append under `pg_advisory_xact_lock` with monotonic `created_at` (concurrency-safe tip linking).
- SUCCESS for sensitive mutations shares the request transaction (**fail-closed** if audit cannot be written for grant/revoke/metadata/content/delete/login success/admin status).
- DENIED uses a **separate committed session** so rolling back the protected-operation transaction does not erase the denial. If that independent write fails, the denial HTTP response is still returned and the event is **not** claimed persisted.
- No ordinary API can PATCH/DELETE historical audit rows.
- Admin audit listing never grants document content permission.

## Tests

- `tests/test_document_authorization.py`
- `tests/test_document_access.py`
- `tests/test_document_sharing.py`
- `tests/test_document_mutations.py` — PATCH/DELETE, R2 failure honesty, revoke-then-edit
- `tests/test_user_search.py` — auth, matching, inactive/self exclusion, pagination, sensitive fields
- `tests/test_audit_trail.py` — hash/link/tamper/empty/concurrent/admin filters/non-admin denial

## Remaining gaps

- Automated orphan R2 cleanup worker after failed storage delete
- Token logout/revocation
- External chain-head anchoring (silent tail truncation / full DBA rewrite)
