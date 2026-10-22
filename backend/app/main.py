"""TrustVault FastAPI application entrypoint."""

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


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        description=(
            "Secure document sharing API. "
            "Register/login, upload PDF/DOCX, list, metadata, content edit, PDF download, "
            "grant/revoke, owner soft-delete, owner promotion, and administrator audit/user management."
        ),
        version="0.1.0",
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
