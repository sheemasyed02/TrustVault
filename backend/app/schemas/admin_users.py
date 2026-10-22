"""Administrator user-management schemas."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class AdminPromotionSummary(BaseModel):
    """Safe owner-promotion request fields for admin profile views."""

    id: UUID
    status: str
    justification: str | None = None
    admin_note: str | None = None
    created_at: datetime
    reviewed_at: datetime | None = None
    reviewed_by: UUID | None = None


class AdminUserActivitySummary(BaseModel):
    """Counts derived from existing tables — never document bytes or storage keys."""

    owned_documents: int = Field(ge=0)
    active_grants_received: int = Field(ge=0)
    audit_events_as_actor: int = Field(ge=0)
    denied_audit_events_as_actor: int = Field(ge=0)


class AdminUserSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    email: EmailStr
    role: str
    is_active: bool
    created_at: datetime
    updated_at: datetime
    account_status: str = "Active"
    promotion_request_status: str | None = None
    promotion_requested_at: datetime | None = None
    pending_promotion_id: UUID | None = None


class AdminUserProfileResponse(AdminUserSummary):
    """Full admin profile — extends list summary with promotion + activity."""

    latest_promotion: AdminPromotionSummary | None = None
    activity: AdminUserActivitySummary


class AdminUserListResponse(BaseModel):
    results: list[AdminUserSummary]
    page: int
    page_size: int
    total: int
    total_pages: int


class AdminUserStatusUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    is_active: bool = Field(..., description="Activate or deactivate the account")


class AdminUserRoleUpdateRequest(BaseModel):
    """Ordinary role assignment via Manage Users.

    Only OWNER or VIEWER are accepted. ADMIN cannot be assigned here; existing
    administrators are provisioned via bootstrap/seed only.
    """

    model_config = ConfigDict(extra="forbid")

    role: str = Field(..., description="OWNER or VIEWER only")


class AdminSummaryResponse(BaseModel):
    """Accurate aggregate counts for the admin dashboard (no invented stats)."""

    users_total: int = Field(ge=0)
    users_active: int = Field(ge=0)
    users_inactive: int = Field(ge=0)
    audit_success_total: int = Field(ge=0)
    audit_denied_total: int = Field(ge=0)
