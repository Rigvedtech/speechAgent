"""Import remote ATS records into local candidates / jobs / documents."""

from __future__ import annotations

import logging
from typing import Any, Optional
from uuid import UUID

import requests
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ats.base import AtsRemoteCandidate, AtsRemoteJob
from ats.factory import get_provider
from db.models import Candidate, Document, JobPosting, Organization, User
from document_store import create_uploaded_document, mark_document_ready

logger = logging.getLogger(__name__)


def _find_candidate_by_ats(
    db: Session, org_id: UUID, external_id: str
) -> Optional[Candidate]:
    return db.scalar(
        select(Candidate).where(
            Candidate.organization_id == org_id,
            Candidate.external_ats_id == external_id,
            Candidate.deleted_at.is_(None),
        )
    )


def _find_job_by_ats(
    db: Session, org_id: UUID, external_id: str
) -> Optional[JobPosting]:
    return db.scalar(
        select(JobPosting).where(
            JobPosting.organization_id == org_id,
            JobPosting.external_ats_id == external_id,
            JobPosting.deleted_at.is_(None),
        )
    )


def _download_bytes(
    url: str,
    timeout: float = 30.0,
    headers: Optional[dict] = None,
) -> tuple[bytes, Optional[str]]:
    try:
        resp = requests.get(url, timeout=timeout, headers=headers or {})
    except requests.RequestException as ex:
        raise HTTPException(status_code=502, detail=f"Failed to download ATS file: {ex}") from ex
    if resp.status_code >= 400:
        raise HTTPException(
            status_code=502,
            detail=f"ATS file download HTTP {resp.status_code}",
        )
    return resp.content, resp.headers.get("Content-Type")


def _auth_headers(provider: Any) -> dict:
    fn = getattr(provider, "_headers", None)
    if callable(fn):
        try:
            return dict(fn())
        except Exception:
            return {}
    return {}


def _usable_extracted_text(text: str, *, mime: Optional[str], filename: str) -> str:
    """Avoid treating PDF/DOCX binary as UTF-8 text for cv_text/jd_text."""
    if not text or not text.strip():
        return ""
    lower_name = (filename or "").lower()
    lower_mime = (mime or "").lower()
    if (
        lower_name.endswith((".pdf", ".docx", ".doc", ".png", ".jpg", ".jpeg"))
        or "pdf" in lower_mime
        or "officedocument" in lower_mime
        or "msword" in lower_mime
    ):
        return ""
    sample = text[:2000]
    if "\x00" in sample:
        return ""
    printable = sum(1 for ch in sample if ch.isprintable() or ch in "\n\r\t")
    if printable < max(20, int(len(sample) * 0.7)):
        return ""
    return text.strip()


def import_candidate(
    db: Session,
    user: User,
    org: Organization,
    external_id: str,
    parent_id: Optional[str] = None,
) -> Candidate:
    provider = get_provider(org)
    try:
        try:
            remote = provider.get_candidate(external_id, parent_id=parent_id)
        except TypeError:
            remote = provider.get_candidate(external_id)
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve)) from ve

    row = _find_candidate_by_ats(db, org.id, remote.external_id)
    if row is None:
        row = Candidate(
            organization_id=org.id,
            created_by=user.id,
            full_name=remote.full_name[:255],
            email=(remote.email or None),
            phone=(remote.phone or None)[:50] if remote.phone else None,
            cv_text=remote.cv_text,
            source="ats",
            external_ats_id=remote.external_id[:255],
            is_active=True,
        )
        db.add(row)
        db.flush()
    else:
        row.full_name = remote.full_name[:255]
        row.email = remote.email or row.email
        row.phone = (remote.phone or row.phone)
        if remote.cv_text:
            row.cv_text = remote.cv_text
        row.source = "ats"
        row.is_active = True

    db.commit()
    db.refresh(row)

    # Persist CV file into documents when we have text or a downloadable URL
    try:
        _persist_cv_document(db, user, row, remote, headers=_auth_headers(provider))
    except Exception as ex:
        logger.warning("[ats] CV document persist skipped: %s", ex)

    db.refresh(row)
    logger.info(
        "[ats] imported candidate org=%s external=%s local=%s",
        org.slug,
        remote.external_id,
        row.id,
    )
    return row


def import_job(
    db: Session,
    user: User,
    org: Organization,
    external_id: str,
) -> JobPosting:
    provider = get_provider(org)
    try:
        remote = provider.get_job(external_id)
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve)) from ve

    row = _find_job_by_ats(db, org.id, remote.external_id)
    if row is None:
        row = JobPosting(
            organization_id=org.id,
            created_by=user.id,
            job_title=remote.job_title[:255],
            jd_text=remote.jd_text,
            description=remote.description,
            source="ats",
            external_ats_id=remote.external_id[:255],
            status="open",
            is_active=True,
        )
        db.add(row)
        db.flush()
    else:
        row.job_title = remote.job_title[:255]
        if remote.jd_text:
            row.jd_text = remote.jd_text
        if remote.description:
            row.description = remote.description
        row.source = "ats"
        row.is_active = True

    db.commit()
    db.refresh(row)

    try:
        _persist_jd_document(db, user, row, remote, headers=_auth_headers(provider))
    except Exception as ex:
        logger.warning("[ats] JD document persist skipped: %s", ex)

    db.refresh(row)
    logger.info(
        "[ats] imported job org=%s external=%s local=%s",
        org.slug,
        remote.external_id,
        row.id,
    )
    return row


def _persist_cv_document(
    db: Session,
    user: User,
    candidate: Candidate,
    remote: AtsRemoteCandidate,
    headers: Optional[dict] = None,
) -> Optional[Document]:
    file_bytes: Optional[bytes] = None
    mime: Optional[str] = None
    filename = remote.cv_filename or f"{remote.external_id}_cv.txt"

    if remote.cv_url:
        file_bytes, mime = _download_bytes(remote.cv_url, headers=headers)
        if not remote.cv_filename and remote.cv_url:
            filename = remote.cv_url.rstrip("/").split("/")[-1] or filename
    elif remote.cv_text:
        file_bytes = remote.cv_text.encode("utf-8")
        mime = "text/plain"
        if not filename.endswith(".txt"):
            filename = f"{filename}.txt"
    else:
        return None

    doc = create_uploaded_document(
        db,
        user,
        document_type="cv",
        file_bytes=file_bytes,
        original_filename=filename,
        mime_type=mime,
        candidate_id=candidate.id,
        source="ats",
    )
    text = remote.cv_text or ""
    if not text and file_bytes:
        try:
            decoded = file_bytes.decode("utf-8", errors="ignore")
        except Exception:
            decoded = ""
        text = _usable_extracted_text(decoded, mime=mime, filename=filename)
    if text:
        mark_document_ready(db, doc.id, extracted_text=text)
        if not candidate.cv_text:
            candidate.cv_text = text
            db.commit()
    elif remote.cv_text:
        mark_document_ready(db, doc.id, extracted_text=remote.cv_text)
    return doc


def _persist_jd_document(
    db: Session,
    user: User,
    job: JobPosting,
    remote: AtsRemoteJob,
    headers: Optional[dict] = None,
) -> Optional[Document]:
    file_bytes: Optional[bytes] = None
    mime: Optional[str] = None
    filename = remote.jd_filename or f"{remote.external_id}_jd.txt"

    if remote.jd_url:
        file_bytes, mime = _download_bytes(remote.jd_url, headers=headers)
        if not remote.jd_filename and remote.jd_url:
            filename = remote.jd_url.rstrip("/").split("/")[-1] or filename
    elif remote.jd_text:
        file_bytes = remote.jd_text.encode("utf-8")
        mime = "text/plain"
        if not filename.endswith(".txt"):
            filename = f"{filename}.txt"
    else:
        return None

    doc = create_uploaded_document(
        db,
        user,
        document_type="jd",
        file_bytes=file_bytes,
        original_filename=filename,
        mime_type=mime,
        job_posting_id=job.id,
        source="ats",
    )
    text = remote.jd_text or ""
    if not text and file_bytes:
        try:
            decoded = file_bytes.decode("utf-8", errors="ignore")
        except Exception:
            decoded = ""
        text = _usable_extracted_text(decoded, mime=mime, filename=filename)
    if text:
        mark_document_ready(db, doc.id, extracted_text=text)
        job.jd_text = text
        job.jd_document_id = doc.id
        db.commit()
    elif remote.jd_text:
        job.jd_text = remote.jd_text
        job.jd_document_id = doc.id
        mark_document_ready(db, doc.id, extracted_text=remote.jd_text)
        db.commit()
    else:
        job.jd_document_id = doc.id
        db.commit()
    return doc
