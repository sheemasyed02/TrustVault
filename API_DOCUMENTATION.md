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

## Planned (not implemented)

- Document upload, list, search, details, metadata update, soft-delete, download stream
- Permissions: grant, revoke, list grants
- Admin user management, audit listing/filtering, audit integrity verification
- Token revocation / logout that invalidates issued JWTs

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

Never put signing secrets in frontend `NEXT_PUBLIC_*` variables.
