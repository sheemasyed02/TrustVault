"""Application configuration loaded from environment variables."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.database_url import normalize_database_url

# backend/app/core/config.py → backend/.env (independent of process cwd)
_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_BACKEND_ENV_FILE = _BACKEND_ROOT / ".env"


class Settings(BaseSettings):
    """Runtime settings. Secrets belong in environment variables, not source."""

    model_config = SettingsConfigDict(
        env_file=str(_BACKEND_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    app_name: str = "TrustVault"
    app_env: str = Field(default="development", alias="APP_ENV")
    api_prefix: str = Field(default="/api/v1", alias="API_PREFIX")
    cors_origins: str = Field(
        default="http://localhost:3000,http://127.0.0.1:3000",
        alias="CORS_ORIGINS",
    )
    database_url: str = Field(alias="DATABASE_URL")

    # JWT — required before issuing or validating access tokens.
    jwt_secret_key: str | None = Field(default=None, alias="JWT_SECRET_KEY")
    # Legacy alias accepted for older local .env files; prefer JWT_SECRET_KEY.
    jwt_secret: str | None = Field(default=None, alias="JWT_SECRET")
    jwt_algorithm: str = Field(default="HS256", alias="JWT_ALGORITHM")
    jwt_issuer: str = Field(default="trustvault", alias="JWT_ISSUER")
    jwt_audience: str = Field(default="trustvault-api", alias="JWT_AUDIENCE")
    access_token_expire_minutes: int = Field(
        default=30,
        alias="ACCESS_TOKEN_EXPIRE_MINUTES",
    )

    # Cloudflare R2 — optional until a storage operation is attempted.
    r2_account_id: str | None = Field(default=None, alias="R2_ACCOUNT_ID")
    r2_access_key_id: str | None = Field(default=None, alias="R2_ACCESS_KEY_ID")
    r2_secret_access_key: str | None = Field(default=None, alias="R2_SECRET_ACCESS_KEY")
    r2_bucket_name: str | None = Field(default=None, alias="R2_BUCKET_NAME")
    r2_endpoint_url: str | None = Field(default=None, alias="R2_ENDPOINT_URL")

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, value: str) -> str:
        return normalize_database_url(value)

    @model_validator(mode="after")
    def validate_jwt_algorithm(self) -> "Settings":
        if self.jwt_algorithm != "HS256":
            raise ValueError("JWT_ALGORITHM must be HS256")
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        origins = [origin.strip() for origin in self.cors_origins.split(",")]
        return [origin for origin in origins if origin]

    @property
    def resolved_jwt_secret(self) -> str:
        secret = (self.jwt_secret_key or self.jwt_secret or "").strip()
        if not secret or secret == "CHANGE_ME_TO_A_LONG_RANDOM_VALUE":
            raise ValueError(
                "JWT_SECRET_KEY is required and must be a long random secret"
            )
        if len(secret) < 32:
            raise ValueError("JWT_SECRET_KEY must be at least 32 characters")
        return secret


@lru_cache
def get_settings() -> Settings:
    return Settings()
