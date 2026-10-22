"""Authentication request and response schemas."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: str = Field(min_length=1, max_length=1024)


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: datetime
    expires_in: int


class RegisterRequest(BaseModel):
    """Public registration. Role is never accepted from the client."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=2, max_length=255)
    email: EmailStr
    password: str = Field(min_length=10, max_length=128)


class RegisterResponse(BaseModel):
    id: str
    name: str
    email: EmailStr
    role: str
    message: str
