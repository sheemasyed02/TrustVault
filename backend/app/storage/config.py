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


def r2_config_presence(settings: Settings | None = None) -> dict[str, bool]:
    """Report which R2 setting *names* are present (never values)."""
    resolved = settings or get_settings()
    return {
        "R2_ACCOUNT_ID": bool((resolved.r2_account_id or "").strip()),
        "R2_ACCESS_KEY_ID": bool((resolved.r2_access_key_id or "").strip()),
        "R2_SECRET_ACCESS_KEY": bool((resolved.r2_secret_access_key or "").strip()),
        "R2_BUCKET_NAME": bool((resolved.r2_bucket_name or "").strip()),
        "R2_ENDPOINT_URL": bool((resolved.r2_endpoint_url or "").strip()),
    }


def load_r2_config(settings: Settings | None = None) -> R2Config:
    """Load R2 settings or raise a safe configuration error."""
    resolved = settings or get_settings()
    missing = _missing_r2_fields(resolved)
    if missing:
        raise StorageConfigurationError(
            "Cloudflare R2 is not configured. Missing: " + ", ".join(missing)
        )

    account_id = resolved.r2_account_id.strip()
    endpoint = resolved.r2_endpoint_url.strip()
    # Allow a bare account-id-based default when the URL was left as a placeholder.
    if "your_account_id" in endpoint.lower():
        endpoint = f"https://{account_id}.r2.cloudflarestorage.com"
    if not (
        endpoint.startswith("https://")
        or endpoint.startswith("http://")
    ):
        raise StorageConfigurationError(
            "R2_ENDPOINT_URL must be an http(s) endpoint URL"
        )

    return R2Config(
        account_id=account_id,
        access_key_id=resolved.r2_access_key_id.strip(),
        secret_access_key=resolved.r2_secret_access_key.strip(),
        bucket_name=resolved.r2_bucket_name.strip(),
        endpoint_url=endpoint,
    )
