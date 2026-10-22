# TrustVault — Permissions Model

Status: **Authorization service implemented**. Document **upload**, **list/search**, **metadata**, **download**, **grant/revoke**, **metadata PATCH**, and **owner soft-delete** are implemented.

## Platform role vs document grant (do not conflate)

TrustVault uses **two independent concepts**:

| Concept | Stored in | Values | Purpose |
| --- | --- | --- | --- |
| **Platform role** | `users.role` | `ADMIN`, `OWNER`, `VIEWER` | Who may upload (`OWNER`), who may use admin APIs (`ADMIN`), default UI navigation |
| **Document ownership** | `documents.owner_id` | User UUID | Full control of that document (share/revoke/delete) |
| **Document grant** | `document_permissions.permission` | `READ`, `EDIT` | Explicit share to a named user; never changes `users.role` |

Rules:

- Granting `READ` or `EDIT` does **not** promote the recipient to platform `OWNER` or `ADMIN`.
- Platform `ADMIN` does **not** receive document content access by default.
- API field `your_access` (`OWNER` \| `EDIT` \| `READ`) is **document-level** only. `your_access=OWNER` means `documents.owner_id == caller`, not `users.role == OWNER`.
- Every protected document request reloads ownership and `revoked_at IS NULL` grants from PostgreSQL. JWTs are not a permission cache.

## Authentication vs authorization

- **Authentication** (`get_current_user`): proves who the caller is (valid bearer token + active user in PostgreSQL).
- **Authorization** (`app.services.document_authorization`): decides whether that user may perform a specific action on a specific document, using current database ownership and grants.

Token role claims and client-supplied owner/permission fields are never treated as authorization.

## Permission matrix

| Principal | List / discover | Read metadata / download | Edit metadata | Edit content (`PUT …/content`) | Grant / revoke | Soft-delete | Admin APIs |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Document owner (`owner_id`) | Yes | Yes | Yes | Yes | Yes | Yes | No (unless platform role ADMIN) |
| Active READ grant | Yes (that doc) | Yes | No | No | No | No | No |
| Active EDIT grant | Yes (that doc) | Yes | No (owner only) | Yes | No | No | No |
| No active grant | No | No | No | No | No | No | No |
| Platform ADMIN without grant | No | No | No | No | No | No | Yes (users/audit/promotions only) |
| Inactive account | No protected actions | | | | | | |

Denial policy: inaccessible documents → **404**; insufficient action with a visible relationship → **403**; unauthenticated/inactive → **401**.

Security regression matrix: `backend/tests/security/`.

### Owner vs EDIT grantee (metadata vs content)

- **Owner:** may PATCH `title`, `category`, `description`; may grant/revoke; may DELETE (soft-delete); may edit content.
- **EDIT grantee:** may edit document **contents** only (`PUT …/content` for DOCX). Cannot change title/category/description, `owner_id`, `storage_key`, size/checksum/MIME, deletion state, or permissions. Cannot DELETE or share.

### Metadata PATCH

- Route: `PATCH /documents/{document_id}`
- Service: `update_document_metadata` → `evaluate_document_access(EDIT_METADATA)` after `SELECT … FOR UPDATE`
- **Owner only** — active EDIT grants do not permit title/category/description changes
- Forbidden fields rejected via schema `extra=forbid` and `reject_protected_metadata_fields`
- Non-owners with a grant receive **403**; no relationship → **404**

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

`GET /documents` includes `your_access` per row. `shared_only=true` returns only granted (non-owned) documents for Shared With Me.

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
- Passwords, tokens, file bytes, and storage keys are stripped from metadata at write time.

### Event types (selected)

| Action | When |
| --- | --- |
| `DOCUMENT_UPLOAD` | Upload accepted or rejected |
| `DOCUMENT_VIEW` | Authorised inline preview request (not proof of reading) |
| `DOCUMENT_DOWNLOAD` | Authorised attachment download |
| `DOCUMENT_CONTENT_UPDATE` / `DOCUMENT_METADATA_UPDATE` | Content or owner metadata change |
| `DOCUMENT_DELETE` | Soft-delete |
| `DOCUMENT_PERMISSION_GRANT` / `REVOKE` | Owner grant/revoke; metadata includes `permission` and `target_user_id` |
| `OWNER_PROMOTION_REQUEST` / `REVIEW` | Viewer requests and admin decisions |
| `LOGIN` / `REGISTER` | Auth success and relevant failures |
| `ADMIN_USER_STATUS_UPDATE` / `ROLE_UPDATE` | Admin account changes |

### Dashboards

- **Owner** `GET /documents/{id}/audit` — owner-only; summary counts + timeline with actor/target identities; guessing another owner's document ID is denied.
- **Admin** `GET /admin/audit/events` — platform-wide filters: actor, document, **owner**, action, outcome, date range. Metadata only; never file bytes.

### Integrity limits

The same-database hash chain detects many in-place row edits when an attacker cannot rewrite the whole table consistently. A privileged DBA who can UPDATE/DELETE/INSERT freely (or truncate the chain tail without an external head anchor) can still forge a valid-looking chain. External anchoring / WORM storage is not implemented.

## Tests

- `tests/test_document_authorization.py`
- `tests/test_document_access.py`
- `tests/test_document_sharing.py`
- `tests/test_document_mutations.py` — PATCH/DELETE, R2 failure honesty, revoke-then-edit
- `tests/test_user_search.py` — auth, matching, inactive/self exclusion, pagination, sensitive fields
- `tests/test_audit_trail.py` — hash/link/tamper/empty/concurrent/admin filters/non-admin denial
- `tests/test_document_audit_dashboard.py` — view/download counts, owner IDOR, admin owner filter, grant identity
- `tests/security/test_security_matrix.py` — owner / READ / EDIT / unrelated / ADMIN matrix
- `tests/security/test_role_permission_separation.py` — platform role ≠ document grant; Part 5 regressions

## Document formats (upload / preview / edit / download)

| Format | Upload | Preview | In-app content edit | Download |
| --- | --- | --- | --- | --- |
| **DOCX** | **Yes only** (extension + MIME + OOXML ZIP structure) | Yes (mammoth HTML) | **Yes (limited)** — body text rewritten; other package parts preserved when possible; body tables/images simplified | Genuine conversion to PDF (LibreOffice when installed; otherwise ReportLab text/table fallback) |
| **PDF** | **Rejected** (415) | Legacy rows only | **No** (415) | Legacy rows streamed as PDF; new docs always convert from DOCX |

Downloads never rename `.docx` to `.pdf`. Conversion uses private temp directories that are deleted after use. Preview and download always re-check current grants. Previously downloaded PDF copies cannot be remotely revoked.

## Remaining gaps

- Automated orphan R2 cleanup worker after failed storage delete
- Token logout/revocation
- External chain-head anchoring (silent tail truncation / full DBA rewrite)
- Full-fidelity DOCX→PDF without LibreOffice (fallback omits images and complex layout)
- Full-fidelity in-browser Word editing (body tables/images/drawings are simplified on save)
