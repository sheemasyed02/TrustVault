"""Durable audit hash-chain writer and verifier.

Concurrency: every append takes PostgreSQL ``pg_advisory_xact_lock`` for a fixed
key inside the writer transaction, then reads the current chain tip and inserts
the next event. Selecting the latest row alone is not enough under concurrency;
the advisory lock serializes tip reads and inserts.

Security boundary: this chain detects many in-place alterations when an attacker
cannot rewrite the whole table consistently. A privileged database administrator
who can UPDATE/DELETE/INSERT freely can rebuild a valid-looking chain. External
anchoring / WORM storage is future work — not implemented here.

Never store passwords, bearer tokens, JWTs, file bytes, or secrets in metadata.
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import Select, func, select, text
from sqlalchemy.orm import Session

from app.db.models import AuditEvent, Document, User
from app.db.session import get_session_factory
from app.schemas.audit import AuditEventResponse, DocumentAuditSummary

logger = logging.getLogger(__name__)

# Fixed 64-bit key for pg_advisory_xact_lock (TrustVault audit chain).
AUDIT_CHAIN_LOCK_KEY = 0x5472757374564175  # "TrustVAu"

FORBIDDEN_METADATA_KEYS = frozenset(
    {
        "password",
        "password_hash",
        "token",
        "access_token",
        "refresh_token",
        "authorization",
        "jwt",
        "secret",
        "api_key",
        "file_bytes",
        "content",
        "raw_body",
        "storage_key",
        "credentials",
    }
)


class AuditTrailError(Exception):
    """Raised when an audit event cannot be persisted safely."""

    def __init__(self, message: str, *, reason_code: str) -> None:
        super().__init__(message)
        self.message = message
        self.reason_code = reason_code


@dataclass(frozen=True, slots=True)
class ChainVerificationResult:
    valid: bool
    event_count: int
    checked_count: int
    first_failure_index: int | None
    first_failure_event_id: uuid.UUID | None
    reason_code: str | None
    detail: str


@dataclass(frozen=True, slots=True)
class AuditListResult:
    items: list[AuditEvent]
    page: int
    page_size: int
    total: int
    total_pages: int


def _utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _iso_utc(dt: datetime) -> str:
    return _utc(dt).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _uuid_str(value: uuid.UUID | None) -> str | None:
    return str(value) if value is not None else None


def sanitize_metadata(metadata: dict[str, Any] | None) -> dict[str, Any]:
    """Drop forbidden keys; never accept nested secret-bearing blobs blindly."""
    if not metadata:
        return {}
    clean: dict[str, Any] = {}
    for key, value in metadata.items():
        lowered = str(key).lower()
        if lowered in FORBIDDEN_METADATA_KEYS:
            continue
        if any(part in lowered for part in ("password", "token", "secret", "jwt")):
            continue
        if isinstance(value, (bytes, bytearray)):
            continue
        if isinstance(value, dict):
            clean[key] = sanitize_metadata(value)
        elif isinstance(value, list):
            clean[key] = [
                sanitize_metadata(item) if isinstance(item, dict) else item
                for item in value
                if not isinstance(item, (bytes, bytearray))
            ]
        else:
            clean[key] = value
    return clean


def canonical_event_payload(
    *,
    event_id: uuid.UUID,
    created_at: datetime,
    actor_id: uuid.UUID | None,
    action: str,
    document_id: uuid.UUID | None,
    target_user_id: uuid.UUID | None,
    outcome: str,
    reason_code: str | None,
    request_id: str | None,
    metadata: dict[str, Any],
    previous_hash: str | None,
) -> str:
    """Deterministic JSON used as the SHA-256 preimage."""
    payload = {
        "id": str(event_id),
        "created_at": _iso_utc(created_at),
        "actor_id": _uuid_str(actor_id),
        "action": action,
        "document_id": _uuid_str(document_id),
        "target_user_id": _uuid_str(target_user_id),
        "outcome": outcome,
        "reason_code": reason_code,
        "request_id": request_id,
        "metadata": metadata,
        "previous_hash": previous_hash,
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def compute_event_hash(
    *,
    event_id: uuid.UUID,
    created_at: datetime,
    actor_id: uuid.UUID | None,
    action: str,
    document_id: uuid.UUID | None,
    target_user_id: uuid.UUID | None,
    outcome: str,
    reason_code: str | None,
    request_id: str | None,
    metadata: dict[str, Any],
    previous_hash: str | None,
) -> str:
    canonical = canonical_event_payload(
        event_id=event_id,
        created_at=created_at,
        actor_id=actor_id,
        action=action,
        document_id=document_id,
        target_user_id=target_user_id,
        outcome=outcome,
        reason_code=reason_code,
        request_id=request_id,
        metadata=metadata,
        previous_hash=previous_hash,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _lock_chain(session: Session) -> None:
    session.execute(
        text("SELECT pg_advisory_xact_lock(:key)"),
        {"key": AUDIT_CHAIN_LOCK_KEY},
    )


def _latest_event(session: Session) -> AuditEvent | None:
    return session.scalar(
        select(AuditEvent)
        .order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
        .limit(1)
    )


def append_audit_event(
    session: Session,
    *,
    action: str,
    outcome: str,
    actor_id: uuid.UUID | None = None,
    document_id: uuid.UUID | None = None,
    target_user_id: uuid.UUID | None = None,
    reason_code: str | None = None,
    request_id: str | None = None,
    metadata: dict[str, Any] | None = None,
    event_id: uuid.UUID | None = None,
    created_at: datetime | None = None,
) -> AuditEvent:
    """Append one event under the advisory lock using the caller's transaction.

    The caller controls commit/rollback. Prefer this for SUCCESS events that must
    commit atomically with the protected operation (fail-closed).
    """
    if outcome not in {"SUCCESS", "DENIED"}:
        raise AuditTrailError(
            "Invalid audit outcome",
            reason_code="INVALID_OUTCOME",
        )
    if not action or len(action) > 128:
        raise AuditTrailError(
            "Invalid audit action",
            reason_code="INVALID_ACTION",
        )

    safe_metadata = sanitize_metadata(metadata)
    eid = event_id or uuid.uuid4()

    _lock_chain(session)
    tip = _latest_event(session)
    previous_hash = tip.event_hash if tip is not None else None
    # Timestamps must be strictly increasing with chain order. Concurrent
    # writers can otherwise share the same created_at; ordering by id then
    # disagrees with previous_hash links (UUIDv4 is not insertion-ordered).
    ts = _utc(created_at or datetime.now(timezone.utc))
    if tip is not None:
        tip_ts = _utc(tip.created_at)
        if ts <= tip_ts:
            ts = tip_ts + timedelta(microseconds=1)
    event_hash = compute_event_hash(
        event_id=eid,
        created_at=ts,
        actor_id=actor_id,
        action=action,
        document_id=document_id,
        target_user_id=target_user_id,
        outcome=outcome,
        reason_code=reason_code,
        request_id=request_id,
        metadata=safe_metadata,
        previous_hash=previous_hash,
    )

    event = AuditEvent(
        id=eid,
        actor_id=actor_id,
        action=action,
        document_id=document_id,
        target_user_id=target_user_id,
        outcome=outcome,
        reason_code=reason_code,
        request_id=request_id,
        created_at=ts,
        metadata_json=safe_metadata,
        previous_hash=previous_hash,
        event_hash=event_hash,
    )
    session.add(event)
    session.flush()
    return event


def append_audit_event_committed(
    *,
    action: str,
    outcome: str,
    actor_id: uuid.UUID | None = None,
    document_id: uuid.UUID | None = None,
    target_user_id: uuid.UUID | None = None,
    reason_code: str | None = None,
    request_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> AuditEvent:
    """Persist an event in its own committed transaction.

    Used for DENIED events so a later rollback of the request session cannot
    erase the denial record. If this write fails, callers must not claim the
    event was persisted; the original denial response should still be returned.
    """
    session = get_session_factory()()
    try:
        event = append_audit_event(
            session,
            action=action,
            outcome=outcome,
            actor_id=actor_id,
            document_id=document_id,
            target_user_id=target_user_id,
            reason_code=reason_code,
            request_id=request_id,
            metadata=metadata,
        )
        session.commit()
        session.refresh(event)
        return event
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def try_append_audit_event_committed(
    *,
    action: str,
    outcome: str,
    actor_id: uuid.UUID | None = None,
    document_id: uuid.UUID | None = None,
    target_user_id: uuid.UUID | None = None,
    reason_code: str | None = None,
    request_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> AuditEvent | None:
    """Best-effort independent append using ``pg_try_advisory_xact_lock``.

    Returns ``None`` when the chain lock is busy or the write fails. Callers
    must not claim persistence and must still enforce the security decision.
    """
    session = get_session_factory()()
    try:
        got = session.execute(
            text("SELECT pg_try_advisory_xact_lock(:key)"),
            {"key": AUDIT_CHAIN_LOCK_KEY},
        ).scalar()
        if not got:
            logger.warning(
                "Skipped audit append; chain lock busy",
                extra={"audit_action": action, "audit_persisted": False},
            )
            return None

        # Lock held for this transaction; append without taking the lock again.
        safe_metadata = sanitize_metadata(metadata)
        eid = uuid.uuid4()
        tip = _latest_event(session)
        previous_hash = tip.event_hash if tip is not None else None
        ts = _utc(datetime.now(timezone.utc))
        if tip is not None:
            tip_ts = _utc(tip.created_at)
            if ts <= tip_ts:
                ts = tip_ts + timedelta(microseconds=1)
        event_hash = compute_event_hash(
            event_id=eid,
            created_at=ts,
            actor_id=actor_id,
            action=action,
            document_id=document_id,
            target_user_id=target_user_id,
            outcome=outcome,
            reason_code=reason_code,
            request_id=request_id,
            metadata=safe_metadata,
            previous_hash=previous_hash,
        )
        event = AuditEvent(
            id=eid,
            actor_id=actor_id,
            action=action,
            document_id=document_id,
            target_user_id=target_user_id,
            outcome=outcome,
            reason_code=reason_code,
            request_id=request_id,
            created_at=ts,
            metadata_json=safe_metadata,
            previous_hash=previous_hash,
            event_hash=event_hash,
        )
        session.add(event)
        session.commit()
        session.refresh(event)
        return event
    except Exception:
        session.rollback()
        logger.exception(
            "Best-effort audit append failed",
            extra={"audit_action": action, "audit_persisted": False},
        )
        return None
    finally:
        session.close()


def verify_audit_chain(session: Session) -> ChainVerificationResult:
    """Recalculate hashes and check previous_hash links in created_at/id order.

    Empty chain is valid. Truncation of the *tail* (deleting the newest events
    without leaving a broken link) is not detectable without an external chain
    head anchor — this verifier only validates the remaining contiguous chain.
    """
    events = list(
        session.scalars(
            select(AuditEvent).order_by(AuditEvent.created_at.asc(), AuditEvent.id.asc())
        ).all()
    )
    if not events:
        return ChainVerificationResult(
            valid=True,
            event_count=0,
            checked_count=0,
            first_failure_index=None,
            first_failure_event_id=None,
            reason_code="EMPTY_CHAIN",
            detail="Audit chain is empty",
        )

    expected_previous: str | None = None
    for index, event in enumerate(events):
        if event.previous_hash != expected_previous:
            return ChainVerificationResult(
                valid=False,
                event_count=len(events),
                checked_count=index,
                first_failure_index=index,
                first_failure_event_id=event.id,
                reason_code="PREVIOUS_HASH_MISMATCH",
                detail="previous_hash does not match prior event_hash",
            )
        expected = compute_event_hash(
            event_id=event.id,
            created_at=event.created_at,
            actor_id=event.actor_id,
            action=event.action,
            document_id=event.document_id,
            target_user_id=event.target_user_id,
            outcome=event.outcome,
            reason_code=event.reason_code,
            request_id=event.request_id,
            metadata=dict(event.metadata_json or {}),
            previous_hash=event.previous_hash,
        )
        if event.event_hash != expected:
            return ChainVerificationResult(
                valid=False,
                event_count=len(events),
                checked_count=index,
                first_failure_index=index,
                first_failure_event_id=event.id,
                reason_code="EVENT_HASH_MISMATCH",
                detail="Stored event_hash does not match recalculated hash",
            )
        expected_previous = event.event_hash

    return ChainVerificationResult(
        valid=True,
        event_count=len(events),
        checked_count=len(events),
        first_failure_index=None,
        first_failure_event_id=None,
        reason_code=None,
        detail="Audit chain integrity verified",
    )


def _apply_audit_filters(
    stmt: Select[tuple[AuditEvent]],
    *,
    actor_id: uuid.UUID | None,
    exclude_actor_id: uuid.UUID | None,
    action: str | None,
    document_id: uuid.UUID | None,
    owner_id: uuid.UUID | None,
    outcome: str | None,
    created_from: datetime | None,
    created_to: datetime | None,
) -> Select[tuple[AuditEvent]]:
    from sqlalchemy import or_

    if actor_id is not None:
        stmt = stmt.where(AuditEvent.actor_id == actor_id)
    if exclude_actor_id is not None:
        stmt = stmt.where(
            or_(
                AuditEvent.actor_id.is_(None),
                AuditEvent.actor_id != exclude_actor_id,
            )
        )
    if action is not None:
        stmt = stmt.where(AuditEvent.action == action)
    if document_id is not None:
        stmt = stmt.where(AuditEvent.document_id == document_id)
    if owner_id is not None:
        # Join document metadata only — never loads file bytes or storage keys.
        stmt = stmt.join(
            Document,
            Document.id == AuditEvent.document_id,
        ).where(Document.owner_id == owner_id)
    if outcome is not None:
        stmt = stmt.where(AuditEvent.outcome == outcome)
    if created_from is not None:
        stmt = stmt.where(AuditEvent.created_at >= _utc(created_from))
    if created_to is not None:
        stmt = stmt.where(AuditEvent.created_at <= _utc(created_to))
    return stmt


def list_audit_events(
    session: Session,
    *,
    page: int = 1,
    page_size: int = 50,
    actor_id: uuid.UUID | None = None,
    exclude_actor_id: uuid.UUID | None = None,
    action: str | None = None,
    document_id: uuid.UUID | None = None,
    owner_id: uuid.UUID | None = None,
    outcome: str | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
) -> AuditListResult:
    if page < 1:
        page = 1
    if page_size < 1:
        page_size = 1
    if page_size > 100:
        page_size = 100

    base = select(AuditEvent)
    base = _apply_audit_filters(
        base,
        actor_id=actor_id,
        exclude_actor_id=exclude_actor_id,
        action=action,
        document_id=document_id,
        owner_id=owner_id,
        outcome=outcome,
        created_from=created_from,
        created_to=created_to,
    )
    total = session.scalar(
        select(func.count()).select_from(base.subquery())
    ) or 0
    total_pages = (total + page_size - 1) // page_size if total else 0
    items = list(
        session.scalars(
            base.order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
    )
    return AuditListResult(
        items=items,
        page=page,
        page_size=page_size,
        total=total,
        total_pages=total_pages,
    )


def _count_document_events(
    session: Session,
    *,
    document_id: uuid.UUID,
    action: str | None = None,
    outcome: str | None = None,
) -> int:
    stmt = (
        select(func.count())
        .select_from(AuditEvent)
        .where(AuditEvent.document_id == document_id)
    )
    if action is not None:
        stmt = stmt.where(AuditEvent.action == action)
    if outcome is not None:
        stmt = stmt.where(AuditEvent.outcome == outcome)
    return session.scalar(stmt) or 0


def summarize_document_audit(
    session: Session,
    *,
    document_id: uuid.UUID,
    owner_id: uuid.UUID | None = None,
) -> DocumentAuditSummary:
    """Aggregate counts for the owner document activity dashboard."""
    from app.services.document_view_audit import document_view_stats

    views, distinct, latest = document_view_stats(session, document_id=document_id)
    resolved_owner_id = owner_id
    if resolved_owner_id is None:
        doc = session.get(Document, document_id)
        resolved_owner_id = doc.owner_id if doc is not None else None

    external_views = 0
    external_distinct = 0
    external_latest = None
    owner_self_views = 0
    if resolved_owner_id is not None:
        external_views, external_distinct, external_latest = document_view_stats(
            session,
            document_id=document_id,
            exclude_actor_id=resolved_owner_id,
        )
        owner_self_views = (
            session.scalar(
                select(func.count())
                .select_from(AuditEvent)
                .where(
                    AuditEvent.document_id == document_id,
                    AuditEvent.action == "DOCUMENT_VIEW",
                    AuditEvent.outcome == "SUCCESS",
                    AuditEvent.actor_id == resolved_owner_id,
                )
            )
            or 0
        )

    return DocumentAuditSummary(
        successful_views=views,
        distinct_viewers=distinct,
        latest_view_at=latest,
        external_views=external_views,
        distinct_external_viewers=external_distinct,
        latest_external_view_at=external_latest,
        owner_self_views=owner_self_views,
        successful_downloads=_count_document_events(
            session,
            document_id=document_id,
            action="DOCUMENT_DOWNLOAD",
            outcome="SUCCESS",
        ),
        denied_access_attempts=_count_document_events(
            session,
            document_id=document_id,
            outcome="DENIED",
        ),
        permission_grants=_count_document_events(
            session,
            document_id=document_id,
            action="DOCUMENT_PERMISSION_GRANT",
            outcome="SUCCESS",
        ),
        permission_revocations=_count_document_events(
            session,
            document_id=document_id,
            action="DOCUMENT_PERMISSION_REVOKE",
            outcome="SUCCESS",
        ),
        content_updates=_count_document_events(
            session,
            document_id=document_id,
            action="DOCUMENT_CONTENT_UPDATE",
            outcome="SUCCESS",
        ),
        metadata_updates=_count_document_events(
            session,
            document_id=document_id,
            action="DOCUMENT_METADATA_UPDATE",
            outcome="SUCCESS",
        ),
        uploads=_count_document_events(
            session,
            document_id=document_id,
            action="DOCUMENT_UPLOAD",
            outcome="SUCCESS",
        ),
        deletions=_count_document_events(
            session,
            document_id=document_id,
            action="DOCUMENT_DELETE",
            outcome="SUCCESS",
        ),
    )


def enrich_audit_event_responses(
    session: Session,
    events: list[AuditEvent],
) -> list[AuditEventResponse]:
    """Attach safe actor/target/document display fields when those rows still exist."""
    user_ids: set[uuid.UUID] = set()
    document_ids: set[uuid.UUID] = set()
    for event in events:
        if event.actor_id is not None:
            user_ids.add(event.actor_id)
        if event.target_user_id is not None:
            user_ids.add(event.target_user_id)
        if event.document_id is not None:
            document_ids.add(event.document_id)

    users_by_id: dict[uuid.UUID, User] = {}
    if user_ids:
        users_by_id = {
            user.id: user
            for user in session.scalars(
                select(User).where(User.id.in_(user_ids))
            ).all()
        }

    docs_by_id: dict[uuid.UUID, Document] = {}
    owner_ids: set[uuid.UUID] = set()
    if document_ids:
        docs_by_id = {
            doc.id: doc
            for doc in session.scalars(
                select(Document).where(Document.id.in_(document_ids))
            ).all()
        }
        owner_ids = {doc.owner_id for doc in docs_by_id.values()}
        missing_owners = owner_ids - set(users_by_id)
        if missing_owners:
            for owner in session.scalars(
                select(User).where(User.id.in_(missing_owners))
            ).all():
                users_by_id[owner.id] = owner

    results: list[AuditEventResponse] = []
    for event in events:
        actor = users_by_id.get(event.actor_id) if event.actor_id else None
        target = (
            users_by_id.get(event.target_user_id) if event.target_user_id else None
        )
        doc = docs_by_id.get(event.document_id) if event.document_id else None
        owner = users_by_id.get(doc.owner_id) if doc is not None else None
        is_self = bool(
            doc is not None
            and event.actor_id is not None
            and event.actor_id == doc.owner_id
            and event.action == "DOCUMENT_VIEW"
        )
        results.append(
            AuditEventResponse(
                id=event.id,
                created_at=event.created_at,
                actor_id=event.actor_id,
                actor_name=actor.name if actor else None,
                actor_email=actor.email if actor else None,
                action=event.action,
                document_id=event.document_id,
                document_title=doc.title if doc else None,
                document_owner_id=doc.owner_id if doc else None,
                document_owner_name=owner.name if owner else None,
                document_owner_email=owner.email if owner else None,
                is_owner_self_view=is_self,
                target_user_id=event.target_user_id,
                target_user_name=target.name if target else None,
                target_user_email=target.email if target else None,
                outcome=event.outcome,
                reason_code=event.reason_code,
                request_id=event.request_id,
                metadata=dict(event.metadata_json or {}),
                previous_hash=event.previous_hash,
                event_hash=event.event_hash,
            )
        )
    return results
