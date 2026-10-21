"""Server-generated opaque object keys for private R2 storage."""

from __future__ import annotations

import uuid


def generate_object_key(*, prefix: str = "objects") -> str:
    """Return an opaque storage key. Never derived from a client filename."""
    clean_prefix = (prefix or "objects").strip().strip("/")
    if not clean_prefix:
        clean_prefix = "objects"
    return f"{clean_prefix}/{uuid.uuid4()}"
