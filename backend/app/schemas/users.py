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
