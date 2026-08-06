"""
Extraction trigger and result endpoints — Phase 2.

Endpoints
---------
POST /api/batches/{batch_id}/extract     — extract all pending docs in a batch
POST /api/documents/{doc_id}/extract     — extract a single document (re-runnable)
GET  /api/documents/{doc_id}/extracted   — get extracted text + metadata
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from auth.deps import get_current_user, get_db, require_writer
from db.models import Document, UploadBatch, UploadBatchItem, User
from document_store import uploads_root
from services.text_extractor import ExtractionResult, extract_document

logger = logging.getLogger(__name__)

router = APIRouter(tags=["extraction"])


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class ExtractedTextOut(BaseModel):
    document_id: UUID
    original_filename: Optional[str] = None
    upload_status: str
    extraction_method: Optional[str] = None
    page_count: int = 0
    scanned_page_count: int = 0
    ocr_required: bool = False
    confidence: float = 0.0
    char_count: int = 0
    warnings: list[str] = []
    text_preview: Optional[str] = None   # first 500 chars
    extracted_text: Optional[str] = None  # full text (only when ?include_text=true)


class BatchExtractSummary(BaseModel):
    batch_id: UUID
    total: int
    extracted: int
    failed: int
    skipped_already_done: int
    results: list[ExtractedTextOut]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_org_document(db: Session, user: User, doc_id: UUID) -> Document:
    """Fetch document with org scoping check."""
    row = db.get(Document, doc_id)
    if row is None or row.organization_id != user.organization_id:
        raise HTTPException(status_code=404, detail="Document not found")
    return row


def _resolve_path(doc: Document) -> Path:
    """Turn the stored relative path into an absolute filesystem path."""
    if not doc.storage_path:
        raise HTTPException(
            status_code=422,
            detail=f"Document {doc.id} has no storage_path set.",
        )
    p = Path(doc.storage_path)
    if p.is_absolute():
        return p
    full = uploads_root() / p
    if not full.exists():
        raise HTTPException(
            status_code=422,
            detail=f"File not found on disk: {doc.storage_path}",
        )
    return full


def _run_extraction(doc: Document, db: Session) -> ExtractionResult:
    """
    Run the extraction pipeline on a single Document row.
    Updates document.upload_status, document.extracted_text in DB.
    """
    path = _resolve_path(doc)
    mime = doc.mime_type or "application/octet-stream"

    # Mark as processing
    doc.upload_status = "processing"
    db.commit()

    try:
        result = extract_document(path, mime)
    except Exception as exc:
        logger.error("[extraction] unexpected error doc=%s: %s", doc.id, exc)
        result = ExtractionResult(
            text="",
            warnings=[f"Unexpected extraction error: {exc}"],
            confidence=0.0,
        )

    # Persist result
    if result.text.strip():
        doc.extracted_text = result.text
        doc.upload_status = "ready"
        # Store extraction metadata in structured_json
        doc.structured_json = {
            "extraction_method": result.extraction_method,
            "page_count": result.page_count,
            "scanned_page_count": result.scanned_page_count,
            "ocr_required": result.ocr_required,
            "confidence": result.confidence,
            "char_count": len(result.text),
            "warnings": result.warnings,
        }
    else:
        doc.upload_status = "needs_review" if result.ocr_required else "failed"
        doc.error_message = "; ".join(result.warnings)[:500] if result.warnings else "No text extracted"
        doc.structured_json = {
            "extraction_method": result.extraction_method,
            "confidence": result.confidence,
            "warnings": result.warnings,
        }

    db.commit()
    db.refresh(doc)
    return result


def _doc_to_out(doc: Document, result: ExtractionResult, include_text: bool = False) -> ExtractedTextOut:
    meta: dict = doc.structured_json or {}
    text = result.text or ""
    return ExtractedTextOut(
        document_id=doc.id,
        original_filename=doc.original_filename,
        upload_status=doc.upload_status,
        extraction_method=meta.get("extraction_method", result.extraction_method),
        page_count=meta.get("page_count", result.page_count),
        scanned_page_count=meta.get("scanned_page_count", result.scanned_page_count),
        ocr_required=meta.get("ocr_required", result.ocr_required),
        confidence=meta.get("confidence", result.confidence),
        char_count=len(text),
        warnings=result.warnings,
        text_preview=text[:500] if text else None,
        extracted_text=text if include_text else None,
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post(
    "/api/batches/{batch_id}/extract",
    response_model=BatchExtractSummary,
    summary="Extract text from all pending documents in a batch",
)
def extract_batch(
    batch_id: UUID,
    user: User = Depends(require_writer),
    db: Session = Depends(get_db),
) -> BatchExtractSummary:
    """
    Trigger synchronous extraction for every document in a batch that has
    upload_status = 'pending'.

    Already extracted documents (status = 'ready') are skipped.
    Returns per-document results and a batch summary.

    Note: This runs synchronously in the request. For large batches (>10 files),
    Phase 4 will replace this with an async Celery/ARQ worker.
    """
    batch = db.get(UploadBatch, batch_id)
    if batch is None or batch.organization_id != user.organization_id:
        raise HTTPException(status_code=404, detail="Batch not found")

    # Fetch all batch items
    items = db.scalars(
        select(UploadBatchItem).where(UploadBatchItem.batch_id == batch_id)
    ).all()

    if not items:
        raise HTTPException(status_code=422, detail="Batch has no items.")

    batch.status = "processing"
    db.commit()

    # Collect unique document_ids (duplicate-skipped items share a doc_id)
    seen_doc_ids: set[UUID] = set()
    doc_ids: list[UUID] = []
    for item in items:
        if item.document_id and item.document_id not in seen_doc_ids:
            doc_ids.append(item.document_id)
            seen_doc_ids.add(item.document_id)

    results_out: list[ExtractedTextOut] = []
    extracted = 0
    failed = 0
    skipped = 0

    for doc_id in doc_ids:
        doc = db.get(Document, doc_id)
        if doc is None or doc.organization_id != user.organization_id:
            continue

        if doc.upload_status == "ready":
            # Already extracted — skip
            skipped += 1
            for item in items:
                if item.document_id == doc.id and item.status != "skipped":
                    item.status = "ready"
                    item.completed_at = datetime.now(timezone.utc)
            results_out.append(
                ExtractedTextOut(
                    document_id=doc.id,
                    original_filename=doc.original_filename,
                    upload_status=doc.upload_status,
                    extraction_method=(doc.structured_json or {}).get("extraction_method"),
                    page_count=(doc.structured_json or {}).get("page_count", 0),
                    scanned_page_count=(doc.structured_json or {}).get("scanned_page_count", 0),
                    ocr_required=(doc.structured_json or {}).get("ocr_required", False),
                    confidence=(doc.structured_json or {}).get("confidence", 1.0),
                    char_count=len(doc.extracted_text or ""),
                    warnings=[],
                    text_preview=(doc.extracted_text or "")[:500] or None,
                )
            )
            continue

        logger.info("[extraction] extracting doc=%s file=%s", doc.id, doc.original_filename)
        for item in items:
            if item.document_id == doc.id and item.status != "skipped":
                item.status = "processing"
        db.commit()
        result = _run_extraction(doc, db)

        if doc.upload_status == "ready":
            extracted += 1
            item_status = "ready"
        else:
            failed += 1
            item_status = "failed"

        for item in items:
            if item.document_id == doc.id and item.status != "skipped":
                item.status = item_status
                item.error_message = doc.error_message if item_status == "failed" else None
                item.completed_at = datetime.now(timezone.utc)

        results_out.append(_doc_to_out(doc, result, include_text=False))

    # Update batch status
    batch.success_count = sum(1 for item in items if item.status in {"ready", "skipped"})
    batch.fail_count = sum(1 for item in items if item.status == "failed")
    if failed == 0:
        batch.status = "done"
    elif extracted + skipped == 0:
        batch.status = "failed"
    else:
        batch.status = "done"  # partial success counts as done
    batch.completed_at = datetime.now(timezone.utc)
    db.commit()

    logger.info(
        "[extraction] batch=%s done: extracted=%d skipped=%d failed=%d",
        batch_id, extracted, skipped, failed,
    )

    return BatchExtractSummary(
        batch_id=batch_id,
        total=len(doc_ids),
        extracted=extracted,
        failed=failed,
        skipped_already_done=skipped,
        results=results_out,
    )


@router.post(
    "/api/documents/{doc_id}/extract",
    response_model=ExtractedTextOut,
    summary="Extract (or re-extract) text from a single document",
)
def extract_single(
    doc_id: UUID,
    include_text: bool = False,
    user: User = Depends(require_writer),
    db: Session = Depends(get_db),
) -> ExtractedTextOut:
    """
    Run extraction on a single document. Can be called multiple times
    (e.g. after fixing a corrupt file or to re-extract with a newer pipeline).

    Set ?include_text=true to get the full extracted text in the response.
    """
    doc = _get_org_document(db, user, doc_id)
    result = _run_extraction(doc, db)
    return _doc_to_out(doc, result, include_text=include_text)


@router.get(
    "/api/documents/{doc_id}/extracted",
    response_model=ExtractedTextOut,
    summary="Get extracted text and metadata for a document",
)
def get_extracted(
    doc_id: UUID,
    include_text: bool = False,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ExtractedTextOut:
    """
    Return the stored extraction result for a document.
    Does NOT re-run extraction. Use POST /extract to trigger.

    Set ?include_text=true to include the full extracted text.
    """
    doc = _get_org_document(db, user, doc_id)
    meta: dict = doc.structured_json or {}

    return ExtractedTextOut(
        document_id=doc.id,
        original_filename=doc.original_filename,
        upload_status=doc.upload_status,
        extraction_method=meta.get("extraction_method"),
        page_count=meta.get("page_count", 0),
        scanned_page_count=meta.get("scanned_page_count", 0),
        ocr_required=meta.get("ocr_required", False),
        confidence=meta.get("confidence", 0.0),
        char_count=len(doc.extracted_text or ""),
        warnings=meta.get("warnings", []),
        text_preview=(doc.extracted_text or "")[:500] or None,
        extracted_text=doc.extracted_text if include_text else None,
    )
