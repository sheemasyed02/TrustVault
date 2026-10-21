"""Safe document API schemas — never include storage credentials or file bytes."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class DocumentOwnerSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    email: EmailStr


class DocumentCreatedResponse(BaseModel):
    id: UUID
    title: str
    category: str
    description: str | None = None
    owner: DocumentOwnerSummary
    original_filename: str | None = None
    mime_type: str
    file_size: int = Field(ge=0)
    sha256_checksum: str
    created_at: datetime


class DocumentListItem(BaseModel):
    """List rows omit description to reduce unnecessary metadata exposure."""

    id: UUID
    title: str
    category: str
    owner: DocumentOwnerSummary
    original_filename: str | None = None
    mime_type: str
    file_size: int = Field(ge=0)
    created_at: datetime
    # Document-level access for the caller (not users.role).
    your_access: str = Field(description="OWNER, EDIT, or READ")


class DocumentListResponse(BaseModel):
    results: list[DocumentListItem]
    page: int
    page_size: int
    total: int
    total_pages: int


class DocumentDetailResponse(BaseModel):
    id: UUID
    title: str
    category: str
    description: str | None = None
    owner: DocumentOwnerSummary
    original_filename: str | None = None
    mime_type: str
    file_size: int = Field(ge=0)
    sha256_checksum: str
    created_at: datetime
    updated_at: datetime
    # Document-level access from PostgreSQL (never trust client claims).
    # OWNER = documents.owner_id; EDIT/READ = active grant. Not users.role.
    your_access: str = Field(
        description="Document access: OWNER (owner_id), EDIT, or READ — not a platform role"
    )


class DocumentMetadataUpdateRequest(BaseModel):
    """Only title/category/description may be patched; all other fields forbidden."""

    model_config = ConfigDict(extra="forbid")

    title: str | None = None
    category: str | None = None
    description: str | None = None


class DocumentContentUpdateRequest(BaseModel):
    """Plain-text body used to rebuild the stored DOCX for in-app editors."""

    model_config = ConfigDict(extra="forbid")

    text: str = Field(..., max_length=500_000)


class DocumentDeleteResponse(BaseModel):
    id: UUID
    deleted_at: datetime
    storage_cleanup: str


class PermissionGrantRequest(BaseModel):
    """Only these fields are accepted; granted_by/revoked_at are server-set."""

    model_config = ConfigDict(extra="forbid")

    user_id: UUID
    permission: str = Field(..., min_length=1, max_length=16)


class PermissionUserSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    email: EmailStr


class PermissionGrantResponse(BaseModel):
    id: UUID
    document_id: UUID
    user: PermissionUserSummary
    permission: str
    granted_at: datetime
    granted_by: PermissionUserSummary
    regranted: bool = False


class PermissionListResponse(BaseModel):
    document_id: UUID
    permissions: list[PermissionGrantResponse]


class PermissionRevokeResponse(BaseModel):
    document_id: UUID
    user_id: UUID
    permission: str
    revoked_at: datetime
