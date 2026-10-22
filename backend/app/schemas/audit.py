"""Safe audit API schemas — never include secrets or file contents."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AuditEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime
    actor_id: UUID | None = None
    actor_name: str | None = None
    actor_email: str | None = None
    action: str
    document_id: UUID | None = None
    target_user_id: UUID | None = None
    target_user_name: str | None = None
    target_user_email: str | None = None
    outcome: str
    reason_code: str | None = None
    request_id: str | None = None
    metadata: dict = Field(default_factory=dict)
    previous_hash: str | None = None
    event_hash: str


class DocumentAuditSummary(BaseModel):
    """Counts for one document. Views mean authorised preview requests, not reading proof."""

    successful_views: int = 0
    distinct_viewers: int = 0
    latest_view_at: datetime | None = None
    successful_downloads: int = 0
    denied_access_attempts: int = 0
    permission_grants: int = 0
    permission_revocations: int = 0
    content_updates: int = 0
    metadata_updates: int = 0
    uploads: int = 0
    deletions: int = 0


class AuditEventListResponse(BaseModel):
    results: list[AuditEventResponse]
    page: int
    page_size: int
    total: int
    total_pages: int
    summary: DocumentAuditSummary | None = None


class DocumentViewActivityItem(BaseModel):
    document_id: UUID
    title: str
    owner_id: UUID
    owner_name: str
    owner_email: str
    total_views: int = Field(ge=0)
    distinct_viewers: int = Field(ge=0)
    latest_view_at: datetime | None = None


class DocumentViewPlatformSummary(BaseModel):
    total_view_events: int = Field(ge=0)
    documents_with_views: int = Field(ge=0)
    most_viewed: list[DocumentViewActivityItem] = Field(default_factory=list)


class DocumentViewActivityListResponse(BaseModel):
    results: list[DocumentViewActivityItem]
    page: int
    page_size: int
    total: int
    total_pages: int
    summary: DocumentViewPlatformSummary | None = None


class AuditIntegrityResponse(BaseModel):
    valid: bool
    event_count: int
    checked_count: int
    first_failure_index: int | None = None
    first_failure_event_id: UUID | None = None
    reason_code: str | None = None
    detail: str
