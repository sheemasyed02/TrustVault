"""Owner-promotion request schemas."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class PromotionSubmitRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    justification: str | None = Field(default=None, max_length=2000)


class PromotionReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: str = Field(..., description="APPROVED or REJECTED")
    admin_note: str | None = Field(default=None, max_length=2000)


class PromotionRequesterSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    email: EmailStr
    role: str


class PromotionRequestResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    requester_id: UUID
    status: str
    justification: str | None
    admin_note: str | None
    reviewed_by: UUID | None
    created_at: datetime
    reviewed_at: datetime | None
    requester: PromotionRequesterSummary | None = None


class PromotionListResponse(BaseModel):
    results: list[PromotionRequestResponse]
    page: int
    page_size: int
    total: int
    total_pages: int
