"""JD ↔ CV match scoring APIs (job-scoped shortlisting)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from auth.deps import get_current_user, get_db, require_writer
from db.models import Candidate, Document, JobCandidateMatch, JobPosting, User
from services.jd_cv_matcher import (
    fingerprint_from_breakdown,
    match_content_fingerprint,
    score_cv_against_jd,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/jobs", tags=["matches"])


class ScoreMatchesRequest(BaseModel):
    """Optional filters. Default: score all unscored ready CVs for the job."""

    candidate_ids: Optional[List[UUID]] = None
    force: bool = Field(
        default=False,
        description=(
            "If true, re-score candidates that already have a match row, "
            "but only when JD/CV content fingerprint changed."
        ),
    )


class JobMatchOut(BaseModel):
    candidate_id: UUID
    document_id: Optional[UUID] = None
    score: float
    rank: Optional[int] = None
    score_breakdown: Optional[dict[str, Any]] = None
    reasons_json: Optional[dict[str, Any]] = None
    domain_overlap: list[str] = Field(default_factory=list)
    model_version: Optional[str] = None
    scored_at: datetime


class ScoreMatchesResponse(BaseModel):
    job_posting_id: UUID
    total_candidates: int
    scored: int
    skipped_already_scored: int
    skipped_unchanged: int = 0
    skipped_no_profile: int
    skipped_no_text: int
    failed: int
    unscored_remaining: int
    results: list[JobMatchOut]


def _get_active_job(db: Session, user: User, job_id: UUID) -> JobPosting:
    job = db.scalar(
        select(JobPosting).where(
            JobPosting.id == job_id,
            JobPosting.organization_id == user.organization_id,
            JobPosting.is_active.is_(True),
        )
    )
    if job is None:
        raise HTTPException(status_code=404, detail="Job posting not found")
    return job


def _jd_text_for_job(db: Session, job: JobPosting) -> str:
    text = (job.jd_text or "").strip()
    if len(text) >= 40:
        return text
    if job.jd_document_id:
        doc = db.get(Document, job.jd_document_id)
        if doc and (doc.extracted_text or "").strip():
            return doc.extracted_text.strip()
    raise HTTPException(
        status_code=400,
        detail="Job description text is not ready. Process the JD before scoring CVs.",
    )


def _cv_text_for_candidate(candidate: Candidate, document: Document) -> str:
    text = (candidate.cv_text or "").strip()
    if len(text) >= 40:
        return text
    return (document.extracted_text or "").strip()


def _recompute_ranks(db: Session, job_id: UUID) -> None:
    rows = db.scalars(
        select(JobCandidateMatch)
        .where(JobCandidateMatch.job_posting_id == job_id)
        .order_by(JobCandidateMatch.score.desc(), JobCandidateMatch.scored_at.asc())
    ).all()
    for idx, row in enumerate(rows, start=1):
        row.rank = idx
    db.commit()


def invalidate_candidate_matches(db: Session, candidate_id: UUID) -> int:
    """Delete match rows so Get Score unlocks after CV text changes."""
    rows = db.scalars(
        select(JobCandidateMatch).where(JobCandidateMatch.candidate_id == candidate_id)
    ).all()
    count = len(rows)
    for row in rows:
        db.delete(row)
    if count:
        db.commit()
    return count


def invalidate_job_matches(db: Session, job_posting_id: UUID) -> int:
    """Delete all match rows for a job when JD text changes."""
    rows = db.scalars(
        select(JobCandidateMatch).where(
            JobCandidateMatch.job_posting_id == job_posting_id
        )
    ).all()
    count = len(rows)
    for row in rows:
        db.delete(row)
    if count:
        db.commit()
    return count


@router.post(
    "/{job_id}/score-matches",
    response_model=ScoreMatchesResponse,
    summary="Score unscored CVs against this job description",
)
def score_job_matches(
    job_id: UUID,
    body: ScoreMatchesRequest = ScoreMatchesRequest(),
    user: User = Depends(require_writer),
    db: Session = Depends(get_db),
) -> ScoreMatchesResponse:
    """
    Score candidate CVs linked to this job against the JD only.

    - Skips already-scored pairs unless force=true
    - When force=true, skips pairs whose JD/CV content fingerprint is unchanged
      (keeps persisted scores stable across Rescore clicks)
    - Skips CVs without a candidate profile or usable text
    - Does not re-score other candidates relative to each other (rank is post-sort only)
    """
    job = _get_active_job(db, user, job_id)
    jd_text = _jd_text_for_job(db, job)

    doc_rows = db.execute(
        select(Document, Candidate)
        .join(Candidate, Candidate.id == Document.candidate_id)
        .where(
            Document.organization_id == user.organization_id,
            Document.job_posting_id == job_id,
            Document.document_type == "cv",
            Document.source != "ats",
            Document.candidate_id.is_not(None),
            Candidate.is_active.is_(True),
        )
        .order_by(Document.created_at.desc())
    ).all()

    # Newest document per candidate
    by_candidate: dict[UUID, tuple[Document, Candidate]] = {}
    for document, candidate in doc_rows:
        if candidate.id in by_candidate:
            continue
        if body.candidate_ids and candidate.id not in body.candidate_ids:
            continue
        by_candidate[candidate.id] = (document, candidate)

    existing = {
        row.candidate_id: row
        for row in db.scalars(
            select(JobCandidateMatch).where(JobCandidateMatch.job_posting_id == job_id)
        ).all()
    }

    scored = 0
    skipped_already = 0
    skipped_unchanged = 0
    skipped_no_profile = 0
    skipped_no_text = 0
    failed = 0
    results: list[JobMatchOut] = []

    jd_structured = job.structured_json if isinstance(job.structured_json, dict) else None
    jd_domain_tags = list(job.domain_tags or [])

    for candidate_id, (document, candidate) in by_candidate.items():
        existing_row = existing.get(candidate_id)
        if existing_row is not None and not body.force:
            skipped_already += 1
            continue

        cv_text = _cv_text_for_candidate(candidate, document)
        if len(cv_text) < 40:
            skipped_no_text += 1
            continue

        cv_structured = (
            candidate.structured_json
            if isinstance(candidate.structured_json, dict)
            else None
        )
        cv_domain_tags = list(candidate.domain_tags or [])
        current_fp = match_content_fingerprint(
            jd_text=jd_text,
            cv_text=cv_text,
            jd_structured=jd_structured,
            cv_structured=cv_structured,
            jd_domain_tags=jd_domain_tags,
            cv_domain_tags=cv_domain_tags,
        )

        if existing_row is not None and body.force:
            prev_fp = fingerprint_from_breakdown(
                existing_row.score_breakdown
                if isinstance(existing_row.score_breakdown, dict)
                else None
            )
            now = datetime.now(timezone.utc)
            if prev_fp == current_fp:
                skipped_unchanged += 1
                continue
            if prev_fp is None:
                # Legacy row: stamp fingerprint for current content and keep score.
                breakdown = (
                    dict(existing_row.score_breakdown)
                    if isinstance(existing_row.score_breakdown, dict)
                    else {}
                )
                breakdown["content_fingerprint"] = current_fp
                existing_row.score_breakdown = breakdown
                existing_row.updated_at = now
                db.commit()
                skipped_unchanged += 1
                logger.info(
                    "[jd_cv_match] kept score (backfilled fingerprint) job=%s candidate=%s",
                    job_id,
                    candidate_id,
                )
                continue

        try:
            match = score_cv_against_jd(
                job_title=job.job_title or "",
                jd_text=jd_text,
                cv_text=cv_text,
                jd_structured=jd_structured,
                cv_structured=cv_structured,
                jd_domain_tags=jd_domain_tags,
                cv_domain_tags=cv_domain_tags,
            )
        except Exception as exc:  # noqa: BLE001
            failed += 1
            logger.warning(
                "[jd_cv_match] score failed job=%s candidate=%s: %s",
                job_id,
                candidate_id,
                exc,
            )
            continue

        row = existing_row
        now = datetime.now(timezone.utc)
        if row is None:
            row = JobCandidateMatch(
                organization_id=user.organization_id,
                job_posting_id=job_id,
                candidate_id=candidate_id,
            )
            db.add(row)
            existing[candidate_id] = row

        row.cv_document_id = document.id
        row.score = match.score
        row.score_breakdown = match.score_breakdown
        row.reasons_json = match.reasons_json
        row.domain_overlap = list(match.domain_overlap)
        row.model_version = match.model_version
        row.scored_at = now
        row.updated_at = now
        db.commit()
        db.refresh(row)
        scored += 1
        results.append(
            JobMatchOut(
                candidate_id=candidate_id,
                document_id=document.id,
                score=float(match.score),
                rank=row.rank,
                score_breakdown=row.score_breakdown,
                reasons_json=row.reasons_json,
                domain_overlap=list(row.domain_overlap or []),
                model_version=row.model_version,
                scored_at=row.scored_at,
            )
        )

    if scored:
        _recompute_ranks(db, job_id)
        # Refresh ranks on response rows
        rank_map = {
            r.candidate_id: r.rank
            for r in db.scalars(
                select(JobCandidateMatch).where(JobCandidateMatch.job_posting_id == job_id)
            ).all()
        }
        for item in results:
            item.rank = rank_map.get(item.candidate_id)

    # Re-load all ready profiles for remaining unscored count
    all_ready = {
        candidate.id
        for document, candidate in db.execute(
            select(Document, Candidate)
            .join(Candidate, Candidate.id == Document.candidate_id)
            .where(
                Document.organization_id == user.organization_id,
                Document.job_posting_id == job_id,
                Document.document_type == "cv",
                Document.source != "ats",
                Document.candidate_id.is_not(None),
            )
        ).all()
        if len(_cv_text_for_candidate(candidate, document)) >= 40
    }
    matched_ids = {
        row.candidate_id
        for row in db.scalars(
            select(JobCandidateMatch).where(JobCandidateMatch.job_posting_id == job_id)
        ).all()
    }
    unscored_remaining = len(all_ready - matched_ids)

    if (
        scored == 0
        and skipped_already == 0
        and skipped_unchanged == 0
        and failed == 0
        and skipped_no_text == 0
    ):
        # Nothing to score — likely no profiles yet
        skipped_no_profile = max(0, len(doc_rows) - len(by_candidate))

    return ScoreMatchesResponse(
        job_posting_id=job_id,
        total_candidates=len(by_candidate) if body.candidate_ids else len(all_ready),
        scored=scored,
        skipped_already_scored=skipped_already,
        skipped_unchanged=skipped_unchanged,
        skipped_no_profile=skipped_no_profile,
        skipped_no_text=skipped_no_text,
        failed=failed,
        unscored_remaining=unscored_remaining,
        results=results,
    )


@router.get(
    "/{job_id}/matches",
    response_model=list[JobMatchOut],
    summary="List JD↔CV match scores for a job (highest first)",
)
def list_job_matches(
    job_id: UUID,
    limit: int = Query(100, ge=1, le=500),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[JobMatchOut]:
    _get_active_job(db, user, job_id)
    rows = db.scalars(
        select(JobCandidateMatch)
        .where(
            JobCandidateMatch.organization_id == user.organization_id,
            JobCandidateMatch.job_posting_id == job_id,
        )
        .order_by(JobCandidateMatch.score.desc(), JobCandidateMatch.scored_at.asc())
        .limit(limit)
    ).all()
    def _ten(raw: object) -> float:
        value = float(raw)
        if value > 10:
            value = value / 10.0
        return round(max(1.0, min(10.0, value)), 1)

    return [
        JobMatchOut(
            candidate_id=row.candidate_id,
            document_id=row.cv_document_id,
            score=_ten(row.score),
            rank=row.rank,
            score_breakdown=row.score_breakdown,
            reasons_json=row.reasons_json,
            domain_overlap=list(row.domain_overlap or []),
            model_version=row.model_version,
            scored_at=row.scored_at,
        )
        for row in rows
    ]
