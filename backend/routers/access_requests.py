"""Invite-only access requests. Public form does not create a login."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from auth.deps import get_db, require_platform_admin
from auth.provisioning import create_organization_with_admin
from auth.security import (
    client_ip,
    enforce_access_request_rate_limit,
    validate_password_strength,
)
from db.models import AccessRequest, User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/access-requests", tags=["access-requests"])

_SUCCESS_DETAIL = (
    "Thanks. If this request is new, our team will review it and email you if access is granted."
)


class AccessRequestCreate(BaseModel):
    company_name: str = Field(..., min_length=2, max_length=255)
    contact_name: str = Field(..., min_length=2, max_length=255)
    email: EmailStr
    phone: str = Field(..., min_length=7, max_length=40)
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
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Phone is required")
        return cleaned

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
    password: str = Field(..., min_length=8, max_length=128)
    organization_slug: Optional[str] = Field(None, max_length=100)


class GrantAccessResult(BaseModel):
    request: AccessRequestOut
    organization_name: str
    login_email: str


def _phone_ok(phone: str) -> bool:
    return bool(re.fullmatch(r"[0-9+\-()\s]{7,40}", phone))


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

    if not _phone_ok(body.phone):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Enter a valid phone number.",
        )

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
        phone=body.phone,
        message=body.message,
        status="pending",
        ip_address=client_ip(request)[:64],
    )
    db.add(row)
    db.commit()
    logger.info("[access] request queued company=%s email=%s", row.company_name, row.email)
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
    body: GrantAccessRequest,
    admin: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
):
    """Create the customer org + admin login. Platform admin only."""
    row = db.get(AccessRequest, request_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Access request not found")
    if row.status == "granted":
        raise HTTPException(status_code=409, detail="This request was already granted")
    if row.status == "rejected":
        raise HTTPException(status_code=409, detail="This request was rejected")

    validate_password_strength(body.password)
    org, user = create_organization_with_admin(
        db,
        organization_name=row.company_name,
        organization_slug=body.organization_slug,
        full_name=row.contact_name,
        email=row.email,
        password=body.password,
    )
    row.status = "granted"
    row.granted_org_id = org.id
    row.granted_by_user_id = admin.id
    row.granted_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(row)
    logger.info(
        "[access] granted company=%s email=%s by=%s org=%s",
        row.company_name,
        row.email,
        admin.email,
        org.slug,
    )
    return GrantAccessResult(
        request=AccessRequestOut.model_validate(row),
        organization_name=org.name,
        login_email=user.email,
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
