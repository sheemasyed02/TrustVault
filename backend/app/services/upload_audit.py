"""Document/upload audit integration point.

A durable audit writer is not implemented yet. Hooks may log safe reason codes
but must not claim persistence unless a real audit service records the event.
Never pass passwords, tokens, credentials, or file bytes into these hooks.
"""

from __future__ import annotations

import logging
import uuid
from typing import Protocol

logger = logging.getLogger(__name__)


class UploadAuditHook(Protocol):
    def record(
        self,
        *,
        action: str,
        outcome: str,
        reason_code: str | None = None,
        actor_id: uuid.UUID | None = None,
        document_id: uuid.UUID | None = None,
        target_user_id: uuid.UUID | None = None,
        request_id: str | None = None,
        changed_fields: list[str] | None = None,
    ) -> None: ...


class NullUploadAuditHook:
    """Logs allow/deny style events without durable persistence."""

    def record(
        self,
        *,
        action: str,
        outcome: str,
        reason_code: str | None = None,
        actor_id: uuid.UUID | None = None,
        document_id: uuid.UUID | None = None,
        target_user_id: uuid.UUID | None = None,
        request_id: str | None = None,
        changed_fields: list[str] | None = None,
    ) -> None:
        logger.info(
            "Document audit event (not persisted)",
            extra={
                "audit_action": action,
                "audit_outcome": outcome,
                "audit_reason": reason_code,
                "audit_changed_fields": changed_fields,
                "audit_persisted": False,
            },
        )


class RecordingUploadAuditHook:
    """In-memory recorder for tests. Still not a durable audit store."""

    def __init__(self) -> None:
        self.events: list[dict] = []

    def record(
        self,
        *,
        action: str,
        outcome: str,
        reason_code: str | None = None,
        actor_id: uuid.UUID | None = None,
        document_id: uuid.UUID | None = None,
        target_user_id: uuid.UUID | None = None,
        request_id: str | None = None,
        changed_fields: list[str] | None = None,
    ) -> None:
        self.events.append(
            {
                "action": action,
                "outcome": outcome,
                "reason_code": reason_code,
                "actor_id": actor_id,
                "document_id": document_id,
                "target_user_id": target_user_id,
                "request_id": request_id,
                "changed_fields": changed_fields,
                "persisted": False,
            }
        )


class FailingUploadAuditHook:
    """Test double that refuses to record; simulates audit backend failure."""

    def record(
        self,
        *,
        action: str,
        outcome: str,
        reason_code: str | None = None,
        actor_id: uuid.UUID | None = None,
        document_id: uuid.UUID | None = None,
        target_user_id: uuid.UUID | None = None,
        request_id: str | None = None,
        changed_fields: list[str] | None = None,
    ) -> None:
        raise RuntimeError("Audit backend unavailable")
