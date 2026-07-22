"""Persist uploaded CV/JD files into documents table + local disk."""

from __future__ import annotations

import logging
import re
import uuid
from pathlib import Path
from typing import Literal, Optional
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.orm import Session

import config as app_config
from db.models import Candidate, Document, JobPosting, User

logger = logging.getLogger(__name__)

DocumentType = Literal["cv", "jd"]
DocumentSource = Literal["upload", "manual", "ats"]

_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


def uploads_root() -> Path:
    raw = (app_config.DOCUMENT_UPLOAD_DIR or "uploads").strip() or "uploads"
    path = Path(raw)
    if not path.is_absolute():
        path = Path(__file__).resolve().parent / path
    path.mkdir(parents=True, exist_ok=True)
    return path


def _safe_filename(name: str) -> str:
    base = Path(name or "upload.bin").name
    cleaned = _SAFE_NAME.sub("_", base).strip("._") or "upload.bin"
    return cleaned[:200]


def _assert_candidate(db: Session, user: User, candidate_id: Optional[UUID]) -> None:
    if candidate_id is None:
        return
    row = db.get(Candidate, candidate_id)
    if (
        row is None
        or row.organization_id != user.organization_id
        or row.deleted_at is not None
    ):
        raise HTTPException(status_code=404, detail="Candidate not found")


def _assert_job(db: Session, user: User, job_posting_id: Optional[UUID]) -> None:
    if job_posting_id is None:
        return
    row = db.get(JobPosting, job_posting_id)
    if (
        row is None
        or row.organization_id != user.organization_id
        or row.deleted_at is not None
    ):
        raise HTTPException(status_code=404, detail="Job posting not found")


def create_uploaded_document(
    db: Session,
    user: User,
    *,
    document_type: DocumentType,
    file_bytes: bytes,
    original_filename: str,
    mime_type: Optional[str] = None,
    candidate_id: Optional[UUID] = None,
    job_posting_id: Optional[UUID] = None,
    source: DocumentSource = "upload",
) -> Document:
    """
    Write file to disk and insert a documents row (status=processing).
    For JD, optionally links job_postings.jd_document_id after flush.
    """
    if document_type == "cv":
        _assert_candidate(db, user, candidate_id)
    else:
        _assert_job(db, user, job_posting_id)

    max_bytes = int(getattr(app_config, "DOCUMENT_MAX_BYTES", 15 * 1024 * 1024))
    if len(file_bytes) > max_bytes:
        raise HTTPException(
            status_code=400,
            detail=f"File too large (max {max_bytes // (1024 * 1024)} MB)",
        )
    if not file_bytes:
        raise HTTPException(status_code=400, detail="File is empty")

    doc_id = uuid.uuid4()
    org_dir = uploads_root() / str(user.organization_id)
    org_dir.mkdir(parents=True, exist_ok=True)
    safe_name = _safe_filename(original_filename)
    disk_name = f"{doc_id}_{safe_name}"
    abs_path = org_dir / disk_name
    abs_path.write_bytes(file_bytes)

    # Store path relative to uploads root for portability
    rel_path = f"{user.organization_id}/{disk_name}"

    row = Document(
        id=doc_id,
        organization_id=user.organization_id,
        uploaded_by=user.id,
        candidate_id=candidate_id if document_type == "cv" else None,
        document_type=document_type,
        source=source,
        original_filename=safe_name[:512],
        storage_path=rel_path,
        mime_type=(mime_type or "")[:127] or None,
        file_size_bytes=len(file_bytes),
        upload_status="processing",
    )
    db.add(row)
    db.flush()

    if document_type == "jd" and job_posting_id is not None:
        job = db.get(JobPosting, job_posting_id)
        if job is not None:
            job.jd_document_id = row.id

    db.commit()
    db.refresh(row)
    logger.info(
        "[documents] saved id=%s type=%s user=%s bytes=%s path=%s",
        row.id,
        document_type,
        user.email,
        len(file_bytes),
        rel_path,
    )
    return row


def mark_document_ready(
    db: Session,
    document_id: UUID,
    *,
    extracted_text: str,
) -> Document:
    row = db.get(Document, document_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Document not found")
    row.extracted_text = extracted_text or None
    row.upload_status = "ready"
    db.commit()
    db.refresh(row)
    return row


def mark_document_failed(
    db: Session,
    document_id: UUID,
    *,
    error: Optional[str] = None,
) -> None:
    row = db.get(Document, document_id)
    if row is None:
        return
    row.upload_status = "failed"
    if error and not row.extracted_text:
        # Keep a short note in extracted_text only if empty (no dedicated error col)
        row.extracted_text = None
    db.commit()
    logger.warning("[documents] failed id=%s err=%s", document_id, (error or "")[:200])


def resolve_storage_path(doc: Document) -> Optional[Path]:
    if not doc.storage_path:
        return None
    path = Path(doc.storage_path)
    if path.is_absolute():
        return path if path.exists() else None
    full = uploads_root() / path
    return full if full.exists() else None
