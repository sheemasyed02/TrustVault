"""Health and readiness endpoints.

Liveness (`GET /health`) must stay cheap and secret-free for platform probes.
Readiness (`GET /health/ready`) may touch the database but must never return
URLs, credentials, stack traces, or confidential rows.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Response, status

from app.core.config import get_settings
from app.db.session import check_database_connection
from app.schemas.health import HealthResponse, ReadinessChecks, ReadinessResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def get_health() -> HealthResponse:
    """Process liveness — no database round-trip."""
    settings = get_settings()
    return HealthResponse(status="ok", service=settings.app_name)


@router.get(
    "/health/ready",
    response_model=ReadinessResponse,
    responses={
        503: {
            "description": "One or more dependencies are unavailable",
            "model": ReadinessResponse,
        }
    },
)
def get_readiness(response: Response) -> ReadinessResponse:
    """Dependency readiness for deploy verification.

    Returns HTTP 200 when the database accepts a trivial query, otherwise 503.
    Failure details are logged server-side without echoing connection strings.
    """
    settings = get_settings()
    database_ok = False
    try:
        database_ok = check_database_connection()
    except Exception:
        logger.exception("Readiness database check failed")
        database_ok = False

    ready = database_ok
    response.status_code = (
        status.HTTP_200_OK if ready else status.HTTP_503_SERVICE_UNAVAILABLE
    )
    return ReadinessResponse(
        status="ok" if ready else "unavailable",
        service=settings.app_name,
        checks=ReadinessChecks(database=database_ok),
    )
