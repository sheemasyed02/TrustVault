"""FastAPI dependencies that enforce centralized document authorization.

Future document routes should depend on these helpers before returning
metadata, streaming downloads, mutating metadata, sharing, or deleting.

Example:

    @router.get("/documents/{document_id}")
    def get_document(
        document: Document = Depends(require_readable_document),
    ):
        ...
"""

from __future__ import annotations

import uuid

from fastapi import Depends, HTTPException, Path
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.models import Document, User
from app.db.session import get_db
from app.services.document_authorization import (
    DocumentAuthorizationError,
    require_document_delete,
    require_document_edit,
    require_document_owner,
    require_document_read,
)


def _as_http_error(exc: DocumentAuthorizationError) -> HTTPException:
    # Denial responses must not include titles, owners, or storage keys.
    return HTTPException(status_code=exc.status_code, detail=exc.detail)


def require_readable_document(
    document_id: uuid.UUID = Path(...),
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> Document:
    """Authenticate, then require read/download access for this document."""
    try:
        return require_document_read(
            session,
            user=current_user,
            document_id=document_id,
        )
    except DocumentAuthorizationError as exc:
        raise _as_http_error(exc) from None


def require_editable_document(
    document_id: uuid.UUID = Path(...),
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> Document:
    """Authenticate, then require metadata-edit access for this document."""
    try:
        return require_document_edit(
            session,
            user=current_user,
            document_id=document_id,
        )
    except DocumentAuthorizationError as exc:
        raise _as_http_error(exc) from None


def require_owned_document(
    document_id: uuid.UUID = Path(...),
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> Document:
    """Authenticate, then require ownership (share/revoke)."""
    try:
        return require_document_owner(
            session,
            user=current_user,
            document_id=document_id,
        )
    except DocumentAuthorizationError as exc:
        raise _as_http_error(exc) from None


def require_deletable_document(
    document_id: uuid.UUID = Path(...),
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> Document:
    """Authenticate, then require owner-only delete policy."""
    try:
        return require_document_delete(
            session,
            user=current_user,
            document_id=document_id,
        )
    except DocumentAuthorizationError as exc:
        raise _as_http_error(exc) from None
