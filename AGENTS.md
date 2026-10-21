# TrustVault — Agent Instructions

## Product definition

TrustVault is a secure document-sharing web application for confidential company documents. It must enforce document-level access control on the server and maintain an auditable record of document activity.

This is not merely a CRUD application or a static dashboard. Security and verified functionality take priority over the number of features.

## Technology stack

- Frontend: Next.js with TypeScript.
- Backend: FastAPI with Python.
- Database: PostgreSQL.
- ORM and migrations: SQLAlchemy and Alembic.
- File storage: private Cloudflare R2 using its S3-compatible API.
- Hosting: Railway for FastAPI and PostgreSQL; Vercel for Next.js.
- Automated backend tests: pytest.
- Version control: Git and GitHub.

Do not replace the chosen stack without asking me.

## Required roles and permissions

ADMIN:
- View and manage registered user accounts.
- Activate and deactivate accounts.
- View security audit events and permission changes.
- Run audit integrity verification.
- Must not automatically read or download every confidential document.

OWNER:
- Upload and organize documents they own.
- Search their authorized documents.
- View document details and download their own documents.
- Edit allowed metadata and soft-delete their own documents.
- Grant READ or EDIT permission to a named, registered user.
- Revoke grants they control.
- View the current permission list for their documents.

VIEWER:
- Access documents explicitly shared with them.
- READ permits reading and downloading.
- EDIT permits reading, downloading, and permitted metadata edits.
- VIEWER cannot share or revoke another owner's permissions.

Document ownership is not inferred from a client-provided ID. The server determines ownership and current access from authenticated identity and database state.

## Required functionality

1. Login and logout with securely hashed passwords and signed, expiring access tokens.
2. Role-aware navigation and protected frontend routes.
3. Document upload, listing, details, search, filtering, metadata editing, and deletion.
4. Private Cloudflare R2 storage using opaque server-generated object keys.
5. Per-document READ and EDIT grants to named users.
6. Permission revocation that denies the next protected request.
7. Search by document name, owner, category, and date without leaking unauthorized metadata.
8. Upload validation for size, file type, and file content where practical.
9. Administrative user management, activity logs, permission history, and audit integrity verification.
10. Automated tests proving unauthorized users cannot read, download, edit, delete, or share other users' documents.
11. THREATS.md, PROMPTS.md, API documentation, database migrations, deployment instructions, and a five-minute demo.

## Security requirements

- Every protected API endpoint must enforce authorization server-side.
- Hiding a button or protecting a frontend route is not authorization.
- Check current database permissions for every protected document request.
- Do not use long-lived public URLs or presigned download URLs that remain usable after revocation.
- Stream downloads through the backend only after authorization succeeds.
- Never trust client-supplied roles, owner IDs, grantor IDs, object keys, or permission claims.
- Deny access when authorization state is missing, invalid, or ambiguous.
- A disabled account cannot perform protected actions.
- Prevent IDOR, privilege escalation, unauthorized sharing, and metadata leakage.
- Do not log passwords, tokens, secrets, or file contents.
- Use server-generated UTC audit timestamps.
- Record successful and denied security-relevant actions.
- Use a hash chain for audit integrity, with concurrency-safe writes and verification tests.
- Document the limits of a hash chain stored in the same database; do not call it absolutely tamper-proof.
- Normal application APIs must not edit or delete historical audit events.
- Validate uploads and handle partial failures between storage and database operations.
- Do not expose secrets to the browser or commit them to Git.

## Database requirements

Use SQLAlchemy models and Alembic migrations to create and update the schema.

Required entities:
- users
- documents
- document_permissions
- audit_events

Add indexes, constraints, foreign keys, and appropriate transaction handling.

Keep file bytes in R2 and document metadata in PostgreSQL.

Use DATABASE_URL from environment configuration. Never silently fall back to SQLite or an in-memory database.

Do not ask me to create tables manually in a database dashboard. Generate migration files and give me the exact command to apply them.

## Required frontend pages

- Login
- Dashboard
- My Documents
- Shared With Me
- Upload Document
- Document Details
- Metadata Editing
- Permission Management
- Admin User Management
- Admin Audit Logs and Integrity Verification

Use a consistent, responsive enterprise UI. Include validation, loading, empty, error, and confirmation states. All visible actions must work against real backend APIs.

## Working rules for the agent

1. Inspect the repository and existing code before modifying it.
2. Work on one task at a time and do not implement unrelated functionality.
3. Before each task, explain what is being built and which files will change.
4. Prefer small, reviewable changes over rewrites.
5. Do not duplicate existing models, endpoints, migrations, or UI pages.
6. Never claim tests passed unless they were actually executed.
7. Run relevant tests and report their exact results.
8. Give me commands, the directory to run them in, and verification steps.
9. Never request that I share passwords or secret keys in chat.
10. Stop after each requested task and wait for confirmation.
11. If an existing security test fails, fix the underlying cause and add a regression test.
12. If a requirement is unclear, ask instead of inventing behaviour.

## Required completion report for each task

- What was implemented.
- Files created or changed.
- Database migration or environment changes required.
- Commands executed.
- Actual test results.
- Manual verification steps.
- Known limitations or unresolved failures.
- Suggested commit message.

Do not begin a different task until I approve the report.