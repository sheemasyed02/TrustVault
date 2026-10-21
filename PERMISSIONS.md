# TrustVault — Permissions Model

Status: **Planned**. No authorization is enforced in the current scaffold.

## Roles

### ADMIN

- Manage registered user accounts (activate / deactivate).
- View security audit events and permission-change history.
- Run audit integrity verification.
- Does **not** automatically receive READ/EDIT/download access to every confidential document.

### OWNER

- Upload and organize documents they own.
- View, download, edit allowed metadata, and soft-delete their own documents.
- Grant READ or EDIT to a named, registered user.
- Revoke grants they control.
- View the current permission list for their documents.

### VIEWER

- Access only documents explicitly shared with them.
- READ: view and download.
- EDIT: view, download, and permitted metadata edits.
- Cannot share or revoke another owner's permissions.

## Grant rules

- Ownership and access are determined from authenticated identity and database state.
- Client-supplied roles, owner IDs, grantor IDs, object keys, or permission claims are never trusted.
- Revocation must deny the next protected request.
- Disabled accounts cannot perform protected actions.

## Implementation status

| Control | Status |
| --- | --- |
| Login / access tokens | Not implemented |
| Document grants | Not implemented |
| Server-side authorization checks | Not implemented |
| Admin user management | Not implemented |
