"""Candidate CRUD APIs (Phase 1)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import List, Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from auth.deps import get_current_user, get_db, require_writer
from db.models import Candidate, User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/candidates", tags=["candidates"])

CandidateSource = Literal["manual", "upload", "ats"]


class CandidateCreate(BaseModel):
    full_name: str = Field(..., min_length=2, max_length=255)
    email: Optional[EmailStr] = None
    phone: Optional[str] = Field(None, max_length=50)
    cv_text: Optional[str] = None
    notes: Optional[str] = None
    source: CandidateSource = "manual"

    @field_validator("full_name")
    @classmethod
    def strip_name(cls, v: str) -> str:
        return v.strip()

    @field_validator("email")
    @classmethod
    def email_lower(cls, v: Optional[str]) -> Optional[str]:
        return v.lower().strip() if v else v

    @field_validator("source")
    @classmethod
    def no_ats_via_manual_create(cls, v: str) -> str:
        if v == "ats":
            raise ValueError("Use ATS import API to create candidates with source=ats")
        return v


class CandidateUpdate(BaseModel):
    full_name: Optional[str] = Field(None, min_length=2, max_length=255)
    email: Optional[EmailStr] = None
    phone: Optional[str] = Field(None, max_length=50)
    cv_text: Optional[str] = None
    notes: Optional[str] = None
    is_active: Optional[bool] = None

    @field_validator("full_name")
    @classmethod
    def strip_name(cls, v: Optional[str]) -> Optional[str]:
        return v.strip() if v else v

    @field_validator("email")
    @classmethod
    def email_lower(cls, v: Optional[str]) -> Optional[str]:
        return v.lower().strip() if v else v


class CandidateOut(BaseModel):
    id: UUID
    organization_id: UUID
    created_by: UUID
    full_name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    cv_text: Optional[str] = None
    notes: Optional[str] = None
    source: str
    external_ats_id: Optional[str] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


def _get_org_candidate(
    db: Session, user: User, candidate_id: UUID
) -> Candidate:
    row = db.get(Candidate, candidate_id)
    if (
        row is None
        or row.organization_id != user.organization_id
        or row.deleted_at is not None
    ):
        raise HTTPException(status_code=404, detail="Candidate not found")
    return row


@router.get("", response_model=List[CandidateOut])
def list_candidates(
    q: Optional[str] = Query(None, description="Search name or email"),
    source: Optional[CandidateSource] = None,
    mine_only: bool = Query(
        False, description="If true, only candidates created by current user"
    ),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    stmt = select(Candidate).where(
        Candidate.organization_id == user.organization_id,
        Candidate.deleted_at.is_(None),
        Candidate.is_active.is_(True),
    )
    if mine_only:
        stmt = stmt.where(Candidate.created_by == user.id)
    if source:
        stmt = stmt.where(Candidate.source == source)
    if q and q.strip():
        term = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(Candidate.full_name.ilike(term), Candidate.email.ilike(term))
        )
    stmt = stmt.order_by(Candidate.created_at.desc())
    rows = db.scalars(stmt).all()
    return [CandidateOut.model_validate(r) for r in rows]


@router.post("", response_model=CandidateOut, status_code=status.HTTP_201_CREATED)
def create_candidate(
    body: CandidateCreate,
    user: User = Depends(require_writer),
    db: Session = Depends(get_db),
):
    row = Candidate(
        organization_id=user.organization_id,
        created_by=user.id,
        full_name=body.full_name,
        email=body.email,
        phone=body.phone,
        cv_text=body.cv_text,
        notes=body.notes,
        source=body.source,
        external_ats_id=None,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    logger.info("[candidates] created id=%s by=%s", row.id, user.email)
    return CandidateOut.model_validate(row)


@router.get("/{candidate_id}", response_model=CandidateOut)
def get_candidate(
    candidate_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return CandidateOut.model_validate(_get_org_candidate(db, user, candidate_id))


@router.patch("/{candidate_id}", response_model=CandidateOut)
def update_candidate(
    candidate_id: UUID,
    body: CandidateUpdate,
    user: User = Depends(require_writer),
    db: Session = Depends(get_db),
):
    row = _get_org_candidate(db, user, candidate_id)
    data = body.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(row, key, value)
    db.commit()
    db.refresh(row)
    return CandidateOut.model_validate(row)


@router.delete("/{candidate_id}", response_model=CandidateOut)
def delete_candidate(
    candidate_id: UUID,
    user: User = Depends(require_writer),
    db: Session = Depends(get_db),
):
    row = _get_org_candidate(db, user, candidate_id)
    row.deleted_at = datetime.now(timezone.utc)
    row.is_active = False
    db.commit()
    db.refresh(row)
    return CandidateOut.model_validate(row)
