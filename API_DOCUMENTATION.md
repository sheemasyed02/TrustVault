# TrustVault — API Documentation

Status: **Scaffold**. Only the health endpoint exists.

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

## Planned (not implemented)

These endpoints are required by the product definition and are **not** available yet:

- Authentication: login, logout, current user
- Documents: upload, list, search, details, metadata update, soft-delete, download stream
- Permissions: grant, revoke, list grants for a document
- Admin: user management, audit event listing/filtering, audit integrity verification

All protected document and admin routes must enforce authorization on the server. Frontend route protection alone is not sufficient.

## Error shape

Unhandled and HTTP errors return JSON:

```json
{
  "detail": "Human-readable message"
}
```

Validation failures return `422` with an `errors` array.
