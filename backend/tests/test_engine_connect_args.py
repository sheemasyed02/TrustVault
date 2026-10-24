"""Regression: app engine must tolerate slow Neon cold connects."""

from app.db.session import (
    _APP_CONNECT_TIMEOUT_SECONDS,
    _TEST_CONNECT_TIMEOUT_SECONDS,
    build_engine_kwargs,
)


def test_app_engine_uses_extended_connect_timeout() -> None:
    kwargs = build_engine_kwargs(for_pytest=False)
    assert kwargs["connect_args"]["connect_timeout"] == _APP_CONNECT_TIMEOUT_SECONDS
    assert kwargs["connect_args"]["connect_timeout"] >= 60
    assert kwargs["pool_pre_ping"] is True
    assert kwargs["pool_recycle"] == 280
    assert "poolclass" not in kwargs


def test_pytest_engine_keeps_short_connect_timeout() -> None:
    kwargs = build_engine_kwargs(for_pytest=True)
    assert kwargs["connect_args"]["connect_timeout"] == _TEST_CONNECT_TIMEOUT_SECONDS
    assert kwargs["poolclass"] is not None
