"""Process-local rate limiting for forgot-password requests.

Keys are SHA-256 hashes of IP and email so raw identifiers are not retained in
the limiter map. Suitable for the current single-instance Render deployment;
limits are per process (not shared across multiple replicas).
"""

from __future__ import annotations

import hashlib
import threading
import time
from dataclasses import dataclass

from app.core.config import Settings


class PasswordResetRateLimitExceeded(Exception):
    """Raised when IP or email exceeds the configured forgot-password budget."""

    def __init__(self, message: str = "Too many password reset requests") -> None:
        super().__init__(message)
        self.message = message
        self.reason_code = "RATE_LIMITED"


@dataclass
class _Bucket:
    window_started_at: float
    hits: int


_lock = threading.Lock()
_buckets: dict[str, _Bucket] = {}


def _hash_key(scope: str, value: str) -> str:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
    return f"{scope}:{digest}"


def reset_password_reset_rate_limiter() -> None:
    """Clear in-memory buckets (tests only)."""
    with _lock:
        _buckets.clear()


def check_forgot_password_rate_limit(
    *,
    client_ip: str,
    email: str,
    settings: Settings,
) -> None:
    """Increment IP and email counters; raise if either budget is exhausted."""
    window = max(1, int(settings.password_reset_rate_limit_window_seconds))
    ip_max = max(1, int(settings.password_reset_rate_limit_ip_max))
    email_max = max(1, int(settings.password_reset_rate_limit_email_max))

    ip_value = (client_ip or "unknown").strip() or "unknown"
    email_value = (email or "").strip().lower()
    now = time.monotonic()

    with _lock:
        _hit_or_raise(
            key=_hash_key("ip", ip_value),
            now=now,
            window=window,
            limit=ip_max,
        )
        _hit_or_raise(
            key=_hash_key("email", email_value),
            now=now,
            window=window,
            limit=email_max,
        )


def _hit_or_raise(*, key: str, now: float, window: int, limit: int) -> None:
    bucket = _buckets.get(key)
    if bucket is None or (now - bucket.window_started_at) >= window:
        _buckets[key] = _Bucket(window_started_at=now, hits=1)
        return
    if bucket.hits >= limit:
        raise PasswordResetRateLimitExceeded()
    bucket.hits += 1
