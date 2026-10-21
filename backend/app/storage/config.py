"""Validated R2 configuration loaded from environment settings."""

from __future__ import annotations

from dataclasses import dataclass

from app.core.config import Settings, get_settings
from app.storage.exceptions import StorageConfigurationError

REQUIRED_R2_FIELDS = (
    "r2_account_id",
    "r2_access_key_id",
    "r2_secret_access_key",
    "r2_bucket_name",
    "r2_endpoint_url",
)


@dataclass(frozen=True, slots=True)
class R2Config:
    account_id: str
    access_key_id: str
    secret_access_key: str
    bucket_name: str
    endpoint_url: str


def _missing_r2_fields(settings: Settings) -> list[str]:
    missing: list[str] = []
    mapping = {
        "R2_ACCOUNT_ID": settings.r2_account_id,
        "R2_ACCESS_KEY_ID": settings.r2_access_key_id,
        "R2_SECRET_ACCESS_KEY": settings.r2_secret_access_key,
        "R2_BUCKET_NAME": settings.r2_bucket_name,
        "R2_ENDPOINT_URL": settings.r2_endpoint_url,
    }
    for name, value in mapping.items():
        if value is None or not str(value).strip():
            missing.append(name)
    return missing


def load_r2_config(settings: Settings | None = None) -> R2Config:
    """Load R2 settings or raise a safe configuration error."""
    resolved = settings or get_settings()
    missing = _missing_r2_fields(resolved)
    if missing:
        raise StorageConfigurationError(
            "Cloudflare R2 is not configured. Missing: " + ", ".join(missing)
        )

    endpoint = resolved.r2_endpoint_url.strip()
    if not (
        endpoint.startswith("https://")
        or endpoint.startswith("http://")
    ):
        raise StorageConfigurationError(
            "R2_ENDPOINT_URL must be an http(s) endpoint URL"
        )

    return R2Config(
        account_id=resolved.r2_account_id.strip(),
        access_key_id=resolved.r2_access_key_id.strip(),
        secret_access_key=resolved.r2_secret_access_key.strip(),
        bucket_name=resolved.r2_bucket_name.strip(),
        endpoint_url=endpoint,
    )
