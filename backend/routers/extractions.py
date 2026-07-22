"""List / fetch persisted document_extractions."""

from __future__ import annotations

from datetime import datetime
from typing import Any, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from auth.deps import get_current_user, get_db
from db.models import DocumentExtraction, User

router = APIRouter(prefix="/api/extractions", tags=["extractions"])


class ExtractionOut(BaseModel):
    id: UUID
    organization_id: UUID
    requested_by: Optional[UUID] = None
    candidate_id: Optional[UUID] = None
    job_posting_id: Optional[UUID] = None
    jd_document_id: Optional[UUID] = None
    cv_document_id: Optional[UUID] = None
    status: str
    jd_text: Optional[str] = None
    cv_text: Optional[str] = None
    questions_json: Optional[Any] = None
    error_message: Optional[str] = None
    created_at: datetime
    completed_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


@router.get("", response_model=List[ExtractionOut])
def list_extractions(
    status_filter: Optional[str] = Query(None, alias="status"),
    candidate_id: Optional[UUID] = None,
    job_posting_id: Optional[UUID] = None,
    limit: int = Query(50, ge=1, le=200),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    stmt = select(DocumentExtraction).where(
        DocumentExtraction.organization_id == user.organization_id
    )
    if user.role == "recruiter":
        stmt = stmt.where(DocumentExtraction.requested_by == user.id)
    if status_filter:
        stmt = stmt.where(DocumentExtraction.status == status_filter)
    if candidate_id:
        stmt = stmt.where(DocumentExtraction.candidate_id == candidate_id)
    if job_posting_id:
        stmt = stmt.where(DocumentExtraction.job_posting_id == job_posting_id)
    stmt = stmt.order_by(DocumentExtraction.created_at.desc()).limit(limit)
    rows = db.scalars(stmt).all()
    return [ExtractionOut.model_validate(r) for r in rows]


@router.get("/{extraction_id}", response_model=ExtractionOut)
def get_extraction(
    extraction_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = db.get(DocumentExtraction, extraction_id)
    if row is None or row.organization_id != user.organization_id:
        raise HTTPException(status_code=404, detail="Extraction not found")
    if user.role == "recruiter" and row.requested_by != user.id:
        raise HTTPException(status_code=404, detail="Extraction not found")
    return ExtractionOut.model_validate(row)
