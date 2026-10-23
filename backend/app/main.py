"""TrustVault FastAPI application entrypoint."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.admin import router as admin_router
from app.api.auth import router as auth_router
from app.api.document_permissions import router as document_permissions_router
from app.api.documents import router as documents_router
from app.api.health import router as health_router
from app.api.promotions import router as promotions_router
from app.api.users import router as users_router
from app.core.config import get_settings
from app.core.errors import register_exception_handlers

logger = logging.getLogger(__name__)


def _configure_logging() -> None:
    """Ensure startup/request errors are visible on the hosting platform."""
    root = logging.getLogger()
    if not root.handlers:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        )


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Validate non-secret configuration on boot.

    Does not seed users, run Alembic, create/drop schema, or print credentials.
    """
    _configure_logging()
    settings = get_settings()
    try:
        _ = settings.resolved_jwt_secret
    except ValueError as exc:
        logger.error("Startup configuration error: %s", exc)
        raise
    if "*" in settings.cors_origin_list:
        logger.error("CORS_ORIGINS must not use '*' when credentials are enabled")
        raise RuntimeError("Invalid CORS_ORIGINS: wildcard is not allowed")
    logger.info(
        "TrustVault API starting (env=%s, cors_origins=%d)",
        settings.app_env,
        len(settings.cors_origin_list),
    )
    yield
    logger.info("TrustVault API shutting down")


def create_app() -> FastAPI:
    settings = get_settings()
    # Hide interactive OpenAPI surfaces in production (attack-surface reduction).
    # Schema remains available locally/dev for engineers.
    expose_api_docs = settings.app_env.strip().lower() not in {
        "production",
        "prod",
    }
    app = FastAPI(
        title=settings.app_name,
        description=(
            "Secure document sharing API. "
            "Register/login, upload DOCX, list, metadata, content edit, authorized download, "
            "grant/revoke, owner soft-delete, owner promotion, and administrator audit/user management."
        ),
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs" if expose_api_docs else None,
        redoc_url="/redoc" if expose_api_docs else None,
        openapi_url="/openapi.json" if expose_api_docs else None,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID", "Accept"],
        # Browser JS cannot read Content-Disposition unless exposed (cross-origin
        # frontend → API). Without this, downloads fall back to a useless .bin name.
        expose_headers=[
            "Content-Disposition",
            "Content-Type",
            "Content-Length",
            "X-Request-ID",
            "X-Content-Type-Options",
        ],
    )

    register_exception_handlers(app)
    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(users_router)
    app.include_router(documents_router)
    app.include_router(document_permissions_router)
    app.include_router(promotions_router)
    app.include_router(admin_router)

    return app


app = create_app()
