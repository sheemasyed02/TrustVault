"""SHA-256 helpers for uploaded content."""

from __future__ import annotations

import hashlib
from typing import BinaryIO


def sha256_hex_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_hex_stream(stream: BinaryIO, *, chunk_size: int = 1024 * 1024) -> tuple[str, int]:
    """Hash a stream without loading it all into memory.

    The stream position is restored when seekable.
    """
    digest = hashlib.sha256()
    total = 0
    start = stream.tell() if stream.seekable() else None

    while True:
        chunk = stream.read(chunk_size)
        if not chunk:
            break
        digest.update(chunk)
        total += len(chunk)

    if start is not None and stream.seekable():
        stream.seek(start)

    return digest.hexdigest(), total
