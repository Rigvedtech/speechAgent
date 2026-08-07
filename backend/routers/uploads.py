"""Bulk CV upload under a JD — Phase 1 (file ingestion; extraction queued separately).

Endpoints
---------
POST /api/jobs/{job_id}/upload-cvs   — upload 1–50 CV files under a job posting
GET  /api/jobs/{job_id}/batches      — list upload batches for a job posting
GET  /api/batches/{batch_id}         — batch status + per-file item statuses (poll for progress)
"""

from __future__ import annotations

import hashlib
import io
import logging
import re
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

import config as app_config
from auth.deps import get_current_user, get_db, require_writer
from db.models import (
    Candidate,
    Document,
    JobCandidateMatch,
    JobPosting,
    UploadBatch,
    UploadBatchItem,
    User,
)
from document_store import uploads_root

logger = logging.getLogger(__name__)

router = APIRouter(tags=["uploads"])

# ---------------------------------------------------------------------------
# Module-level constants (resolved once at import time)
# ---------------------------------------------------------------------------

_MAX_FILE_BYTES: int = getattr(app_config, "DOCUMENT_MAX_BYTES", 20 * 1024 * 1024)
_MAX_FILES_PER_BATCH: int = getattr(app_config, "UPLOAD_MAX_FILES_PER_BATCH", 50)

_SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._\-]+")

# Magic byte signatures checked in order — first match wins.
# Format: (prefix_bytes, mime_type, canonical_extension)
_MAGIC_SIGNATURES: list[tuple[bytes, str, str]] = [
    (b"%PDF",              "application/pdf",                 ".pdf"),
    (b"PK\x03\x04",       "application/vnd.openxmlformats-officedocument.wordprocessingml.document", ".docx"),
    (b"\xd0\xcf\x11\xe0", "application/msword",              ".doc"),
    (b"\xff\xd8\xff",     "image/jpeg",                      ".jpg"),
    (b"\x89PNG",          "image/png",                       ".png"),
    (b"II*\x00",          "image/tiff",                      ".tiff"),
    (b"MM\x00*",          "image/tiff",                      ".tiff"),
    # BMP: first 2 bytes are 'BM'
    (b"BM",               "image/bmp",                       ".bmp"),
]

# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _safe_name(filename: str) -> str:
    """Sanitize filename: strip path traversal, replace unsafe chars, cap length."""
    base = Path(filename or "upload.bin").name
    cleaned = _SAFE_NAME_RE.sub("_", base).strip("._") or "upload.bin"
    return cleaned[:200]


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _unsupported_file(filename: str, reason: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail=(
            f"'{filename}' is not a valid supported document: {reason}. "
            "Accepted: PDF, DOC, DOCX, PNG, JPG, JPEG, TIFF, BMP, WEBP."
        ),
    )


def _validate_pdf(data: bytes, filename: str) -> None:
    try:
        import fitz

        with fitz.open(stream=data, filetype="pdf") as pdf:
            if pdf.needs_pass:
                raise _unsupported_file(filename, "password-protected PDFs are not supported")
            if pdf.page_count < 1:
                raise _unsupported_file(filename, "PDF contains no pages")
    except HTTPException:
        raise
    except Exception as exc:
        raise _unsupported_file(filename, f"corrupt PDF ({exc})") from exc


def _validate_docx(data: bytes, filename: str) -> None:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            names = set(archive.namelist())
            if "[Content_Types].xml" not in names or "word/document.xml" not in names:
                raise _unsupported_file(filename, "ZIP content is not a Word DOCX document")
            corrupt_member = archive.testzip()
            if corrupt_member:
                raise _unsupported_file(filename, f"corrupt DOCX member: {corrupt_member}")
    except HTTPException:
        raise
    except (OSError, zipfile.BadZipFile, RuntimeError) as exc:
        raise _unsupported_file(filename, f"corrupt DOCX ({exc})") from exc


def _validate_legacy_doc(data: bytes, filename: str) -> None:
    try:
        import olefile

        with olefile.OleFileIO(io.BytesIO(data)) as ole:
            if not ole.exists("WordDocument"):
                raise _unsupported_file(filename, "OLE content is not a Microsoft Word DOC file")
    except HTTPException:
        raise
    except Exception as exc:
        raise _unsupported_file(filename, f"corrupt DOC ({exc})") from exc


def _validate_image(data: bytes, filename: str) -> None:
    try:
        from PIL import Image

        with Image.open(io.BytesIO(data)) as image:
            image.verify()
    except Exception as exc:
        raise _unsupported_file(filename, f"corrupt image ({exc})") from exc


def _detect_mime(data: bytes, filename: str) -> tuple[str, str]:
    """
    Identify MIME type and canonical extension from magic bytes.

    Raises HTTPException(422) for unsupported or unrecognized file types.
    Returns (mime_type, canonical_extension).
    """
    header = data[:12]

    # Container formats need deeper validation than their shared signatures.
    if data[:1024].find(b"%PDF-") >= 0:
        _validate_pdf(data, filename)
        return "application/pdf", ".pdf"
    if header.startswith(b"PK\x03\x04"):
        _validate_docx(data, filename)
        return "application/vnd.openxmlformats-officedocument.wordprocessingml.document", ".docx"
    if header.startswith(b"\xd0\xcf\x11\xe0"):
        _validate_legacy_doc(data, filename)
        return "application/msword", ".doc"

    # Image magic bytes are followed by a full Pillow decode/verify.
    for prefix, mime, ext in _MAGIC_SIGNATURES:
        if header.startswith(prefix):
            _validate_image(data, filename)
            return mime, ext

    # WebP: RIFF????WEBP (bytes 0-3 = "RIFF", bytes 8-11 = "WEBP")
    if header[:4] == b"RIFF" and header[8:12] == b"WEBP":
        _validate_image(data, filename)
        return "image/webp", ".webp"

    raise _unsupported_file(filename, "file content does not match a supported format")


def _get_active_job(db: Session, user: User, job_id: UUID) -> JobPosting:
    """Return the job posting or raise 404 (enforces org scoping + soft-delete)."""
    row = db.get(JobPosting, job_id)
    if (
        row is None
        or row.organization_id != user.organization_id
        or row.deleted_at is not None
        or not row.is_active
    ):
        raise HTTPException(status_code=404, detail="Job posting not found")
    return row


def _require_ready_jd(db: Session, job: JobPosting) -> Optional[Document]:
    """Require stored JD text or a successfully processed JD document."""
    stored_jd_text = (job.jd_text or "").strip()
    if stored_jd_text:
        if not job.jd_document_id:
            return None
        linked_doc = db.get(Document, job.jd_document_id)
        if (
            linked_doc
            and linked_doc.organization_id == job.organization_id
            and linked_doc.job_posting_id == job.id
            and linked_doc.document_type == "jd"
        ):
            return linked_doc
        return None

    if not job.jd_document_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Add job description text or upload and process a JD before adding resumes.",
        )

    jd = db.get(Document, job.jd_document_id)
    is_linked_jd = bool(
        jd
        and jd.organization_id == job.organization_id
        and jd.job_posting_id == job.id
        and jd.document_type == "jd"
    )
    if (
        not is_linked_jd
        or job.pipeline_status != "ready"
        or jd.upload_status != "ready"
        or not (jd.extracted_text or "").strip()
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The job description must finish processing successfully before resumes can be uploaded.",
        )
    return jd


def _find_existing_doc(
    db: Session,
    org_id: UUID,
    job_id: UUID,
    content_hash: str,
) -> Optional[Document]:
    """
    Return an existing CV document with the same SHA-256 for this job.

    A separate Document row is retained when the same CV is submitted to a
    different job so every job-candidate link has an unambiguous document.
    Includes flushed-but-not-committed rows from the current session.
    """
    return db.scalars(
        select(Document).where(
            Document.organization_id == org_id,
            Document.job_posting_id == job_id,
            Document.document_type == "cv",
            Document.content_hash == content_hash,
        ).limit(1)
    ).first()


def _batch_dir(org_id: UUID, batch_id: UUID) -> Path:
    """Return (and create) the per-batch subdirectory under uploads root."""
    d = uploads_root() / str(org_id) / str(batch_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class UploadItemResult(BaseModel):
    original_filename: str
    document_id: UUID
    batch_item_id: UUID
    status: str          # "queued" | "skipped"
    is_duplicate: bool
    file_size_bytes: int
    mime_type: str


class BatchUploadResponse(BaseModel):
    batch_id: UUID
    job_posting_id: UUID
    total_files: int
    total_queued: int
    total_duplicate_skipped: int
    items: list[UploadItemResult]


class JdUploadResponse(BaseModel):
    job_posting_id: UUID
    document_id: UUID
    batch_id: UUID
    status: str
    is_duplicate: bool
    original_filename: str
    mime_type: str
    file_size_bytes: int


class BatchItemOut(BaseModel):
    id: UUID
    original_filename: Optional[str] = None
    file_size_bytes: Optional[int] = None
    mime_type: Optional[str] = None
    status: str
    document_id: Optional[UUID] = None
    error_message: Optional[str] = None
    created_at: datetime
    completed_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class BatchOut(BaseModel):
    id: UUID
    organization_id: UUID
    job_posting_id: Optional[UUID] = None
    batch_type: str
    status: str
    total_count: int
    success_count: int
    fail_count: int
    error_message: Optional[str] = None
    created_at: datetime
    completed_at: Optional[datetime] = None
    items: list[BatchItemOut] = []

    model_config = {"from_attributes": True}


class BatchSummaryOut(BaseModel):
    id: UUID
    job_posting_id: Optional[UUID] = None
    batch_type: str
    status: str
    total_count: int
    success_count: int
    fail_count: int
    created_at: datetime
    completed_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class JobResumeOut(BaseModel):
    document_id: UUID
    candidate_id: Optional[UUID] = None
    original_filename: Optional[str] = None
    file_size_bytes: Optional[int] = None
    mime_type: Optional[str] = None
    upload_status: str
    error_message: Optional[str] = None
    full_name: Optional[str] = None
    email: Optional[str] = None
    current_title: Optional[str] = None
    cv_text: Optional[str] = None
    created_at: datetime
    # JD ↔ CV match (null = unscored for this job)
    match_score: Optional[float] = None
    match_rank: Optional[int] = None
    match_scored_at: Optional[datetime] = None
    match_summary: Optional[str] = None
    match_reasons: Optional[dict[str, object]] = None
    match_breakdown: Optional[dict[str, object]] = None


def _plain_breakdown(raw: object) -> Optional[dict[str, object]]:
    """Coerce JSONB score_breakdown into JSON-safe floats for the UI."""
    if not isinstance(raw, dict):
        return None
    out: dict[str, object] = {}
    for key, value in raw.items():
        k = str(key)
        if isinstance(value, bool):
            out[k] = value
        elif isinstance(value, (int, float)):
            out[k] = float(value)
        elif isinstance(value, str):
            try:
                out[k] = float(value)
            except ValueError:
                out[k] = value
        elif isinstance(value, list):
            out[k] = [str(x) for x in value]
        elif isinstance(value, dict):
            nested = _plain_breakdown(value)
            out[k] = nested if nested is not None else value
        else:
            # Decimal / other numerics
            try:
                out[k] = float(value)  # type: ignore[arg-type]
            except (TypeError, ValueError):
                out[k] = value
    return out or None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post(
    "/api/jobs/{job_id}/upload-jd",
    response_model=JdUploadResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Upload the JD document for a job posting",
)
async def upload_job_description(
    job_id: UUID,
    file: UploadFile = File(..., description="One JD file (PDF, DOC, DOCX, or image)"),
    user: User = Depends(require_writer),
    db: Session = Depends(get_db),
) -> JdUploadResponse:
    """Upload one active JD version. Previous JD documents remain as history."""
    job = _get_active_job(db, user, job_id)
    raw_name = (file.filename or "job-description.bin").strip() or "job-description.bin"
    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="JD file is empty.",
        )
    if len(file_bytes) > _MAX_FILE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"JD file is too large. Maximum allowed: {_MAX_FILE_BYTES // (1024 * 1024)} MB.",
        )

    mime_type, canonical_ext = _detect_mime(file_bytes, raw_name)
    content_hash = _sha256(file_bytes)
    batch_id = uuid.uuid4()
    batch = UploadBatch(
        id=batch_id,
        organization_id=user.organization_id,
        created_by=user.id,
        batch_type="jd",
        job_posting_id=job.id,
        status="queued",
        total_count=1,
        success_count=0,
        fail_count=0,
    )
    db.add(batch)
    db.flush()

    current_doc = db.get(Document, job.jd_document_id) if job.jd_document_id else None
    is_duplicate = bool(
        current_doc
        and current_doc.organization_id == user.organization_id
        and current_doc.content_hash == content_hash
    )
    written_path: Optional[Path] = None

    try:
        if is_duplicate:
            document = current_doc
            item_status = "skipped"
            batch.status = "done"
            batch.success_count = 1
            batch.completed_at = datetime.now(timezone.utc)
            storage_path: Optional[str] = None
        else:
            document_id = uuid.uuid4()
            safe_name = _safe_name(raw_name)
            safe_stem = Path(safe_name).stem or "job-description"
            batch_dir = _batch_dir(user.organization_id, batch_id)
            written_path = batch_dir / f"{document_id}_{safe_stem}{canonical_ext}"
            written_path.write_bytes(file_bytes)
            storage_path = (
                f"{user.organization_id}/{batch_id}/{written_path.name}"
            )
            document = Document(
                id=document_id,
                organization_id=user.organization_id,
                uploaded_by=user.id,
                job_posting_id=job.id,
                document_type="jd",
                source="upload",
                original_filename=safe_name[:512],
                storage_path=storage_path,
                mime_type=mime_type[:127],
                file_size_bytes=len(file_bytes),
                upload_status="pending",
                content_hash=content_hash,
            )
            db.add(document)
            db.flush()
            job.jd_document_id = document.id
            job.content_hash = content_hash
            job.pipeline_status = "pending"
            item_status = "queued"

        batch_item = UploadBatchItem(
            id=uuid.uuid4(),
            batch_id=batch_id,
            original_filename=_safe_name(raw_name)[:512],
            storage_path=storage_path,
            mime_type=mime_type[:127],
            file_size_bytes=len(file_bytes),
            status=item_status,
            document_id=document.id,
            job_posting_id=job.id,
            completed_at=datetime.now(timezone.utc) if is_duplicate else None,
        )
        db.add(batch_item)
        db.commit()
    except Exception:
        db.rollback()
        if written_path:
            written_path.unlink(missing_ok=True)
        raise

    return JdUploadResponse(
        job_posting_id=job.id,
        document_id=document.id,
        batch_id=batch_id,
        status=item_status,
        is_duplicate=is_duplicate,
        original_filename=raw_name,
        mime_type=mime_type,
        file_size_bytes=len(file_bytes),
    )


@router.post(
    "/api/jobs/{job_id}/upload-cvs",
    response_model=BatchUploadResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Bulk upload CV files under a job posting",
    description=(
        "Upload 1–50 CV files for a specific job posting. "
        "Files are validated by magic bytes (not just extension). "
        "Duplicate files (same SHA-256 in this org) are detected and skipped "
        "without re-saving. Each accepted file gets a `documents` row "
        "(upload_status=pending) and an `upload_batch_items` row (status=queued). "
        "Returns immediately — extraction runs in background (Phase 4)."
    ),
)
async def bulk_upload_cvs(
    job_id: UUID,
    files: List[UploadFile] = File(
        ...,
        description=f"CV files to upload (max {_MAX_FILES_PER_BATCH} per request, max {_MAX_FILE_BYTES // (1024 * 1024)} MB each)",
    ),
    user: User = Depends(require_writer),
    db: Session = Depends(get_db),
) -> BatchUploadResponse:
    # ------------------------------------------------------------------
    # Step 1: Validate job ownership and JD readiness
    # ------------------------------------------------------------------
    job = _get_active_job(db, user, job_id)
    _require_ready_jd(db, job)
    org_id = user.organization_id

    # ------------------------------------------------------------------
    # Step 2: Validate file count upfront
    # ------------------------------------------------------------------
    if not files:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="No files provided.",
        )
    if len(files) > _MAX_FILES_PER_BATCH:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Too many files ({len(files)}). Maximum {_MAX_FILES_PER_BATCH} per request.",
        )

    # ------------------------------------------------------------------
    # Step 3: Read + validate ALL files before writing anything
    #         (fail fast — no partial uploads if one file is bad)
    # ------------------------------------------------------------------
    validated: list[dict] = []
    for upload in files:
        raw_name = (upload.filename or "upload.bin").strip() or "upload.bin"

        file_bytes = await upload.read()

        if not file_bytes:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"File '{raw_name}' is empty.",
            )
        if len(file_bytes) > _MAX_FILE_BYTES:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=(
                    f"File '{raw_name}' is too large "
                    f"({len(file_bytes) // (1024 * 1024)} MB). "
                    f"Maximum allowed: {_MAX_FILE_BYTES // (1024 * 1024)} MB."
                ),
            )

        # Detect and validate the real file type; extensions are not trusted.
        mime_type, canonical_ext = _detect_mime(file_bytes, raw_name)

        validated.append(
            {
                "raw_name": raw_name,
                "file_bytes": file_bytes,
                "mime_type": mime_type,
                "canonical_ext": canonical_ext,
                "content_hash": _sha256(file_bytes),
            }
        )

    # ------------------------------------------------------------------
    # Step 4: Create the UploadBatch row
    # ------------------------------------------------------------------
    batch_id = uuid.uuid4()
    batch = UploadBatch(
        id=batch_id,
        organization_id=org_id,
        created_by=user.id,
        batch_type="cv",
        job_posting_id=job.id,
        status="queued",
        total_count=len(validated),
        success_count=0,
        fail_count=0,
    )
    db.add(batch)
    db.flush()  # persist batch row so batch_items FK resolves

    # ------------------------------------------------------------------
    # Step 5: Process each file — dedup check, disk write, DB rows
    # ------------------------------------------------------------------
    batch_dir = _batch_dir(org_id, batch_id)
    written_paths: list[Path] = []  # track for rollback on unexpected failure

    results: list[UploadItemResult] = []
    seen_hashes: set[str] = set()   # within-batch dedup
    total_duplicate = 0

    try:
        for item in validated:
            content_hash: str = item["content_hash"]

            # Dedup: check within current batch + prior uploads in this org.
            # _find_existing_doc sees flushed-but-uncommitted rows (same session).
            existing_doc: Optional[Document] = _find_existing_doc(
                db, org_id, job.id, content_hash
            )
            is_duplicate = existing_doc is not None or content_hash in seen_hashes

            if is_duplicate:
                # Reuse existing document — no disk write, no new Document row.
                # existing_doc may be None if it was just flushed in this loop
                # (within-batch), so query again to get the flushed row.
                if existing_doc is None:
                    existing_doc = _find_existing_doc(
                        db, org_id, job.id, content_hash
                    )
                doc_id = existing_doc.id  # type: ignore[union-attr]
                total_duplicate += 1
                batch_item_status = "skipped"
                storage_path_for_item: Optional[str] = None
            else:
                # First occurrence of this hash — save to disk and create Document.
                seen_hashes.add(content_hash)
                safe_name = _safe_name(item["raw_name"])
                doc_uuid = uuid.uuid4()
                safe_stem = Path(safe_name).stem or "upload"
                disk_name = f"{doc_uuid}_{safe_stem}{item['canonical_ext']}"
                abs_path = batch_dir / disk_name
                abs_path.write_bytes(item["file_bytes"])
                written_paths.append(abs_path)

                rel_path = f"{org_id}/{batch_id}/{disk_name}"

                doc = Document(
                    id=doc_uuid,
                    organization_id=org_id,
                    uploaded_by=user.id,
                    document_type="cv",
                    source="bulk_upload",
                    original_filename=safe_name[:512],
                    storage_path=rel_path,
                    mime_type=item["mime_type"][:127],
                    file_size_bytes=len(item["file_bytes"]),
                    upload_status="pending",
                    content_hash=content_hash,
                    job_posting_id=job.id,
                )
                db.add(doc)
                db.flush()  # make this doc visible for subsequent dedup queries
                doc_id = doc.id
                batch_item_status = "queued"
                storage_path_for_item = rel_path

            # Create UploadBatchItem row for every file (duplicate or not)
            batch_item_id = uuid.uuid4()
            batch_item = UploadBatchItem(
                id=batch_item_id,
                batch_id=batch_id,
                original_filename=_safe_name(item["raw_name"])[:512],
                storage_path=storage_path_for_item,
                mime_type=item["mime_type"][:127],
                file_size_bytes=len(item["file_bytes"]),
                status=batch_item_status,
                document_id=doc_id,
                job_posting_id=job.id,
            )
            db.add(batch_item)

            results.append(
                UploadItemResult(
                    original_filename=item["raw_name"],
                    document_id=doc_id,
                    batch_item_id=batch_item_id,
                    status=batch_item_status,
                    is_duplicate=is_duplicate,
                    file_size_bytes=len(item["file_bytes"]),
                    mime_type=item["mime_type"],
                )
            )

    except Exception:
        # Clean up any files written to disk before this exception
        for p in written_paths:
            try:
                p.unlink(missing_ok=True)
            except OSError:
                pass
        raise

    # ------------------------------------------------------------------
    # Step 6: Commit everything atomically
    # ------------------------------------------------------------------
    db.commit()

    total_queued = len(validated) - total_duplicate
    logger.info(
        "[uploads] batch=%s job=%s org=%s user=%s files=%d queued=%d duplicates=%d",
        batch_id,
        job.id,
        org_id,
        user.email,
        len(validated),
        total_queued,
        total_duplicate,
    )

    return BatchUploadResponse(
        batch_id=batch_id,
        job_posting_id=job.id,
        total_files=len(validated),
        total_queued=total_queued,
        total_duplicate_skipped=total_duplicate,
        items=results,
    )


@router.get(
    "/api/jobs/{job_id}/resumes",
    response_model=list[JobResumeOut],
    summary="List resumes uploaded for a job posting",
)
def list_job_resumes(
    job_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[JobResumeOut]:
    """Return CV documents and parsed candidate details for one job."""
    _get_active_job(db, user, job_id)

    rows = db.execute(
        select(Document, Candidate)
        .outerjoin(Candidate, Candidate.id == Document.candidate_id)
        .where(
            Document.organization_id == user.organization_id,
            Document.job_posting_id == job_id,
            Document.document_type == "cv",
            Document.source != "ats",
        )
        .order_by(Document.created_at.desc())
    ).all()

    matches = {
        m.candidate_id: m
        for m in db.scalars(
            select(JobCandidateMatch).where(
                JobCandidateMatch.organization_id == user.organization_id,
                JobCandidateMatch.job_posting_id == job_id,
            )
        ).all()
    }

    def _score_on_ten(raw: object) -> Optional[float]:
        """Normalize stored score to 1–10 (legacy rows may still be 0–100)."""
        try:
            value = float(raw)
        except (TypeError, ValueError):
            return None
        if value > 10:
            value = value / 10.0
        return round(max(1.0, min(10.0, value)), 1)

    out: list[JobResumeOut] = []
    for document, candidate in rows:
        match = matches.get(candidate.id) if candidate else None
        reasons = match.reasons_json if match and isinstance(match.reasons_json, dict) else None
        # Same text source the scorer uses (candidate.cv_text, else document extract)
        candidate_cv = (candidate.cv_text or "").strip() if candidate else ""
        doc_cv = (document.extracted_text or "").strip()
        effective_cv = candidate_cv if len(candidate_cv) >= 40 else doc_cv
        out.append(
            JobResumeOut(
                document_id=document.id,
                candidate_id=document.candidate_id,
                original_filename=document.original_filename,
                file_size_bytes=document.file_size_bytes,
                mime_type=document.mime_type,
                upload_status=document.upload_status,
                error_message=document.error_message,
                full_name=candidate.full_name if candidate else None,
                email=candidate.email if candidate else None,
                current_title=candidate.current_title if candidate else None,
                cv_text=effective_cv or None,
                created_at=document.created_at,
                match_score=_score_on_ten(match.score) if match else None,
                match_rank=match.rank if match else None,
                match_scored_at=match.scored_at if match else None,
                match_summary=(reasons or {}).get("summary") if reasons else None,
                match_reasons=reasons,
                match_breakdown=_plain_breakdown(
                    match.score_breakdown if match else None
                ),
            )
        )
    # Scored first (highest), then unscored — keeps shortlist readable
    out.sort(
        key=lambda r: (
            0 if r.match_score is None else 1,
            r.match_score if r.match_score is not None else -1,
            r.created_at,
        ),
        reverse=True,
    )
    return out


@router.get(
    "/api/jobs/{job_id}/batches",
    response_model=list[BatchSummaryOut],
    summary="List CV upload batches for a job posting",
)
def list_job_batches(
    job_id: UUID,
    limit: int = Query(20, ge=1, le=100, description="Max number of batches to return"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[BatchSummaryOut]:
    """List upload batches for a job posting, newest first."""
    _get_active_job(db, user, job_id)

    rows = db.scalars(
        select(UploadBatch)
        .where(
            UploadBatch.organization_id == user.organization_id,
            UploadBatch.job_posting_id == job_id,
            UploadBatch.batch_type == "cv",
        )
        .order_by(UploadBatch.created_at.desc())
        .limit(limit)
    ).all()

    return [BatchSummaryOut.model_validate(r) for r in rows]


@router.get(
    "/api/batches/{batch_id}",
    response_model=BatchOut,
    summary="Get batch status and per-file progress",
)
def get_batch(
    batch_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BatchOut:
    """
    Poll this endpoint to track extraction progress.
    Returns batch-level status plus per-file item statuses.
    Frontend polls every 2–3 seconds until batch.status = 'done' or 'failed'.
    """
    batch = db.get(UploadBatch, batch_id)
    if batch is None or batch.organization_id != user.organization_id:
        raise HTTPException(status_code=404, detail="Batch not found")

    items = db.scalars(
        select(UploadBatchItem)
        .where(UploadBatchItem.batch_id == batch_id)
        .order_by(UploadBatchItem.created_at)
    ).all()

    return BatchOut(
        id=batch.id,
        organization_id=batch.organization_id,
        job_posting_id=batch.job_posting_id,
        batch_type=batch.batch_type,
        status=batch.status,
        total_count=batch.total_count,
        success_count=batch.success_count,
        fail_count=batch.fail_count,
        error_message=batch.error_message,
        created_at=batch.created_at,
        completed_at=batch.completed_at,
        items=[BatchItemOut.model_validate(i) for i in items],
    )
