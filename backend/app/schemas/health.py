"""Health check response schemas."""

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
    service: str
