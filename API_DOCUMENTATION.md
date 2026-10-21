# TrustVault — API Documentation

Base URL (local): `http://127.0.0.1:8000`

## Implemented

### `GET /health`

Returns service liveness for local development and deployment checks.

**Response `200`**

```json
{
  "status": "ok",
  "service": "TrustVault"
}
```

### `POST /auth/login`

Exchange email and password for a signed JWT access token.

**Request**

```json
{
  "email": "user@example.com",
  "password": "your-password"
}
```

Emails are normalized (trim + lowercase) before lookup. Passwords are verified against Argon2id hashes stored in PostgreSQL.

**Response `200`**

```json
{
  "access_token": "<jwt>",
  "token_type": "bearer",
  "expires_at": "2026-10-21T12:00:00+00:00",
  "expires_in": 1800
}
```

**Response `401`** (generic — does not reveal whether the email exists, the password is wrong, or the account is inactive):

```json
{
  "detail": "Invalid email or password"
}
```

Password hashes are never returned.

#### Token validation behavior

- Algorithm is configured server-side (`HS256` only). The API does not accept an algorithm chosen from an unverified token.
- Validated claims: signature, `exp`, `iat`, `iss`, `aud`, `typ=access`, and `sub` (user UUID).
- The token does **not** authorize roles. The current role and active status are always loaded from PostgreSQL.
- **Logout / revocation:** this API does not implement token revocation. A pure JWT access token remains valid until it expires unless a revocation store is added later. Do not claim that logout invalidates issued tokens until that exists.

### `GET /users/me`

Requires `Authorization: Bearer <access_token>`.

Loads the current user from PostgreSQL using the token `sub`. Rejects missing, invalid, expired, wrong-issuer/audience tokens, and inactive or missing users with `401`.

**Response `200`**

```json
{
  "id": "00000000-0000-0000-0000-000000000000",
  "name": "Demo Viewer",
  "email": "user@trustvault.demo",
  "role": "VIEWER",
  "is_active": true,
  "created_at": "2026-10-21T12:00:00+00:00",
  "updated_at": "2026-10-21T12:00:00+00:00"
}
```

Never includes `password_hash`.

### `GET /users/search`

Requires `Authorization: Bearer <access_token>`.

Authenticated directory lookup for share recipients. Searches **active** registered users by `name` or `email` (case-insensitive substring). Excludes the caller. Does not return inactive accounts.

**Query parameters**

| Param | Required | Notes |
| --- | --- | --- |
| `q` | Yes | Trimmed; minimum **2** characters; maximum 128. Matches name/email substring, or an **exact user UUID** when `q` is a UUID |
| `page` | No | Default `1` |
| `page_size` | No | Default `10`; maximum `20` |
| `exclude_user_id` | No | Comma-separated user UUIDs to omit (e.g. document owner) |

Empty or single-character `q` values are rejected (`422`) so callers cannot dump the full directory. The caller is always excluded.

**Response `200`**

```json
{
  "results": [
    {
      "id": "33333333-3333-3333-3333-333333333333",
      "name": "Bob Viewer",
      "email": "bob@example.com"
    }
  ],
  "page": 1,
  "page_size": 10,
  "total": 1,
  "total_pages": 1
}
```

Each hit includes only `id`, `name`, and `email`. Never includes `password_hash`, tokens, roles, or full account records. LIKE metacharacters in `q` are escaped so `%` / `_` are matched literally.

**Errors:** `401` unauthenticated / inactive caller; `422` invalid `q` / pagination.

Granting access still uses `POST /documents/{document_id}/permissions` with the selected `user_id`. Search alone does not grant permissions.

### `POST /documents`

Authenticated **OWNER** only. Uploads a file to private Cloudflare R2 and stores metadata in PostgreSQL.

**Content type:** `multipart/form-data`

| Field | Required | Notes |
| --- | --- | --- |
| `file` | Yes | **DOCX only** (Word document); max **10 MiB** |
| `title` | Yes | Trimmed; max 255 characters |
| `category` | Yes | Trimmed; max 128 characters |
| `description` | No | Trimmed; max 5000 characters |

Not accepted as authoritative (ignored if sent): `owner_id`, `storage_key`, checksum, size, audit fields. Owner and opaque R2 key are always server-assigned.

**Validation**

- Empty files rejected (`400`).
- Oversized files rejected (`413`).
- Unsupported or mismatched type/extension/content rejected (`415`).
- Only `.docx` is accepted. Extension and client MIME type are not trusted alone; DOCX ZIP structure (`[Content_Types].xml`, `word/document.xml`) is checked. PDF, PNG, and JPEG uploads are rejected (`415`).
- This is **not** malware scanning.

**Response `201`**

```json
{
  "id": "00000000-0000-0000-0000-000000000000",
  "title": "Q3 Report",
  "category": "Finance",
  "description": "Optional notes",
  "owner": {
    "id": "00000000-0000-0000-0000-000000000001",
    "name": "Sheema Owner",
    "email": "sheema@trustvault.demo"
  },
  "mime_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  "file_size": 12345,
  "sha256_checksum": "<hex>",
  "created_at": "2026-10-21T12:00:00+00:00"
}
```

Never returns `storage_key`, credentials, public URLs, or file bytes.

**Typical errors**

| Status | Meaning |
| --- | --- |
| 401 | Missing/invalid token or inactive user |
| 403 | Authenticated but not OWNER (VIEWER/ADMIN) |
| 413 | File larger than 10 MiB |
| 415 | Unsupported or mismatched file type |
| 422 | Invalid title/category/description |
| 500 | Storage or database failure (no success record) |

**Failure compensation:** validate → R2 put → DB insert. If DB insert fails after R2 put, the API attempts to delete the R2 object. Success is never returned if either required step fails. Residual risk: orphaned private R2 object if cleanup also fails.

**Audit:** upload allow/deny events are persisted to the `audit_events` hash chain (`DOCUMENT_UPLOAD`). SUCCESS events share the request transaction (fail-closed if the audit write fails). DENIED events use a separate committed session so a later request rollback does not erase the denial.

### `GET /documents`

Authenticated. Returns a paginated list of documents the caller may **discover**:

- Owned by the authenticated user, or
- Shared via an **active** READ or EDIT grant (`revoked_at IS NULL`)
- Soft-deleted documents (`deleted_at` set) are excluded
- **ADMIN role alone does not expand visibility**

Access filtering is applied in the PostgreSQL query before results are returned. Filters never reveal inaccessible documents (including title search against private titles).

| Query param | Notes |
| --- | --- |
| `title` | Case-insensitive substring search; max 200 characters |
| `owner_id` | UUID; only intersects with already-visible documents |
| `owner_email` | Normalized email; only intersects with already-visible documents |
| `category` | Exact match; max 128 characters |
| `created_from` / `created_to` | Inclusive ISO-8601 datetimes; `created_from` ≤ `created_to` |
| `shared_only` | When `true`, only documents shared with the caller (not owned). Cannot combine with `owner_id` |
| `page` | ≥ 1 (default 1) |
| `page_size` | 1–100 (default 20) |

Stable order: `created_at DESC`, `id DESC`.

Each row includes **`your_access`** (`OWNER` \| `EDIT` \| `READ`) from current PostgreSQL ownership/grants. This is document-level access, not the caller's platform role.

**Response `200`**

```json
{
  "results": [
    {
      "id": "00000000-0000-0000-0000-000000000000",
      "title": "Q3 Report",
      "category": "Finance",
      "owner": {
        "id": "00000000-0000-0000-0000-000000000001",
        "name": "Sheema Owner",
        "email": "sheema@trustvault.demo"
      },
      "mime_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
      "file_size": 12345,
      "created_at": "2026-10-21T12:00:00+00:00",
      "your_access": "READ"
    }
  ],
  "page": 1,
  "page_size": 20,
  "total": 1,
  "total_pages": 1
}
```

List items omit `description`, `storage_key`, checksum, and file bytes. Invalid filters/pagination → `422`.

### `GET /documents/{document_id}`

Authenticated. Returns safe metadata after centralized **read** authorization (`require_document_read`).

Includes: title, category, description, owner summary, mime type, size, SHA-256 checksum, `created_at`, `updated_at`, and **`your_access`** (`OWNER` | `EDIT` | `READ`) derived from the current PostgreSQL ownership/grant row for the caller.

**`your_access` is document-level, not a platform role.** It does not change `users.role`. Values:

- `OWNER` — caller is `documents.owner_id` (not “promoted” to platform OWNER)
- `EDIT` — active EDIT grant (metadata/content edit; no share/delete)
- `READ` — active READ grant (view/download only)

Platform roles (`ADMIN` / `OWNER` / `VIEWER`) remain separate. Sharing never elevates a recipient to ADMIN or OWNER. Platform ADMIN without ownership or a grant still receives **404** for this route.

Never returns `storage_key`, credentials, or file bytes.

| Status | Meaning |
| --- | --- |
| 200 | Authorized metadata |
| 401 | Missing/invalid token or inactive user |
| 404 | Missing, soft-deleted, or inaccessible (enumeration-resistant) |
| 503 | Authorization check failed (fail closed) |

### `GET /documents/{document_id}/download`

Authenticated. Streams file bytes from **private** Cloudflare R2 through the API after authorization.

Required sequence: authenticate → load document → verify not deleted → check ownership or active READ/EDIT grant → open R2 object → stream chunks → close R2 body.

Security:

- No public URL and no presigned download URL
- No redirect to R2
- Caller cannot supply the object key (taken from PostgreSQL only)
- R2 is not contacted before authorization succeeds
- Chunked streaming; R2 body closed when finished (including generator close)
- `Content-Type` from stored validated MIME type
- `Content-Disposition: attachment; filename="…"` with sanitized filename (CR/LF/quotes neutralized)
- `X-Content-Type-Options: nosniff`
- `Cache-Control: private, no-store`
- Immediate revocation: every request re-checks current grants

| Status | Meaning |
| --- | --- |
| 200 | Authorized byte stream |
| 401 | Missing/invalid token or inactive user |
| 404 | Missing, soft-deleted, or inaccessible |
| 503 | Storage missing-object / network failure (generic message; no keys/credentials) |

**Audit:** list/metadata/download success, denial, and storage failure events are written to the durable hash chain (`DOCUMENT_LIST`, `DOCUMENT_READ`, `DOCUMENT_DOWNLOAD`, storage failure reason codes).

### `GET /documents/{document_id}/permissions`

Authenticated **document owner** only (`require_document_owner`). Returns active grants (`revoked_at IS NULL`).

**Response `200`**

```json
{
  "document_id": "00000000-0000-0000-0000-000000000000",
  "permissions": [
    {
      "id": "00000000-0000-0000-0000-000000000010",
      "document_id": "00000000-0000-0000-0000-000000000000",
      "user": {
        "id": "00000000-0000-0000-0000-000000000002",
        "name": "Viewer",
        "email": "viewer@example.com"
      },
      "permission": "READ",
      "granted_at": "2026-10-21T12:00:00+00:00",
      "granted_by": {
        "id": "00000000-0000-0000-0000-000000000001",
        "name": "Owner",
        "email": "owner@example.com"
      },
      "regranted": false
    }
  ]
}
```

Never includes password hashes, tokens, or storage keys. READ/EDIT grantees and non-owners cannot enumerate grants (**403** if they have some document relationship, **404** if none).

### `POST /documents/{document_id}/permissions`

Authenticated **document owner** only. Creates an active READ or EDIT grant.

**Request**

```json
{
  "user_id": "EXISTING_USER_UUID",
  "permission": "READ"
}
```

Only `user_id` and `permission` are accepted (`extra=forbid`). `granted_by` is always the authenticated owner. `revoked_at` / ownership / audit fields are not accepted.

| Status | Meaning |
| --- | --- |
| 201 | Grant created (`regranted: true` when a prior revoked grant existed for the same user) |
| 400 | Cannot grant to owner; inactive target |
| 401 | Unauthenticated / inactive actor |
| 403 | Authenticated but not owner (e.g. EDIT grantee) |
| 404 | Document inaccessible/missing, or target user not found |
| 409 | Duplicate active grant (application check or unique index) |
| 422 | Invalid permission value or unknown fields |
| 503 | Persistence or audit failure (unaudited grant is removed) |

**Regrant policy:** revocation sets `revoked_at` and keeps history. A later owner grant inserts a **new** row; it does not silently clear `revoked_at` on the old row. Success audit uses reason `REGRANTED` when applicable.

### `DELETE /documents/{document_id}/permissions/{user_id}`

Authenticated **document owner** only. Soft-revokes the active grant (`revoked_at = now()`). Does not physically delete the permission row.

| Status | Meaning |
| --- | --- |
| 200 | Active grant revoked |
| 403 | Authenticated but not owner (grantee cannot self-revoke here) |
| 404 | Document inaccessible, or no active grant for that user (including already revoked) |
| 503 | Persistence or audit failure (revocation is undone if audit fails) |

**Immediate revocation:** the next `GET` metadata/download/list check queries PostgreSQL for `revoked_at IS NULL`. JWTs are not permission caches. Already-downloaded local copies are outside TrustVault control.

**Sharing audit:** `DOCUMENT_PERMISSION_LIST` / `DOCUMENT_PERMISSION_GRANT` / `DOCUMENT_PERMISSION_REVOKE` with SUCCESS or DENIED, optional `target_user_id`, persisted on the hash chain. Grant/revoke SUCCESS is fail-closed if audit cannot be written.

### `PUT /documents/{document_id}/content`

Authenticated. Replace the stored DOCX body for the **document owner** or an **active EDIT** grantee. READ grantees receive `403`. Rebuilds a minimal DOCX from plain text under the existing private R2 key and updates `file_size` / `sha256_checksum`. Complex Word formatting is not preserved.

**Request**

```json
{
  "text": "Updated document body\\nSecond paragraph"
}
```

**Response `200`:** same safe detail shape as `GET /documents/{id}` (includes `your_access`).

| Status | Meaning |
| --- | --- |
| 200 | Content replaced |
| 401 | Unauthenticated / inactive |
| 403 | Relationship exists but not edit rights (e.g. READ grant) |
| 404 | Missing, soft-deleted, or inaccessible |
| 415 | Non-DOCX document |
| 422 | Invalid / oversized text |
| 503 | Storage or persistence failure |

### `PATCH /documents/{document_id}`

Authenticated. Partial metadata update for the **document owner** or an **active EDIT** grantee (`require_document_edit` / `EDIT_METADATA`).

**Request** (`extra=forbid` — unknown fields rejected)

```json
{
  "title": "Updated title",
  "category": "Legal",
  "description": "Optional notes"
}
```

Only fields present in the body are considered (`exclude_unset`). Allowed keys: `title`, `category`, `description`. Forbidden examples: `owner_id`, `storage_key`, `file_size`, `sha256_checksum`, `mime_type`, `deleted_at`, permission/audit fields.

Validation mirrors upload rules (non-empty title/category when provided; length limits). Empty title/category → `422`.

**Response `200`:** same safe shape as `GET /documents/{id}` (no `storage_key`).

| Status | Meaning |
| --- | --- |
| 200 | Updated (or no-op when values unchanged) |
| 401 | Unauthenticated / inactive |
| 403 | Has document relationship but not edit rights (e.g. READ grant) |
| 404 | Missing, soft-deleted, or inaccessible |
| 422 | Invalid / forbidden fields |
| 503 | Lock/persist or audit failure |

**No-op policy:** if provided values match current metadata, response is still `200`; audit SUCCESS with `reason_code=NO_CHANGES` and `changed_fields=[]`. Successful edits audit field **names** only (not description contents).

**Concurrency:** document row (and active grant row for non-owners) locked with `FOR UPDATE`, then edit authorization re-checked. A revoke committed before that check denies the PATCH. A residual race under READ COMMITTED between check and commit is documented in `PERMISSIONS.md` / `THREATS.md` and is not claimed as fully eliminated.

### `DELETE /documents/{document_id}`

Authenticated **document owner** only (`require_document_delete`). Soft-deletes the row (`deleted_at`), then deletes the private R2 object using the server-side `storage_key`.

**Response `200`**

```json
{
  "id": "00000000-0000-0000-0000-000000000000",
  "deleted_at": "2026-10-21T12:00:00+00:00",
  "storage_cleanup": "completed"
}
```

`storage_cleanup` is `completed` or `already_absent` (idempotent if the object was already gone).

| Status | Meaning |
| --- | --- |
| 200 | Soft-deleted and storage cleanup completed/absent |
| 403 | Authenticated but not owner (READ/EDIT grantee) |
| 404 | Missing, already deleted, or inaccessible (repeated DELETE → 404) |
| 503 | DB soft-delete failed, **or** R2 cleanup failed after soft-delete |

**Failure strategy:** soft-delete first (immediately unlistable/unreadable/undownloadable), then R2 delete. If R2 fails, the soft-delete **remains** and the API returns **503** (does not claim complete deletion). Residual risk: private orphaned R2 object until a retry. Permission and audit history rows are retained. No client-supplied storage key.

**Mutation audit:** `DOCUMENT_METADATA_UPDATE`, `DOCUMENT_CONTENT_UPDATE`, `DOCUMENT_DELETE` with SUCCESS / DENIED; persisted on the hash chain. Metadata/content/delete SUCCESS is fail-closed if audit cannot be written.

### `GET /admin/summary`

**ADMIN only.** Accurate aggregate counts for the admin dashboard (no invented statistics):

```json
{
  "users_total": 12,
  "users_active": 10,
  "users_inactive": 2,
  "audit_success_total": 40,
  "audit_denied_total": 7
}
```

### `GET /admin/users`

**ADMIN only.** Paginated list of registered accounts (id, name, email, role, `is_active`, timestamps). Never returns password hashes. Does **not** grant document content access.

| Query | Notes |
| --- | --- |
| `page`, `page_size` | Pagination (`page_size` max 100) |

### `PATCH /admin/users/{user_id}`

**ADMIN only.** Body `{ "is_active": true|false }` (`extra=forbid` — role elevation rejected). Audits `ADMIN_USER_STATUS_UPDATE`.

Policy:

- Cannot deactivate the **last active administrator**
- Cannot deactivate **your own** account when other admins remain
- Disabled users receive **401** on the next protected request (active status is loaded from PostgreSQL, not from the JWT)
- Fail-closed if audit write fails after a status change

### `GET /admin/audit/events`

**ADMIN only.** Paginated audit events from PostgreSQL. Does not return secrets, tokens, or file bytes.

| Query | Notes |
| --- | --- |
| `page`, `page_size` | Pagination |
| `actor_id` | Filter by actor UUID |
| `action` | Exact action name |
| `document_id` | Filter by document UUID |
| `outcome` | `SUCCESS` or `DENIED` |
| `created_from`, `created_to` | Inclusive UTC range |

**Response `200`:** `{ results, page, page_size, total, total_pages }` where each result includes `id`, `created_at`, `actor_id`, `action`, `document_id`, `target_user_id`, `outcome`, `reason_code`, `request_id`, `metadata`, `previous_hash`, `event_hash`.

| Status | Meaning |
| --- | --- |
| 200 | Filtered page |
| 401 | Unauthenticated / inactive |
| 403 | Non-ADMIN |
| 422 | Invalid `outcome` or pagination |

### `GET /admin/audit/integrity`

**ADMIN only.** Recalculates SHA-256 event hashes and checks `previous_hash` links in `(created_at, id)` order.

**Response `200`:**

```json
{
  "valid": true,
  "event_count": 12,
  "checked_count": 12,
  "first_failure_index": null,
  "first_failure_event_id": null,
  "reason_code": null,
  "detail": "Audit chain integrity verified"
}
```

Empty chain returns `valid=true` with `reason_code=EMPTY_CHAIN`. There is **no** application endpoint to edit or delete audit history.

**Hash-chain notes:** appends use `pg_advisory_xact_lock` plus a monotonic `created_at` under that lock. Truncating the *newest* events without leaving a broken link is not detectable without an external chain-head anchor. A DBA who can rewrite the table can forge a new valid-looking chain — see `THREATS.md`.

## Auth login audit

`POST /auth/login` records `LOGIN` SUCCESS (same request transaction; fail-closed) or DENIED (`INVALID_CREDENTIALS` / `INACTIVE_ACCOUNT`) in an independent commit. Metadata may include `email_domain` only — never passwords or tokens. Inactive bearer access attempts may record `AUTH_INACTIVE_ACCESS`.

## Security testing

Automated authorization and IDOR regressions live in `backend/tests/security/`:

- `test_security_matrix.py` — owner / READ / EDIT / unrelated / ADMIN matrix, revocation, deactivation, mass-assignment, audit gates
- `test_role_permission_separation.py` — platform role vs document grant; ADMIN audit without content; grant does not promote roles; disabled accounts; forged IDs/role fields

Broader suites remain under `backend/tests/test_document_*.py`, `test_audit_trail.py`, and `test_admin_users.py`. Threat mitigations and residual risks: `THREATS.md`. How to reproduce an authorization-removal demo: `README.md`.

## Planned (not implemented)

- Token revocation / logout that invalidates issued JWTs
- Application-layer login rate limiting / account lockout
- Automated retry worker for orphaned R2 objects after `STORAGE_DELETE_FAILED`
- External audit-chain anchoring / WORM storage

All protected document and admin routes must enforce authorization on the server. Frontend route protection alone is not sufficient.

## Error shape

```json
{
  "detail": "Human-readable message"
}
```

Validation failures return `422` with an `errors` array.

## Required environment variables (names only)

| Variable | Purpose |
| --- | --- |
| `DATABASE_URL` | PostgreSQL connection string |
| `JWT_SECRET_KEY` | Signing secret (≥ 32 chars). Legacy `JWT_SECRET` also accepted. |
| `JWT_ALGORITHM` | Must be `HS256` |
| `JWT_ISSUER` | Expected token issuer (default `trustvault`) |
| `JWT_AUDIENCE` | Expected token audience (default `trustvault-api`) |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Access token lifetime (default `30`) |
| `DEMO_ADMIN_PASSWORD` / `DEMO_OWNER_PASSWORD` / `DEMO_VIEWER_PASSWORD` | Dev-only seed passwords |
| `R2_ACCOUNT_ID` / `R2_ACCESS_KEY_ID` / `R2_SECRET_ACCESS_KEY` / `R2_BUCKET_NAME` / `R2_ENDPOINT_URL` | Private R2 (required for real uploads) |

Never put signing secrets or R2 credentials in frontend `NEXT_PUBLIC_*` variables.
