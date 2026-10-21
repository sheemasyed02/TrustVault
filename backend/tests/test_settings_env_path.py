"""Settings must load backend/.env even when the process cwd is elsewhere."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from app.core.config import _BACKEND_ENV_FILE, get_settings


def test_backend_env_file_path_is_absolute_under_backend() -> None:
    assert _BACKEND_ENV_FILE.is_absolute()
    assert _BACKEND_ENV_FILE.name == ".env"
    assert _BACKEND_ENV_FILE.parent.name == "backend"


def test_settings_load_from_backend_env_when_cwd_is_repo_root(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    monkeypatch.chdir(repo_root)
    # Clear process env overrides so the file path is exercised.
    for key in (
        "DATABASE_URL",
        "R2_ACCOUNT_ID",
        "R2_ACCESS_KEY_ID",
        "R2_SECRET_ACCESS_KEY",
        "R2_BUCKET_NAME",
        "R2_ENDPOINT_URL",
        "JWT_SECRET_KEY",
    ):
        monkeypatch.delenv(key, raising=False)

    if not _BACKEND_ENV_FILE.is_file():
        pytest.skip("backend/.env is not present in this environment")

    get_settings.cache_clear()
    try:
        settings = get_settings()
    finally:
        get_settings.cache_clear()

    assert (settings.database_url or "").strip()
    # Presence only — never assert secret values.
    assert bool((settings.r2_bucket_name or "").strip())
    assert bool((settings.r2_access_key_id or "").strip())
    assert bool((settings.r2_secret_access_key or "").strip())
    assert os.getcwd() == str(repo_root)
