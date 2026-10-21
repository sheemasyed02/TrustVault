# TrustVault — Threat Model

This document separates **planned** mitigations from mitigations that are **implemented and tested**. The current repository is a scaffold; most controls below are planned only.

## Assets

- Confidential document bytes stored in private Cloudflare R2
- Document metadata and permission grants in PostgreSQL
- User credentials and access tokens
- Audit event history and integrity chain

## Actors

- Authenticated ADMIN, OWNER, and VIEWER users
- Disabled or revoked users
- Unauthenticated outsiders
- Insiders with database or hosting console access

## Threats and mitigations

| ID | Threat | Planned mitigation | Implemented and tested |
| --- | --- | --- | --- |
| T1 | Unauthorized document read/download (IDOR) | Server-side permission check on every protected request; stream downloads only after authz | No |
| T2 | Privilege escalation via client-supplied role/owner claims | Ignore client role/owner/permission fields; derive identity from signed token and DB | No |
| T3 | Access after permission revocation | Re-check current grants on each request; no long-lived public/presigned download URLs | No |
| T4 | Public exposure of R2 objects | Private bucket; opaque server-generated keys; backend-mediated download | No |
| T5 | Credential theft / weak auth | Hashed passwords; signed, expiring tokens; no secrets in logs or browser bundles | No |
| T6 | Disabled account still acting | Reject protected actions when account is inactive | No |
| T7 | Metadata leakage in search/list | Return only authorized documents; generic denial responses where appropriate | No |
| T8 | Audit log tampering via app APIs | Append-only application writes; no edit/delete audit endpoints for normal APIs | No |
| T9 | Undetected audit history alteration | Hash chain with verification endpoint and tests; document DB-admin limits honestly | No |
| T10 | Secret leakage via Git or frontend | `.env` ignored; `.env.example` placeholders only; no secrets in client code | Partial: ignore rules and example env files exist; no secret-scanning tests yet |
| T11 | Upload abuse | Size, type, and content validation; handle storage/DB partial failures | No |
| T12 | CORS misuse | Allowed origins loaded from configuration | Partial: CORS middleware reads `CORS_ORIGINS`; not security-tested against hostile origins |

## Honest limits

A hash chain stored in the same PostgreSQL database is **not** proof against a privileged database administrator who can rewrite both events and hashes. It helps detect accidental or limited tampering and supports operational verification. Stronger guarantees require external append-only storage or monitoring outside the application database.

## Current scaffold exposure

- Frontend landing/login UI does not authenticate users.
- Backend exposes only `GET /health`.
- No database tables, auth, documents, or R2 integration exist yet.
