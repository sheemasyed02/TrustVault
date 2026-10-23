"""Health check response schemas (no secrets or connection strings)."""

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """Liveness: process is up. Does not prove database connectivity."""

    status: str
    service: str


class ReadinessChecks(BaseModel):
    """Boolean checks only — never include URLs, credentials, or row data."""

    database: bool = Field(
        description="True when a simple SELECT 1 against DATABASE_URL succeeds."
    )


class ReadinessResponse(BaseModel):
    """Readiness: dependency checks for load balancers and deploy smoke tests."""

    status: str
    service: str
    checks: ReadinessChecks
