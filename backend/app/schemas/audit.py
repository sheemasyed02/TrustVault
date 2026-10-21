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
    action: str
    document_id: UUID | None = None
    target_user_id: UUID | None = None
    outcome: str
    reason_code: str | None = None
    request_id: str | None = None
    metadata: dict = Field(default_factory=dict)
    previous_hash: str | None = None
    event_hash: str


class AuditEventListResponse(BaseModel):
    results: list[AuditEventResponse]
    page: int
    page_size: int
    total: int
    total_pages: int


class AuditIntegrityResponse(BaseModel):
    valid: bool
    event_count: int
    checked_count: int
    first_failure_index: int | None = None
    first_failure_event_id: UUID | None = None
    reason_code: str | None = None
    detail: str
