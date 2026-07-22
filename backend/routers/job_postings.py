"""Job posting CRUD APIs (Phase 1)."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import List, Literal, Optional, Tuple
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from auth.deps import get_current_user, get_db, require_writer
from db.models import JobPosting, User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/job-postings", tags=["job-postings"])

JobSource = Literal["manual", "upload", "ats"]
JobStatus = Literal["draft", "open", "closed", "filled"]

_TITLE_SUFFIX_RE = re.compile(r"^(.*?)\s+(\d{3})$")


def _normalize_jd(text: Optional[str]) -> str:
    if not text:
        return ""
    return " ".join(text.lower().split())


def _root_title(title: str) -> str:
    raw = (title or "").strip()
    match = _TITLE_SUFFIX_RE.match(raw)
    return match.group(1).strip() if match else raw


def _find_reuse_or_allocate_title(
    db: Session,
    *,
    organization_id: UUID,
    desired_title: str,
    jd_text: Optional[str],
) -> Tuple[Optional[JobPosting], str]:
    """Reuse when title root + JD text match; else allocate AI Engineer / AI Engineer 001…"""
    root = _root_title(desired_title)
    if not root:
        return None, desired_title.strip()

    stmt = select(JobPosting).where(
        JobPosting.organization_id == organization_id,
        JobPosting.deleted_at.is_(None),
        JobPosting.is_active.is_(True),
        JobPosting.job_title.ilike(f"{root}%"),
    )
    siblings = [
        row
        for row in db.scalars(stmt).all()
        if _root_title(row.job_title).casefold() == root.casefold()
    ]

    target_jd = _normalize_jd(jd_text)
    for row in siblings:
        if _normalize_jd(row.jd_text) == target_jd:
            return row, row.job_title

    taken = {row.job_title.casefold() for row in siblings}
    if root.casefold() not in taken:
        return None, root

    n = 1
    while f"{root} {n:03d}".casefold() in taken:
        n += 1
        if n > 999:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Too many job postings with this title",
            )
    return None, f"{root} {n:03d}"


class JobPostingCreate(BaseModel):
    job_title: str = Field(..., min_length=2, max_length=255)
    jd_text: Optional[str] = None
    description: Optional[str] = None
    status: JobStatus = "open"
    source: JobSource = "manual"

    @field_validator("job_title")
    @classmethod
    def strip_title(cls, v: str) -> str:
        return v.strip()

    @field_validator("jd_text")
    @classmethod
    def jd_min_len(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        text = v.strip()
        if text and len(text) < 100:
            raise ValueError("jd_text must be at least 100 characters when provided")
        return text or None

    @field_validator("source")
    @classmethod
    def no_ats_via_manual_create(cls, v: str) -> str:
        if v == "ats":
            raise ValueError("Use ATS import API to create jobs with source=ats")
        return v


class JobPostingUpdate(BaseModel):
    job_title: Optional[str] = Field(None, min_length=2, max_length=255)
    jd_text: Optional[str] = None
    description: Optional[str] = None
    status: Optional[JobStatus] = None
    is_active: Optional[bool] = None

    @field_validator("job_title")
    @classmethod
    def strip_title(cls, v: Optional[str]) -> Optional[str]:
        return v.strip() if v else v

    @field_validator("jd_text")
    @classmethod
    def jd_min_len(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        text = v.strip()
        if text and len(text) < 100:
            raise ValueError("jd_text must be at least 100 characters when provided")
        return text or None


class JobPostingOut(BaseModel):
    id: UUID
    organization_id: UUID
    created_by: UUID
    job_title: str
    jd_text: Optional[str] = None
    description: Optional[str] = None
    status: str
    source: str
    external_ats_id: Optional[str] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


def _get_org_job(db: Session, user: User, job_id: UUID) -> JobPosting:
    row = db.get(JobPosting, job_id)
    if (
        row is None
        or row.organization_id != user.organization_id
        or row.deleted_at is not None
    ):
        raise HTTPException(status_code=404, detail="Job posting not found")
    return row


@router.get("", response_model=List[JobPostingOut])
def list_job_postings(
    q: Optional[str] = Query(None, description="Search job title"),
    status_filter: Optional[JobStatus] = Query(None, alias="status"),
    source: Optional[JobSource] = None,
    mine_only: bool = Query(
        False, description="If true, only jobs created by current user"
    ),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    stmt = select(JobPosting).where(
        JobPosting.organization_id == user.organization_id,
        JobPosting.deleted_at.is_(None),
        JobPosting.is_active.is_(True),
    )
    if mine_only:
        stmt = stmt.where(JobPosting.created_by == user.id)
    if status_filter:
        stmt = stmt.where(JobPosting.status == status_filter)
    if source:
        stmt = stmt.where(JobPosting.source == source)
    if q and q.strip():
        stmt = stmt.where(JobPosting.job_title.ilike(f"%{q.strip()}%"))
    stmt = stmt.order_by(JobPosting.created_at.desc())
    rows = db.scalars(stmt).all()
    return [JobPostingOut.model_validate(r) for r in rows]


@router.post("", response_model=JobPostingOut, status_code=status.HTTP_201_CREATED)
def create_job_posting(
    body: JobPostingCreate,
    response: Response,
    user: User = Depends(require_writer),
    db: Session = Depends(get_db),
):
    existing, job_title = _find_reuse_or_allocate_title(
        db,
        organization_id=user.organization_id,
        desired_title=body.job_title,
        jd_text=body.jd_text,
    )
    if existing is not None:
        response.status_code = status.HTTP_200_OK
        logger.info(
            "[job-postings] reused id=%s title=%s by=%s",
            existing.id,
            existing.job_title,
            user.email,
        )
        return JobPostingOut.model_validate(existing)

    row = JobPosting(
        organization_id=user.organization_id,
        created_by=user.id,
        job_title=job_title,
        jd_text=body.jd_text,
        description=body.description,
        status=body.status,
        source=body.source,
        external_ats_id=None,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    logger.info(
        "[job-postings] created id=%s title=%s by=%s",
        row.id,
        row.job_title,
        user.email,
    )
    return JobPostingOut.model_validate(row)


@router.get("/{job_id}", response_model=JobPostingOut)
def get_job_posting(
    job_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return JobPostingOut.model_validate(_get_org_job(db, user, job_id))


@router.patch("/{job_id}", response_model=JobPostingOut)
def update_job_posting(
    job_id: UUID,
    body: JobPostingUpdate,
    user: User = Depends(require_writer),
    db: Session = Depends(get_db),
):
    row = _get_org_job(db, user, job_id)
    data = body.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(row, key, value)
    db.commit()
    db.refresh(row)
    return JobPostingOut.model_validate(row)


@router.delete("/{job_id}", response_model=JobPostingOut)
def delete_job_posting(
    job_id: UUID,
    user: User = Depends(require_writer),
    db: Session = Depends(get_db),
):
    row = _get_org_job(db, user, job_id)
    row.deleted_at = datetime.now(timezone.utc)
    row.is_active = False
    db.commit()
    db.refresh(row)
    return JobPostingOut.model_validate(row)
