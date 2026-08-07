"""
Structured parsing endpoints — Phase 3.

Flow per document
-----------------
1. Load document.extracted_text (from Phase 2)
2. Route: document_type="cv" → parse_cv(); "jd" → parse_jd()
3. Merge parsed fields into document.structured_json (Phase 2 metadata preserved)
4. If document has a candidate_id → update candidate profile fields
5. Return ParsedOut

Endpoints
---------
POST /api/documents/{doc_id}/parse        — parse single document
POST /api/batches/{batch_id}/parse        — parse all extracted docs in batch
GET  /api/documents/{doc_id}/parsed       — read stored parsed result
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from auth.deps import get_current_user, get_db, require_writer
from db.models import (
    Candidate,
    Document,
    JobCandidateLink,
    UploadBatch,
    UploadBatchItem,
    User,
)
from services.structured_extractor import (
    ParsedCV,
    ParsedJD,
    parse_cv,
    parse_jd,
    parsed_cv_to_dict,
    parsed_jd_to_dict,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["parsing"])


# ---------------------------------------------------------------------------
# Pydantic output schemas
# ---------------------------------------------------------------------------

class EducationOut(BaseModel):
    degree: str
    field: Optional[str] = None
    institution: Optional[str] = None
    year: Optional[int] = None


class ParsedCVOut(BaseModel):
    document_id: UUID
    candidate_id: Optional[UUID] = None
    linked_to_job: bool = False
    document_type: str
    original_filename: Optional[str] = None
    upload_status: str
    parse_status: str          # "parsed" | "no_text" | "failed"
    parse_method: Optional[str] = None
    confidence: float = 0.0
    # CV fields
    full_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    linkedin_url: Optional[str] = None
    github_url: Optional[str] = None
    location: Optional[str] = None
    current_title: Optional[str] = None
    total_experience_years: Optional[float] = None
    summary: Optional[str] = None
    skills: list[str] = []
    education: list[EducationOut] = []
    domain_tags: list[str] = []
    # JD fields (populated when document_type="jd")
    job_title: Optional[str] = None
    experience_range: Optional[str] = None
    minimum_qualification: Optional[str] = None
    required_skills: list[str] = []
    jd_summary: Optional[str] = None


class BatchParseSummary(BaseModel):
    batch_id: UUID
    total: int
    parsed: int
    skipped_no_text: int
    skipped_already_parsed: int
    failed: int
    results: list[ParsedCVOut]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_org_doc(db: Session, user: User, doc_id: UUID) -> Document:
    doc = db.get(Document, doc_id)
    if doc is None or doc.organization_id != user.organization_id:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


def _is_already_parsed(doc: Document) -> bool:
    """Check if Phase 3 parse result is already stored."""
    meta: dict = doc.structured_json or {}
    return "parsed_cv" in meta or "parsed_jd" in meta


def _needs_candidate_link(db: Session, doc: Document) -> bool:
    if (doc.document_type or "cv") != "cv" or not doc.job_posting_id:
        return False
    if not doc.candidate_id:
        return True
    return db.scalars(
        select(JobCandidateLink.id).where(
            JobCandidateLink.job_posting_id == doc.job_posting_id,
            JobCandidateLink.candidate_id == doc.candidate_id,
        ).limit(1)
    ).first() is None


def _run_parse(doc: Document, db: Session, actor: User) -> ParsedCVOut:
    """
    Run the structured extraction pipeline for one document.
    Merges result into document.structured_json (preserving Phase 2 metadata).
    Updates candidate profile fields if candidate_id is set.
    """
    text = doc.extracted_text or ""

    if not text.strip():
        logger.warning("[parsing] doc=%s has no extracted_text — skipping LLM", doc.id)
        return ParsedCVOut(
            document_id=doc.id,
            document_type=doc.document_type or "cv",
            original_filename=doc.original_filename,
            upload_status=doc.upload_status,
            parse_status="no_text",
            confidence=0.0,
        )

    doc_type = doc.document_type or "cv"
    parsed_dict: dict[str, Any]
    out: ParsedCVOut

    try:
        if doc_type == "jd":
            parsed: ParsedJD = parse_jd(text)
            parsed_dict = parsed_jd_to_dict(parsed)

            # Merge into structured_json under "parsed_jd" key
            existing: dict = dict(doc.structured_json or {})
            existing["parsed_jd"] = parsed_dict
            existing["parsed_at"] = datetime.now(timezone.utc).isoformat()
            doc.structured_json = existing

            out = ParsedCVOut(
                document_id=doc.id,
                document_type=doc_type,
                original_filename=doc.original_filename,
                upload_status=doc.upload_status,
                parse_status="parsed",
                parse_method=parsed.parse_method,
                confidence=parsed.confidence,
                job_title=parsed.job_title,
                location=parsed.location,
                experience_range=parsed.experience_range,
                minimum_qualification=parsed.minimum_qualification,
                required_skills=parsed.required_skills,
                domain_tags=parsed.domain_tags,
                jd_summary=parsed.jd_summary,
            )

            # If this doc is linked to a job posting — update its structured_json too
            if doc.job_posting_id:
                from db.models import JobPosting
                jp = db.get(JobPosting, doc.job_posting_id)
                if jp and jp.organization_id == doc.organization_id:
                    jp_meta: dict = dict(jp.structured_json or {})
                    jp_meta["parsed_jd"] = parsed_dict
                    jp.structured_json = jp_meta
                    jp.domain_tags = parsed.domain_tags
                    jd_changed = False
                    if len(text.strip()) >= 100:
                        new_jd = text.strip()
                        jd_changed = (jp.jd_text or "").strip() != new_jd
                        jp.jd_text = new_jd
                    jp.pipeline_status = "ready"
                    if jd_changed:
                        from routers.matches import invalidate_job_matches

                        cleared = invalidate_job_matches(db, jp.id)
                        if cleared:
                            logger.info(
                                "[parsing] invalidated %s match score(s) after JD reparse job=%s",
                                cleared,
                                jp.id,
                            )

        else:  # "cv" or unknown
            parsed_cv: ParsedCV = parse_cv(text)
            parsed_dict = parsed_cv_to_dict(parsed_cv)

            # Merge into structured_json under "parsed_cv" key
            existing = dict(doc.structured_json or {})
            existing["parsed_cv"] = parsed_dict
            existing["parsed_at"] = datetime.now(timezone.utc).isoformat()
            doc.structured_json = existing

            out = ParsedCVOut(
                document_id=doc.id,
                document_type=doc_type,
                original_filename=doc.original_filename,
                upload_status=doc.upload_status,
                parse_status="parsed",
                parse_method=parsed_cv.parse_method,
                confidence=parsed_cv.confidence,
                full_name=parsed_cv.full_name,
                email=parsed_cv.email,
                phone=parsed_cv.phone,
                linkedin_url=parsed_cv.linkedin_url,
                github_url=parsed_cv.github_url,
                location=parsed_cv.location,
                current_title=parsed_cv.current_title,
                total_experience_years=parsed_cv.total_experience_years,
                summary=parsed_cv.summary,
                skills=parsed_cv.skills,
                education=[
                    EducationOut(
                        degree=e.degree,
                        field=e.field,
                        institution=e.institution,
                        year=e.year,
                    )
                    for e in parsed_cv.education
                ],
                domain_tags=parsed_cv.domain_tags,
            )

            if doc.job_posting_id:
                candidate = _ensure_candidate_and_job_link(db, doc, parsed_cv, actor)
                out.candidate_id = candidate.id
                out.linked_to_job = True
            elif doc.candidate_id:
                _update_candidate(db, doc, parsed_cv)
                out.candidate_id = doc.candidate_id

    except Exception as exc:
        logger.error("[parsing] doc=%s parse error: %s", doc.id, exc, exc_info=True)
        db.rollback()
        return ParsedCVOut(
            document_id=doc.id,
            document_type=doc_type,
            original_filename=doc.original_filename,
            upload_status=doc.upload_status,
            parse_status="failed",
            confidence=0.0,
        )

    db.commit()
    logger.info(
        "[parsing] doc=%s type=%s method=%s confidence=%.2f skills=%d",
        doc.id, doc_type, out.parse_method, out.confidence, len(out.skills or []),
    )
    return out


def _candidate_name(parsed: ParsedCV, doc: Document) -> str:
    # Product choice: in bulk CV upload, default candidate display name to CV file name.
    stem = re.sub(r"[_\-]+", " ", Path(doc.original_filename or "").stem).strip()
    if len(stem) >= 2:
        return stem[:255]
    if parsed.full_name and parsed.full_name.strip():
        return parsed.full_name.strip()[:255]
    if parsed.email and "@" in parsed.email:
        local_part = parsed.email.split("@", 1)[0]
        from_email = re.sub(r"[._+\-]+", " ", local_part).strip().title()
        if len(from_email) >= 2:
            return from_email[:255]
    return (stem or "Unknown Candidate")[:255]


def _find_candidate_for_cv(
    db: Session,
    doc: Document,
    parsed: ParsedCV,
) -> Optional[Candidate]:
    if parsed.email:
        email = parsed.email.strip().lower()
        candidate = db.scalars(
            select(Candidate).where(
                Candidate.organization_id == doc.organization_id,
                Candidate.deleted_at.is_(None),
                func.lower(Candidate.email) == email,
            ).limit(1)
        ).first()
        if candidate:
            return candidate

    if doc.content_hash:
        return db.scalars(
            select(Candidate).where(
                Candidate.organization_id == doc.organization_id,
                Candidate.deleted_at.is_(None),
                Candidate.content_hash == doc.content_hash,
            ).limit(1)
        ).first()
    return None


def _ensure_candidate_and_job_link(
    db: Session,
    doc: Document,
    parsed: ParsedCV,
    actor: User,
) -> Candidate:
    """Idempotently create/reuse a candidate and attach this CV to its job."""
    candidate = _find_candidate_for_cv(db, doc, parsed)
    parsed_dict = parsed_cv_to_dict(parsed)

    if candidate is None:
        candidate = Candidate(
            organization_id=doc.organization_id,
            created_by=actor.id,
            full_name=_candidate_name(parsed, doc),
            email=parsed.email.strip().lower()[:320] if parsed.email else None,
            phone=parsed.phone[:50] if parsed.phone else None,
            cv_text=doc.extracted_text,
            source="bulk_upload",
            current_title=parsed.current_title[:255] if parsed.current_title else None,
            location=parsed.location[:255] if parsed.location else None,
            linkedin_url=parsed.linkedin_url,
            structured_json={"parsed_cv": parsed_dict},
            domain_tags=sorted(set(parsed.domain_tags)),
            content_hash=doc.content_hash,
            primary_cv_document_id=doc.id,
        )
        db.add(candidate)
        db.flush()
        logger.info("[parsing] created candidate=%s from doc=%s", candidate.id, doc.id)
    else:
        candidate.cv_text = doc.extracted_text or candidate.cv_text
        candidate.content_hash = doc.content_hash or candidate.content_hash
        candidate.primary_cv_document_id = doc.id

    doc.candidate_id = candidate.id
    _update_candidate(db, doc, parsed)

    link = db.scalars(
        select(JobCandidateLink).where(
            JobCandidateLink.job_posting_id == doc.job_posting_id,
            JobCandidateLink.candidate_id == candidate.id,
        ).limit(1)
    ).first()
    if link is None:
        link = JobCandidateLink(
            organization_id=doc.organization_id,
            job_posting_id=doc.job_posting_id,
            candidate_id=candidate.id,
            cv_document_id=doc.id,
            linked_by=actor.id,
            link_source="bulk",
        )
        db.add(link)
    else:
        link.cv_document_id = doc.id
        link.linked_by = actor.id
        link.link_source = "bulk"

    batch_items = db.scalars(
        select(UploadBatchItem).where(UploadBatchItem.document_id == doc.id)
    ).all()
    for item in batch_items:
        item.candidate_id = candidate.id

    return candidate


def _update_candidate(db: Session, doc: Document, parsed: ParsedCV) -> None:
    """
    Populate candidate profile columns from parsed CV.
    Only overwrites if value was previously null (don't stomp manually entered data).
    """
    cand = db.get(Candidate, doc.candidate_id)
    if cand is None or cand.organization_id != doc.organization_id:
        return

    changed = False

    if parsed.current_title and not cand.current_title:
        cand.current_title = parsed.current_title[:255]
        changed = True
    if parsed.location and not cand.location:
        cand.location = parsed.location[:255]
        changed = True
    if parsed.linkedin_url and not cand.linkedin_url:
        cand.linkedin_url = parsed.linkedin_url
        changed = True
    if parsed.email and not cand.email:
        cand.email = parsed.email[:320]
        changed = True
    if parsed.phone and not cand.phone:
        cand.phone = parsed.phone[:50]
        changed = True

    # Update domain tags (merge, don't replace)
    existing_tags: set[str] = set(cand.domain_tags or [])
    new_tags = existing_tags | set(parsed.domain_tags)
    if new_tags != existing_tags:
        cand.domain_tags = sorted(new_tags)
        changed = True

    # Store parsed CV dict in candidate.structured_json
    cand_meta: dict = dict(cand.structured_json or {})
    cand_meta["parsed_cv"] = parsed_cv_to_dict(parsed)
    cand.structured_json = cand_meta

    if changed:
        logger.info("[parsing] updated candidate=%s profile fields", cand.id)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post(
    "/api/documents/{doc_id}/parse",
    response_model=ParsedCVOut,
    summary="Parse structured fields from an extracted document",
)
def parse_single(
    doc_id: UUID,
    force: bool = False,
    user: User = Depends(require_writer),
    db: Session = Depends(get_db),
) -> ParsedCVOut:
    """
    Run structured extraction on a single document's extracted text.

    - Requires `upload_status = 'ready'` (i.e. Phase 2 extraction already done).
    - Skips if already parsed unless `?force=true`.
    - Updates candidate profile fields if a candidate record is linked.
    """
    doc = _get_org_doc(db, user, doc_id)

    if doc.upload_status not in ("ready", "parsed"):
        raise HTTPException(
            status_code=422,
            detail=f"Document must be extracted first (current status: {doc.upload_status}). "
                   "Run POST /api/documents/{doc_id}/extract first.",
        )

    if not force and _is_already_parsed(doc) and not _needs_candidate_link(db, doc):
        # Return stored result without re-running
        meta: dict = doc.structured_json or {}
        stored = meta.get("parsed_cv") or meta.get("parsed_jd") or {}
        doc_type = doc.document_type or "cv"
        return _build_out_from_stored(doc, stored, doc_type)

    return _run_parse(doc, db, user)


@router.post(
    "/api/batches/{batch_id}/parse",
    response_model=BatchParseSummary,
    summary="Parse all extracted documents in a batch",
)
def parse_batch(
    batch_id: UUID,
    force: bool = False,
    user: User = Depends(require_writer),
    db: Session = Depends(get_db),
) -> BatchParseSummary:
    """
    Run structured parsing for every extracted document in a batch.

    - Only documents with `upload_status = 'ready'` are processed.
    - Skips already-parsed documents unless `?force=true`.
    - Returns per-document parsed results.
    """
    batch = db.get(UploadBatch, batch_id)
    if batch is None or batch.organization_id != user.organization_id:
        raise HTTPException(status_code=404, detail="Batch not found")

    items = db.scalars(
        select(UploadBatchItem).where(UploadBatchItem.batch_id == batch_id)
    ).all()

    # Collect unique doc_ids
    seen: set[UUID] = set()
    doc_ids: list[UUID] = []
    for item in items:
        if item.document_id and item.document_id not in seen:
            doc_ids.append(item.document_id)
            seen.add(item.document_id)

    results_out: list[ParsedCVOut] = []
    parsed_count = skipped_no_text = skipped_already = failed_count = 0

    for doc_id in doc_ids:
        doc = db.get(Document, doc_id)
        if doc is None or doc.organization_id != user.organization_id:
            continue

        # Skip not-yet-extracted docs
        if doc.upload_status not in ("ready", "parsed"):
            skipped_no_text += 1
            continue

        # Skip already parsed unless forced
        if not force and _is_already_parsed(doc) and not _needs_candidate_link(db, doc):
            skipped_already += 1
            meta: dict = doc.structured_json or {}
            stored = meta.get("parsed_cv") or meta.get("parsed_jd") or {}
            results_out.append(_build_out_from_stored(doc, stored, doc.document_type or "cv"))
            continue

        result = _run_parse(doc, db, user)
        results_out.append(result)

        if result.parse_status == "parsed":
            parsed_count += 1
        elif result.parse_status == "no_text":
            skipped_no_text += 1
        else:
            failed_count += 1

    logger.info(
        "[parsing] batch=%s parsed=%d skipped_no_text=%d skipped_already=%d failed=%d",
        batch_id, parsed_count, skipped_no_text, skipped_already, failed_count,
    )

    return BatchParseSummary(
        batch_id=batch_id,
        total=len(doc_ids),
        parsed=parsed_count,
        skipped_no_text=skipped_no_text,
        skipped_already_parsed=skipped_already,
        failed=failed_count,
        results=results_out,
    )


@router.get(
    "/api/documents/{doc_id}/parsed",
    response_model=ParsedCVOut,
    summary="Get stored parsed structured data for a document",
)
def get_parsed(
    doc_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ParsedCVOut:
    """
    Return the stored Phase 3 parse result for a document.
    Does NOT re-run parsing. Use POST /parse to trigger.
    """
    doc = _get_org_doc(db, user, doc_id)
    meta: dict = doc.structured_json or {}
    doc_type = doc.document_type or "cv"
    stored = meta.get("parsed_cv") or meta.get("parsed_jd") or {}

    if not stored:
        raise HTTPException(
            status_code=404,
            detail="Document has not been parsed yet. "
                   "Run POST /api/documents/{doc_id}/parse first.",
        )

    return _build_out_from_stored(doc, stored, doc_type)


# ---------------------------------------------------------------------------
# Helper — rebuild ParsedCVOut from stored dict (avoids re-running pipeline)
# ---------------------------------------------------------------------------

def _build_out_from_stored(doc: Document, stored: dict, doc_type: str) -> ParsedCVOut:
    edu = [
        EducationOut(
            degree=e.get("degree", ""),
            field=e.get("field"),
            institution=e.get("institution"),
            year=e.get("year"),
        )
        for e in (stored.get("education") or [])
        if e.get("degree")
    ]
    return ParsedCVOut(
        document_id=doc.id,
        candidate_id=doc.candidate_id,
        linked_to_job=bool(doc.candidate_id and doc.job_posting_id),
        document_type=doc_type,
        original_filename=doc.original_filename,
        upload_status=doc.upload_status,
        parse_status="parsed",
        parse_method=stored.get("parse_method"),
        confidence=stored.get("confidence", 0.0),
        # CV fields
        full_name=stored.get("full_name"),
        email=stored.get("email"),
        phone=stored.get("phone"),
        linkedin_url=stored.get("linkedin_url"),
        github_url=stored.get("github_url"),
        location=stored.get("location"),
        current_title=stored.get("current_title"),
        total_experience_years=stored.get("total_experience_years"),
        summary=stored.get("summary"),
        skills=stored.get("skills") or [],
        education=edu,
        domain_tags=stored.get("domain_tags") or [],
        # JD fields
        job_title=stored.get("job_title"),
        experience_range=stored.get("experience_range"),
        minimum_qualification=stored.get("minimum_qualification"),
        required_skills=stored.get("required_skills") or [],
        jd_summary=stored.get("jd_summary"),
    )
