"""Safe user profile schemas — never include password hashes."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    email: EmailStr
    role: str
    is_active: bool
    created_at: datetime
    updated_at: datetime


class ProfileUpdateRequest(BaseModel):
    """Self-service name update. Email, role, and status are not accepted."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=2, max_length=255)


class ChangePasswordRequest(BaseModel):
    """Self-service password change. Never echoed back in responses."""

    model_config = ConfigDict(extra="forbid")

    current_password: str = Field(min_length=1, max_length=1024)
    new_password: str = Field(min_length=10, max_length=128)
    confirm_password: str = Field(min_length=10, max_length=128)


class ChangePasswordResponse(BaseModel):
    message: str


class UserSearchHit(BaseModel):
    """Minimal recipient fields for the share picker — no role/hash/tokens."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    email: EmailStr


class UserSearchResponse(BaseModel):
    results: list[UserSearchHit]
    page: int = Field(ge=1)
    page_size: int = Field(ge=1)
    total: int = Field(ge=0)
    total_pages: int = Field(ge=0)
