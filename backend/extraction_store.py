"""Persist n8n extract/generate runs into document_extractions."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.orm import Session

from db.models import Candidate, DocumentExtraction, JobPosting, User

logger = logging.getLogger(__name__)


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


def save_cv_extraction(
    db: Session,
    user: User,
    *,
    cv_text: str,
    candidate_id: Optional[UUID] = None,
    cv_document_id: Optional[UUID] = None,
    raw_response: Optional[Any] = None,
) -> DocumentExtraction:
    _assert_candidate(db, user, candidate_id)
    now = datetime.now(timezone.utc)
    row = DocumentExtraction(
        organization_id=user.organization_id,
        requested_by=user.id,
        candidate_id=candidate_id,
        cv_document_id=cv_document_id,
        cv_text=cv_text or None,
        status="success",
        raw_response=raw_response,
        completed_at=now,
    )
    db.add(row)
    if candidate_id and cv_text:
        candidate = db.get(Candidate, candidate_id)
        if candidate is not None:
            candidate.cv_text = cv_text
    db.commit()
    db.refresh(row)
    logger.info("[extractions] CV saved id=%s user=%s doc=%s", row.id, user.email, cv_document_id)
    return row


def save_jd_extraction(
    db: Session,
    user: User,
    *,
    jd_text: str,
    job_posting_id: Optional[UUID] = None,
    jd_document_id: Optional[UUID] = None,
    raw_response: Optional[Any] = None,
) -> DocumentExtraction:
    _assert_job(db, user, job_posting_id)
    now = datetime.now(timezone.utc)
    row = DocumentExtraction(
        organization_id=user.organization_id,
        requested_by=user.id,
        job_posting_id=job_posting_id,
        jd_document_id=jd_document_id,
        jd_text=jd_text or None,
        status="success",
        raw_response=raw_response,
        completed_at=now,
    )
    db.add(row)
    if job_posting_id and jd_text and len(jd_text.strip()) >= 100:
        job = db.get(JobPosting, job_posting_id)
        if job is not None:
            job.jd_text = jd_text.strip()
            if jd_document_id is not None:
                job.jd_document_id = jd_document_id
    db.commit()
    db.refresh(row)
    logger.info("[extractions] JD saved id=%s user=%s doc=%s", row.id, user.email, jd_document_id)
    return row


def save_question_generation(
    db: Session,
    user: User,
    *,
    jd_text: str,
    cv_text: str,
    questions: Any,
    candidate_id: Optional[UUID] = None,
    job_posting_id: Optional[UUID] = None,
    extraction_id: Optional[UUID] = None,
    raw_response: Optional[Any] = None,
    error_message: Optional[str] = None,
    success: bool = True,
) -> DocumentExtraction:
    _assert_candidate(db, user, candidate_id)
    _assert_job(db, user, job_posting_id)
    now = datetime.now(timezone.utc)

    row: Optional[DocumentExtraction] = None
    if extraction_id is not None:
        row = db.get(DocumentExtraction, extraction_id)
        if (
            row is None
            or row.organization_id != user.organization_id
        ):
            raise HTTPException(status_code=404, detail="Extraction not found")

    if row is None:
        row = DocumentExtraction(
            organization_id=user.organization_id,
            requested_by=user.id,
        )
        db.add(row)

    row.requested_by = user.id
    row.candidate_id = candidate_id or row.candidate_id
    row.job_posting_id = job_posting_id or row.job_posting_id
    row.jd_text = jd_text
    row.cv_text = cv_text
    row.questions_json = questions
    row.raw_response = raw_response
    row.status = "success" if success else "failed"
    row.error_message = error_message
    row.completed_at = now

    if success and candidate_id and cv_text:
        candidate = db.get(Candidate, candidate_id)
        if candidate is not None:
            candidate.cv_text = cv_text
    if success and job_posting_id and jd_text and len(jd_text.strip()) >= 100:
        job = db.get(JobPosting, job_posting_id)
        if job is not None:
            job.jd_text = jd_text.strip()

    db.commit()
    db.refresh(row)
    logger.info(
        "[extractions] questions saved id=%s status=%s user=%s",
        row.id,
        row.status,
        user.email,
    )
    return row
