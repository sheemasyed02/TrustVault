"""Document/upload audit integration point.

Production uses DurableAuditHook (hash-chain persistence). Test doubles may
override FastAPI dependencies with RecordingUploadAuditHook / NullUploadAuditHook.
Never pass passwords, tokens, credentials, or file bytes into these hooks.
"""

from __future__ import annotations

import logging
import uuid
from typing import Protocol

from sqlalchemy.orm import Session

from app.services.audit_trail import (
    AuditTrailError,
    append_audit_event,
    append_audit_event_committed,
)

logger = logging.getLogger(__name__)


def _merge_metadata(
    *,
    changed_fields: list[str] | None,
    metadata: dict | None,
) -> dict | None:
    merged: dict = {}
    if metadata:
        merged.update(metadata)
    if changed_fields is not None:
        merged["changed_fields"] = list(changed_fields)
    return merged or None


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
        metadata: dict | None = None,
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
        metadata: dict | None = None,
    ) -> None:
        logger.info(
            "Document audit event (not persisted)",
            extra={
                "audit_action": action,
                "audit_outcome": outcome,
                "audit_reason": reason_code,
                "audit_changed_fields": changed_fields,
                "audit_metadata_keys": list((metadata or {}).keys()),
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
        metadata: dict | None = None,
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
                "metadata": dict(metadata) if metadata else {},
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
        metadata: dict | None = None,
    ) -> None:
        raise RuntimeError("Audit backend unavailable")


class DurableAuditHook:
    """Persists events to the audit hash chain.

    SUCCESS events use the request session (atomic with the protected write).
    DENIED events use a separate committed session so request rollbacks do not
    erase the denial. If a DENIED independent write fails, the denial response
    is still returned and the failure is logged (event not claimed persisted).
    SUCCESS write failures raise so fail-closed callers can abort.
    """

    def __init__(self, session: Session | None = None) -> None:
        self._session = session

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
        metadata: dict | None = None,
    ) -> None:
        merged = _merge_metadata(changed_fields=changed_fields, metadata=metadata)
        try:
            if outcome == "DENIED":
                append_audit_event_committed(
                    action=action,
                    outcome=outcome,
                    actor_id=actor_id,
                    document_id=document_id,
                    target_user_id=target_user_id,
                    reason_code=reason_code,
                    request_id=request_id,
                    metadata=merged,
                )
                return

            if self._session is None:
                append_audit_event_committed(
                    action=action,
                    outcome=outcome,
                    actor_id=actor_id,
                    document_id=document_id,
                    target_user_id=target_user_id,
                    reason_code=reason_code,
                    request_id=request_id,
                    metadata=merged,
                )
                return

            append_audit_event(
                self._session,
                action=action,
                outcome=outcome,
                actor_id=actor_id,
                document_id=document_id,
                target_user_id=target_user_id,
                reason_code=reason_code,
                request_id=request_id,
                metadata=merged,
            )
        except AuditTrailError:
            logger.exception(
                "Audit trail write failed",
                extra={
                    "audit_action": action,
                    "audit_outcome": outcome,
                    "audit_persisted": False,
                },
            )
            if outcome == "DENIED":
                return
            raise
        except Exception:
            logger.exception(
                "Audit trail write failed",
                extra={
                    "audit_action": action,
                    "audit_outcome": outcome,
                    "audit_persisted": False,
                },
            )
            if outcome == "DENIED":
                return
            raise
