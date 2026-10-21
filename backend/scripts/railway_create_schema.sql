-- TrustVault schema for Railway PostgreSQL
-- Matches Alembic revision: 7afa3a6e7e04
--
-- How to use:
-- 1. Open Railway -> Postgres service -> Data / Query
-- 2. Paste this entire script
-- 3. Run it once
-- 4. Verify with the SELECT at the bottom
--
-- Safe to re-run only if tables do not already exist.
-- If tables already exist, stop and do not re-run.

BEGIN;

CREATE TABLE IF NOT EXISTS alembic_version (
    version_num VARCHAR(32) NOT NULL,
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);

CREATE TABLE users (
    id UUID NOT NULL,
    name VARCHAR(255) NOT NULL,
    email VARCHAR(320) NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(32) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT users_pkey PRIMARY KEY (id),
    CONSTRAINT users_email_key UNIQUE (email),
    CONSTRAINT ck_users_role CHECK (role IN ('ADMIN', 'OWNER', 'VIEWER'))
);

CREATE INDEX ix_users_created_at ON users (created_at);
CREATE INDEX ix_users_is_active ON users (is_active);
CREATE INDEX ix_users_role ON users (role);

CREATE TABLE documents (
    id UUID NOT NULL,
    owner_id UUID NOT NULL,
    title VARCHAR(255) NOT NULL,
    category VARCHAR(128) NOT NULL,
    description TEXT,
    storage_key VARCHAR(512) NOT NULL,
    mime_type VARCHAR(255) NOT NULL,
    file_size BIGINT NOT NULL,
    sha256_checksum VARCHAR(64) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at TIMESTAMPTZ,
    CONSTRAINT documents_pkey PRIMARY KEY (id),
    CONSTRAINT documents_storage_key_key UNIQUE (storage_key),
    CONSTRAINT documents_owner_id_fkey
        FOREIGN KEY (owner_id) REFERENCES users (id) ON DELETE RESTRICT
);

CREATE INDEX ix_documents_category ON documents (category);
CREATE INDEX ix_documents_created_at ON documents (created_at);
CREATE INDEX ix_documents_deleted_at ON documents (deleted_at);
CREATE INDEX ix_documents_owner_id ON documents (owner_id);
CREATE INDEX ix_documents_owner_id_deleted_at ON documents (owner_id, deleted_at);
CREATE INDEX ix_documents_title ON documents (title);

CREATE TABLE audit_events (
    id UUID NOT NULL,
    actor_id UUID,
    action VARCHAR(128) NOT NULL,
    document_id UUID,
    target_user_id UUID,
    outcome VARCHAR(32) NOT NULL,
    reason_code VARCHAR(128),
    request_id VARCHAR(128),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    previous_hash VARCHAR(64),
    event_hash VARCHAR(64) NOT NULL,
    CONSTRAINT audit_events_pkey PRIMARY KEY (id),
    CONSTRAINT uq_audit_events_event_hash UNIQUE (event_hash),
    CONSTRAINT ck_audit_events_outcome CHECK (outcome IN ('SUCCESS', 'DENIED')),
    CONSTRAINT audit_events_actor_id_fkey
        FOREIGN KEY (actor_id) REFERENCES users (id) ON DELETE SET NULL,
    CONSTRAINT audit_events_document_id_fkey
        FOREIGN KEY (document_id) REFERENCES documents (id) ON DELETE SET NULL,
    CONSTRAINT audit_events_target_user_id_fkey
        FOREIGN KEY (target_user_id) REFERENCES users (id) ON DELETE SET NULL
);

CREATE INDEX ix_audit_events_action ON audit_events (action);
CREATE INDEX ix_audit_events_actor_id ON audit_events (actor_id);
CREATE INDEX ix_audit_events_created_at ON audit_events (created_at);
CREATE INDEX ix_audit_events_document_id ON audit_events (document_id);
CREATE INDEX ix_audit_events_outcome ON audit_events (outcome);
CREATE INDEX ix_audit_events_request_id ON audit_events (request_id);
CREATE INDEX ix_audit_events_target_user_id ON audit_events (target_user_id);

CREATE TABLE document_permissions (
    id UUID NOT NULL,
    document_id UUID NOT NULL,
    user_id UUID NOT NULL,
    permission VARCHAR(16) NOT NULL,
    granted_by UUID NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    revoked_at TIMESTAMPTZ,
    CONSTRAINT document_permissions_pkey PRIMARY KEY (id),
    CONSTRAINT ck_document_permissions_permission CHECK (permission IN ('READ', 'EDIT')),
    CONSTRAINT document_permissions_document_id_fkey
        FOREIGN KEY (document_id) REFERENCES documents (id) ON DELETE CASCADE,
    CONSTRAINT document_permissions_granted_by_fkey
        FOREIGN KEY (granted_by) REFERENCES users (id) ON DELETE RESTRICT,
    CONSTRAINT document_permissions_user_id_fkey
        FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE INDEX ix_document_permissions_created_at ON document_permissions (created_at);
CREATE INDEX ix_document_permissions_document_id ON document_permissions (document_id);
CREATE INDEX ix_document_permissions_granted_by ON document_permissions (granted_by);
CREATE INDEX ix_document_permissions_user_id ON document_permissions (user_id);
CREATE INDEX ix_document_permissions_user_id_revoked_at ON document_permissions (user_id, revoked_at);

-- Only one active grant per document + user
CREATE UNIQUE INDEX uq_document_permissions_active_document_user
    ON document_permissions (document_id, user_id)
    WHERE revoked_at IS NULL;

-- Mark this schema as matching the Alembic migration already used locally
INSERT INTO alembic_version (version_num)
VALUES ('7afa3a6e7e04')
ON CONFLICT (version_num) DO NOTHING;

COMMIT;

-- Verification (run after the script succeeds):
-- SELECT table_name
-- FROM information_schema.tables
-- WHERE table_schema = 'public'
--   AND table_name IN ('users', 'documents', 'document_permissions', 'audit_events', 'alembic_version')
-- ORDER BY table_name;
