"""Invite-only access requests. Public form does not create a login."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID

from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from auth.deps import get_db, require_platform_admin
from auth.password_setup import issue_invite_token, public_frontend_origin
from auth.provisioning import create_organization_with_admin
from auth.security import (
    client_ip,
    enforce_access_request_rate_limit,
)
from db.models import AccessRequest, User
from services.graph_mail import notify_access_granted, notify_access_request
from services.phone import validate_e164_phone

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/access-requests", tags=["access-requests"])

_SUCCESS_DETAIL = (
    "Thanks. If this request is new, our team will review it and email you if access is granted."
)


class AccessRequestCreate(BaseModel):
    company_name: str = Field(..., min_length=2, max_length=255)
    contact_name: str = Field(..., min_length=2, max_length=255)
    email: EmailStr
    phone: str = Field(..., min_length=1, max_length=20)
    message: Optional[str] = Field(None, max_length=2000)
    # Honeypot — real users leave this empty. Bots that fill it get a fake success.
    website: Optional[str] = Field(None, max_length=200)

    @field_validator("email")
    @classmethod
    def email_lower(cls, v: str) -> str:
        return v.lower().strip()

    @field_validator("company_name", "contact_name")
    @classmethod
    def strip_text(cls, v: str) -> str:
        return v.strip()

    @field_validator("phone")
    @classmethod
    def strip_phone(cls, v: str) -> str:
        return v.strip()

    @field_validator("message")
    @classmethod
    def strip_message(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        cleaned = v.strip()
        return cleaned or None


class AccessRequestOut(BaseModel):
    id: UUID
    company_name: str
    contact_name: str
    email: str
    phone: Optional[str] = None
    message: Optional[str] = None
    status: str
    granted_org_id: Optional[UUID] = None
    granted_at: Optional[datetime] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class AccessRequestPublicResult(BaseModel):
    ok: bool = True
    message: str


class GrantAccessRequest(BaseModel):
    organization_slug: Optional[str] = Field(None, max_length=100)


class GrantAccessResult(BaseModel):
    request: AccessRequestOut
    organization_name: str
    login_email: str
    invite_email_sent: bool


def _invite_url(raw: str) -> str | None:
    origin = public_frontend_origin()
    if not origin:
        return None
    return f"{origin}/set-password?token={quote(raw, safe='')}"


def _mail_invite(user: User, raw: str) -> bool:
    url = _invite_url(raw)
    if not url:
        logger.warning("[access] invite not mailed — FRONTEND_BASE_URL / CORS_ORIGINS empty")
        return False
    return notify_access_granted(
        contact_name=user.full_name,
        email=user.email,
        setup_url=url,
    )


@router.post("", response_model=AccessRequestPublicResult, status_code=status.HTTP_200_OK)
def submit_access_request(
    body: AccessRequestCreate,
    request: Request,
    db: Session = Depends(get_db),
):
    """Public lead form. Never creates a user or organization."""
    if (body.website or "").strip():
        logger.info("[access] honeypot tripped ip=%s", client_ip(request))
        return AccessRequestPublicResult(message=_SUCCESS_DETAIL)

    try:
        phone = validate_e164_phone(body.phone)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    enforce_access_request_rate_limit(request, body.email)

    existing_user = db.scalar(select(User).where(User.email == body.email))
    pending = db.scalar(
        select(AccessRequest).where(
            AccessRequest.email == body.email,
            AccessRequest.status == "pending",
        )
    )
    if existing_user is not None or pending is not None:
        return AccessRequestPublicResult(message=_SUCCESS_DETAIL)

    row = AccessRequest(
        company_name=body.company_name,
        contact_name=body.contact_name,
        email=body.email,
        phone=phone,
        message=body.message,
        status="pending",
        ip_address=client_ip(request)[:64],
    )
    db.add(row)
    db.commit()
    logger.info("[access] request queued company=%s email=%s", row.company_name, row.email)
    notify_access_request(
        company_name=row.company_name,
        contact_name=row.contact_name,
        email=row.email,
        phone=row.phone,
        message=row.message,
    )
    return AccessRequestPublicResult(message=_SUCCESS_DETAIL)


@router.get("", response_model=List[AccessRequestOut])
def list_access_requests(
    admin: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
    status_filter: Optional[str] = None,
):
    del admin
    stmt = select(AccessRequest).order_by(AccessRequest.created_at.desc())
    if status_filter:
        if status_filter not in ("pending", "granted", "rejected"):
            raise HTTPException(status_code=400, detail="Invalid status filter")
        stmt = stmt.where(AccessRequest.status == status_filter)
    rows = db.scalars(stmt).all()
    return [AccessRequestOut.model_validate(r) for r in rows]


@router.post("/{request_id}/grant", response_model=GrantAccessResult)
def grant_access(
    request_id: UUID,
    admin: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
    body: Optional[GrantAccessRequest] = None,
):
    """Create the company + org admin. Applicant sets their own password via email link."""
    row = db.get(AccessRequest, request_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Access request not found")
    if row.status == "granted":
        raise HTTPException(status_code=409, detail="This request was already granted")
    if row.status == "rejected":
        raise HTTPException(status_code=409, detail="This request was rejected")

    org, user = create_organization_with_admin(
        db,
        organization_name=row.company_name,
        organization_slug=body.organization_slug if body else None,
        full_name=row.contact_name,
        email=row.email,
        password=None,
    )
    row.status = "granted"
    row.granted_org_id = org.id
    row.granted_by_user_id = admin.id
    row.granted_at = datetime.now(timezone.utc)
    raw = issue_invite_token(db, user.id)
    db.commit()
    db.refresh(row)
    sent = _mail_invite(user, raw)
    logger.info(
        "[access] granted company=%s email=%s by=%s org=%s invite_sent=%s",
        row.company_name,
        row.email,
        admin.email,
        org.slug,
        sent,
    )
    return GrantAccessResult(
        request=AccessRequestOut.model_validate(row),
        organization_name=org.name,
        login_email=user.email,
        invite_email_sent=sent,
    )


@router.post("/{request_id}/resend-invite", response_model=GrantAccessResult)
def resend_invite(
    request_id: UUID,
    admin: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
):
    """Issue a new set-password link. Invalidates unused previous links."""
    del admin
    row = db.get(AccessRequest, request_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Access request not found")
    if row.status != "granted":
        raise HTTPException(status_code=409, detail="Only granted requests can be resent")
    user = db.scalar(select(User).where(User.email == row.email))
    if user is None or not user.is_active:
        raise HTTPException(status_code=409, detail="Granted user was not found")
    raw = issue_invite_token(db, user.id)
    db.commit()
    sent = _mail_invite(user, raw)
    if not sent:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not send the invite email. Check Graph mail settings and try again.",
        )
    org = user.organization
    return GrantAccessResult(
        request=AccessRequestOut.model_validate(row),
        organization_name=org.name if org else row.company_name,
        login_email=user.email,
        invite_email_sent=True,
    )


@router.post("/{request_id}/reject", response_model=AccessRequestOut)
def reject_access(
    request_id: UUID,
    admin: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
):
    row = db.get(AccessRequest, request_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Access request not found")
    if row.status != "pending":
        raise HTTPException(status_code=409, detail="Only pending requests can be rejected")
    row.status = "rejected"
    row.granted_by_user_id = admin.id
    db.commit()
    db.refresh(row)
    logger.info("[access] rejected company=%s email=%s by=%s", row.company_name, row.email, admin.email)
    return AccessRequestOut.model_validate(row)
