"""Administrator user-management schemas."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class AdminUserSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    email: EmailStr
    role: str
    is_active: bool
    created_at: datetime
    updated_at: datetime


class AdminUserListResponse(BaseModel):
    results: list[AdminUserSummary]
    page: int
    page_size: int
    total: int
    total_pages: int


class AdminUserStatusUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    is_active: bool = Field(..., description="Activate or deactivate the account")


class AdminSummaryResponse(BaseModel):
    """Accurate aggregate counts for the admin dashboard (no invented stats)."""

    users_total: int = Field(ge=0)
    users_active: int = Field(ge=0)
    users_inactive: int = Field(ge=0)
    audit_success_total: int = Field(ge=0)
    audit_denied_total: int = Field(ge=0)
