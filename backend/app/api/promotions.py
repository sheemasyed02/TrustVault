"""Owner-promotion request HTTP routes."""

from __future__ import annotations

import logging
import math
import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, Path, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_admin
from app.db.models import User
from app.db.session import get_db
from app.schemas.promotion import (
    PromotionListResponse,
    PromotionRequestResponse,
    PromotionRequesterSummary,
    PromotionReviewRequest,
    PromotionSubmitRequest,
)
from app.services.audit_trail import append_audit_event, append_audit_event_committed
from app.services.promotion_service import (
    PromotionError,
    list_my_promotion_requests,
    list_promotion_requests_admin,
    review_promotion_request,
    submit_promotion_request,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["promotions"])


def _to_response(req) -> PromotionRequestResponse:
    requester = None
    if getattr(req, "requester", None) is not None:
        requester = PromotionRequesterSummary.model_validate(req.requester)
    return PromotionRequestResponse(
        id=req.id,
        requester_id=req.requester_id,
        status=req.status,
        justification=req.justification,
        admin_note=req.admin_note,
        reviewed_by=req.reviewed_by,
        created_at=req.created_at,
        reviewed_at=req.reviewed_at,
        requester=requester,
    )


@router.post(
    "/promotions/requests",
    response_model=PromotionRequestResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_promotion_request(
    body: PromotionSubmitRequest,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
    x_request_id: str | None = Header(default=None, alias="X-Request-ID"),
) -> PromotionRequestResponse:
    """VIEWER submits a request to become OWNER. Existing grants are unchanged on approval."""
    request_id = (x_request_id or str(uuid.uuid4())).strip() or str(uuid.uuid4())
    try:
        req = submit_promotion_request(
            session,
            actor=current_user,
            justification=body.justification,
        )
    except PromotionError as exc:
        try:
            append_audit_event_committed(
                action="OWNER_PROMOTION_REQUEST",
                outcome="DENIED",
                actor_id=current_user.id,
                reason_code=exc.reason_code,
                request_id=request_id,
            )
        except Exception:
            logger.exception("Failed to audit promotion denial")
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from None

    try:
        append_audit_event(
            session,
            action="OWNER_PROMOTION_REQUEST",
            outcome="SUCCESS",
            actor_id=current_user.id,
            request_id=request_id,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Request could not be audited",
        ) from exc

    return _to_response(req)


@router.get("/promotions/requests/me", response_model=list[PromotionRequestResponse])
def my_promotion_requests(
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> list[PromotionRequestResponse]:
    """List the caller's own promotion requests."""
    items = list_my_promotion_requests(session, actor=current_user)
    return [_to_response(item) for item in items]


@router.get("/admin/promotions", response_model=PromotionListResponse)
def admin_list_promotions(
    status_filter: str | None = Query(default=None, alias="status"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    current_user: User = Depends(require_admin),
    session: Session = Depends(get_db),
) -> PromotionListResponse:
    """ADMIN lists owner-promotion requests."""
    del current_user
    try:
        result = list_promotion_requests_admin(
            session,
            status_filter=status_filter,
            page=page,
            page_size=page_size,
        )
    except PromotionError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from None

    return PromotionListResponse(
        results=[_to_response(item) for item in result.items],
        page=result.page,
        page_size=result.page_size,
        total=result.total,
        total_pages=result.total_pages
        if result.total_pages
        else (math.ceil(result.total / page_size) if result.total else 0),
    )


@router.post(
    "/admin/promotions/{request_id}/review",
    response_model=PromotionRequestResponse,
)
def admin_review_promotion(
    body: PromotionReviewRequest,
    request_id: uuid.UUID = Path(...),
    current_user: User = Depends(require_admin),
    session: Session = Depends(get_db),
    x_request_id: str | None = Header(default=None, alias="X-Request-ID"),
) -> PromotionRequestResponse:
    """ADMIN approves or rejects a pending owner-promotion request."""
    audit_request_id = (x_request_id or str(uuid.uuid4())).strip() or str(uuid.uuid4())
    try:
        req = review_promotion_request(
            session,
            admin=current_user,
            request_id=request_id,
            decision=body.decision.upper(),
            admin_note=body.admin_note,
        )
    except PromotionError as exc:
        try:
            append_audit_event_committed(
                action="OWNER_PROMOTION_REVIEW",
                outcome="DENIED",
                actor_id=current_user.id,
                reason_code=exc.reason_code,
                request_id=audit_request_id,
                metadata={"promotion_request_id": str(request_id)},
            )
        except Exception:
            logger.exception("Failed to audit promotion review denial")
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from None

    try:
        append_audit_event(
            session,
            action="OWNER_PROMOTION_REVIEW",
            outcome="SUCCESS",
            actor_id=current_user.id,
            target_user_id=req.requester_id,
            request_id=audit_request_id,
            metadata={
                "promotion_request_id": str(req.id),
                "decision": req.status,
            },
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Review could not be audited",
        ) from exc

    return _to_response(req)
