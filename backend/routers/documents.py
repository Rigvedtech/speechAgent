"""List / fetch persisted documents (CV/JD uploads)."""

from __future__ import annotations

from datetime import datetime
from typing import List, Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from auth.deps import get_current_user, get_db
from db.models import Document, User

router = APIRouter(prefix="/api/documents", tags=["documents"])

DocumentType = Literal["cv", "jd"]


class DocumentOut(BaseModel):
    id: UUID
    organization_id: UUID
    uploaded_by: Optional[UUID] = None
    candidate_id: Optional[UUID] = None
    document_type: str
    source: str
    external_ats_id: Optional[str] = None
    original_filename: Optional[str] = None
    mime_type: Optional[str] = None
    file_size_bytes: Optional[int] = None
    upload_status: str
    # Text preview only — full text can be large
    has_extracted_text: bool = False
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DocumentDetailOut(DocumentOut):
    extracted_text: Optional[str] = None
    storage_path: Optional[str] = None


def _to_out(row: Document) -> DocumentOut:
    return DocumentOut(
        id=row.id,
        organization_id=row.organization_id,
        uploaded_by=row.uploaded_by,
        candidate_id=row.candidate_id,
        document_type=row.document_type,
        source=row.source,
        external_ats_id=row.external_ats_id,
        original_filename=row.original_filename,
        mime_type=row.mime_type,
        file_size_bytes=row.file_size_bytes,
        upload_status=row.upload_status,
        has_extracted_text=bool(row.extracted_text and row.extracted_text.strip()),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _get_org_document(db: Session, user: User, document_id: UUID) -> Document:
    row = db.get(Document, document_id)
    if row is None or row.organization_id != user.organization_id:
        raise HTTPException(status_code=404, detail="Document not found")
    if user.role == "recruiter" and row.uploaded_by != user.id:
        raise HTTPException(status_code=404, detail="Document not found")
    return row


@router.get("", response_model=List[DocumentOut])
def list_documents(
    document_type: Optional[DocumentType] = None,
    candidate_id: Optional[UUID] = None,
    status_filter: Optional[str] = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=200),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    stmt = select(Document).where(Document.organization_id == user.organization_id)
    if user.role == "recruiter":
        stmt = stmt.where(Document.uploaded_by == user.id)
    if document_type:
        stmt = stmt.where(Document.document_type == document_type)
    if candidate_id:
        stmt = stmt.where(Document.candidate_id == candidate_id)
    if status_filter:
        stmt = stmt.where(Document.upload_status == status_filter)
    stmt = stmt.order_by(Document.created_at.desc()).limit(limit)
    rows = db.scalars(stmt).all()
    return [_to_out(r) for r in rows]


@router.get("/{document_id}", response_model=DocumentDetailOut)
def get_document(
    document_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = _get_org_document(db, user, document_id)
    base = _to_out(row)
    return DocumentDetailOut(
        **base.model_dump(),
        extracted_text=row.extracted_text,
        storage_path=row.storage_path,
    )
