"""ATS settings, browse remote records, and import into local DB."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, List, Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

import requests

from ats.crypto import encrypt_api_key
from ats.factory import (
    SUPPORTED_PROVIDERS,
    get_provider,
    sanitize_config_for_response,
    validate_provider_config,
)
from ats.import_service import import_candidate, import_job
from auth.deps import get_current_user, get_db, require_admin, require_writer
from db.models import Organization, User
from routers.candidates import CandidateOut
from routers.job_postings import JobPostingOut

router = APIRouter(prefix="/api/ats", tags=["ats"])

AtsProviderName = Literal["demo", "custom"]


class AtsSettingsOut(BaseModel):
    provider: Optional[str] = None
    config: dict[str, Any] = Field(default_factory=dict)
    connected_at: Optional[datetime] = None
    is_connected: bool = False
    has_api_key: bool = False
    supported_providers: List[str] = Field(default_factory=lambda: list(SUPPORTED_PROVIDERS))


class AtsSettingsUpdate(BaseModel):
    provider: AtsProviderName
    config: dict[str, Any] = Field(default_factory=dict)
    api_key: Optional[str] = Field(
        None,
        description="Plaintext ATS API key. Encrypted at rest. Omit to keep existing key.",
    )
    clear_api_key: bool = False
    test: bool = True


class AtsTestOut(BaseModel):
    ok: bool
    provider: str
    message: str
    candidates: Optional[int] = None
    jobs: Optional[int] = None
    detail: dict[str, Any] = Field(default_factory=dict)


class AtsRemoteCandidateOut(BaseModel):
    external_id: str
    full_name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    has_cv_text: bool = False
    has_cv_url: bool = False
    already_imported: bool = False
    local_candidate_id: Optional[UUID] = None


class AtsRemoteJobOut(BaseModel):
    external_id: str
    job_title: str
    description: Optional[str] = None
    has_jd_text: bool = False
    has_jd_url: bool = False
    already_imported: bool = False
    local_job_posting_id: Optional[UUID] = None


class AtsJobDetailOut(BaseModel):
    external_id: str
    job_title: str
    description: Optional[str] = None
    jd_text: Optional[str] = None
    has_jd_url: bool = False
    already_imported: bool = False
    local_job_posting_id: Optional[UUID] = None


class AtsCandidateDetailOut(BaseModel):
    external_id: str
    full_name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    cv_text: Optional[str] = None
    has_cv_url: bool = False
    already_imported: bool = False
    local_candidate_id: Optional[UUID] = None
    parent_id: Optional[str] = None


class AtsJobsPageOut(BaseModel):
    items: List[AtsRemoteJobOut]
    page: int = 1
    page_size: int = 10
    total: Optional[int] = None
    total_pages: Optional[int] = None
    has_next: bool = False
    has_prev: bool = False


class AtsImportRequest(BaseModel):
    external_id: str = Field(..., min_length=1, max_length=255)
    parent_id: Optional[str] = Field(
        None,
        description="Parent job/requirement id when candidates are nested under a job",
    )


def _org(db: Session, user: User) -> Organization:
    org = db.get(Organization, user.organization_id)
    if org is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    return org


def _settings_out(org: Organization) -> AtsSettingsOut:
    provider = org.ats_provider
    return AtsSettingsOut(
        provider=provider,
        config=sanitize_config_for_response(org.ats_config),
        connected_at=org.ats_connected_at,
        is_connected=bool(provider),
        has_api_key=bool(getattr(org, "ats_api_key_encrypted", None)),
        supported_providers=list(SUPPORTED_PROVIDERS),
    )


@router.get("/settings", response_model=AtsSettingsOut)
def get_ats_settings(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Any org member can see whether ATS is connected (config for admin UI)."""
    return _settings_out(_org(db, user))


@router.put("/settings", response_model=AtsSettingsOut)
def update_ats_settings(
    body: AtsSettingsUpdate,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    org = _org(db, user)
    cfg = validate_provider_config(body.provider, body.config)
    org.ats_provider = body.provider
    org.ats_config = cfg

    if body.clear_api_key:
        org.ats_api_key_encrypted = None
    elif body.api_key is not None and str(body.api_key).strip():
        try:
            org.ats_api_key_encrypted = encrypt_api_key(str(body.api_key).strip())
        except Exception as ex:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to encrypt API key: {ex}",
            ) from ex

    if body.test:
        db.flush()
        try:
            result = get_provider(org).test_connection()
        except HTTPException:
            raise
        except ValueError as ve:
            raise HTTPException(status_code=400, detail=str(ve)) from ve
        if not result.get("ok", True):
            raise HTTPException(status_code=400, detail=result.get("message") or "ATS test failed")
        org.ats_connected_at = datetime.now(timezone.utc)
    else:
        org.ats_connected_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(org)
    return _settings_out(org)


@router.post("/test", response_model=AtsTestOut)
def test_ats_connection(
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    org = _org(db, user)
    if not org.ats_provider:
        raise HTTPException(status_code=400, detail="Configure ATS provider first")
    try:
        result = get_provider(org).test_connection()
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve)) from ve
    org.ats_connected_at = datetime.now(timezone.utc)
    db.commit()
    return AtsTestOut(
        ok=bool(result.get("ok", True)),
        provider=str(result.get("provider") or org.ats_provider),
        message=str(result.get("message") or "OK"),
        candidates=result.get("candidates"),
        jobs=result.get("jobs"),
        detail={k: v for k, v in result.items() if k not in ("ok", "message")},
    )


@router.post("/disconnect", response_model=AtsSettingsOut)
def disconnect_ats(
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    org = _org(db, user)
    org.ats_provider = None
    org.ats_config = {}
    org.ats_api_key_encrypted = None
    org.ats_connected_at = None
    db.commit()
    db.refresh(org)
    return _settings_out(org)


@router.get("/candidates", response_model=List[AtsRemoteCandidateOut])
def list_remote_candidates(
    q: Optional[str] = Query(None),
    request_id: Optional[str] = Query(
        None,
        description="Parent requirement/job id when candidates are nested under a job",
    ),
    user: User = Depends(require_writer),
    db: Session = Depends(get_db),
):
    from sqlalchemy import select
    from db.models import Candidate

    org = _org(db, user)
    provider = get_provider(org)
    try:
        remote = provider.list_candidates(q=q, parent_id=request_id)
    except TypeError:
        # Demo provider has no parent_id
        remote = provider.list_candidates(q=q)
    except ValueError as ve:
        raise HTTPException(status_code=502, detail=str(ve)) from ve

    ext_ids = [c.external_id for c in remote]
    imported = {}
    if ext_ids:
        rows = db.scalars(
            select(Candidate).where(
                Candidate.organization_id == org.id,
                Candidate.external_ats_id.in_(ext_ids),
                Candidate.deleted_at.is_(None),
            )
        ).all()
        imported = {r.external_ats_id: r.id for r in rows if r.external_ats_id}

    return [
        AtsRemoteCandidateOut(
            external_id=c.external_id,
            full_name=c.full_name,
            email=c.email,
            phone=c.phone,
            has_cv_text=bool(c.cv_text),
            has_cv_url=bool(c.cv_url),
            already_imported=c.external_id in imported,
            local_candidate_id=imported.get(c.external_id),
        )
        for c in remote
    ]


@router.get("/jobs", response_model=AtsJobsPageOut)
def list_remote_jobs(
    q: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    user: User = Depends(require_writer),
    db: Session = Depends(get_db),
):
    from sqlalchemy import select
    from db.models import JobPosting
    from ats.base import AtsJobsPage

    org = _org(db, user)
    provider = get_provider(org)
    try:
        remote = provider.list_jobs(q=q, page=page, page_size=page_size)
    except TypeError:
        # Older provider signature
        rows = provider.list_jobs(q=q)
        remote = AtsJobsPage(items=list(rows), page=1, page_size=len(rows), has_next=False)
    except ValueError as ve:
        raise HTTPException(status_code=502, detail=str(ve)) from ve

    items = remote.items if hasattr(remote, "items") else list(remote)
    ext_ids = [j.external_id for j in items]
    imported = {}
    if ext_ids:
        rows = db.scalars(
            select(JobPosting).where(
                JobPosting.organization_id == org.id,
                JobPosting.external_ats_id.in_(ext_ids),
                JobPosting.deleted_at.is_(None),
            )
        ).all()
        imported = {r.external_ats_id: r.id for r in rows if r.external_ats_id}

    out_items = [
        AtsRemoteJobOut(
            external_id=j.external_id,
            job_title=j.job_title,
            description=j.description,
            has_jd_text=bool(j.jd_text),
            has_jd_url=bool(j.jd_url),
            already_imported=j.external_id in imported,
            local_job_posting_id=imported.get(j.external_id),
        )
        for j in items
    ]
    if hasattr(remote, "items"):
        return AtsJobsPageOut(
            items=out_items,
            page=remote.page,
            page_size=remote.page_size,
            total=remote.total,
            total_pages=remote.total_pages,
            has_next=remote.has_next,
            has_prev=remote.has_prev,
        )
    return AtsJobsPageOut(items=out_items, page=1, page_size=len(out_items))


@router.get("/jobs/{external_id}", response_model=AtsJobDetailOut)
def get_remote_job(
    external_id: str,
    user: User = Depends(require_writer),
    db: Session = Depends(get_db),
):
    """Browse a remote ATS job without writing to the local DB."""
    from sqlalchemy import select
    from db.models import JobPosting

    org = _org(db, user)
    provider = get_provider(org)
    ext = external_id.strip()
    try:
        remote = provider.get_job(ext)
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve)) from ve

    local = db.scalars(
        select(JobPosting).where(
            JobPosting.organization_id == org.id,
            JobPosting.external_ats_id == remote.external_id,
            JobPosting.deleted_at.is_(None),
        )
    ).first()

    return AtsJobDetailOut(
        external_id=remote.external_id,
        job_title=remote.job_title,
        description=remote.description,
        jd_text=remote.jd_text,
        has_jd_url=bool(remote.jd_url),
        already_imported=local is not None,
        local_job_posting_id=local.id if local else None,
    )


@router.get("/candidates/{external_id}", response_model=AtsCandidateDetailOut)
def get_remote_candidate(
    external_id: str,
    request_id: Optional[str] = Query(
        None,
        description="Parent requirement/job id when candidates are nested under a job",
    ),
    user: User = Depends(require_writer),
    db: Session = Depends(get_db),
):
    """Browse a remote ATS candidate without writing to the local DB."""
    from sqlalchemy import select
    from db.models import Candidate
    from ats.import_service import _auth_headers, _download_bytes, _usable_extracted_text

    org = _org(db, user)
    provider = get_provider(org)
    ext = external_id.strip()
    parent = request_id.strip() if request_id else None
    try:
        if parent:
            remote = provider.get_candidate(ext, parent_id=parent)
        else:
            remote = provider.get_candidate(ext)
    except TypeError:
        remote = provider.get_candidate(ext)
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve)) from ve

    cv_text = remote.cv_text
    if not cv_text and remote.cv_url:
        try:
            content, mime = _download_bytes(
                remote.cv_url, headers=_auth_headers(provider)
            )
            decoded = content.decode("utf-8", errors="ignore")
            cv_text = _usable_extracted_text(
                decoded,
                mime=mime,
                filename=remote.cv_filename or "",
            ) or None
        except Exception:
            cv_text = None

    local = db.scalars(
        select(Candidate).where(
            Candidate.organization_id == org.id,
            Candidate.external_ats_id == remote.external_id,
            Candidate.deleted_at.is_(None),
        )
    ).first()

    return AtsCandidateDetailOut(
        external_id=remote.external_id,
        full_name=remote.full_name,
        email=remote.email,
        phone=remote.phone,
        cv_text=cv_text,
        has_cv_url=bool(remote.cv_url),
        already_imported=local is not None,
        local_candidate_id=local.id if local else None,
        parent_id=parent,
    )


@router.get("/jobs/{external_id}/file")
def preview_ats_job_file(
    external_id: str,
    user: User = Depends(require_writer),
    db: Session = Depends(get_db),
):
    """Proxy JD download so the browser can preview with our auth (ATS key stays server-side)."""
    org = _org(db, user)
    provider = get_provider(org)
    ext = external_id.strip()
    jd_url: Optional[str] = None
    filename = f"{ext}_jd"

    # Prefer resolved remote record (may include jd_download_url / filename)
    try:
        remote = provider.get_job(ext)
        jd_url = remote.jd_url
        if remote.jd_filename:
            filename = remote.jd_filename
    except ValueError:
        remote = None

    # Fallback: build from downloads.jd_path template
    if not jd_url:
        downloads = {}
        if isinstance(getattr(org, "ats_config", None), dict):
            downloads = dict((org.ats_config or {}).get("downloads") or {})
        path_tmpl = str(downloads.get("jd_path") or "/api/external/v1/requirements/{request_id}/jd")
        fill = getattr(provider, "_url", None)
        fill_path = path_tmpl.replace("{request_id}", ext).replace("{id}", ext)
        if callable(fill):
            jd_url = fill(fill_path)
        else:
            base = str((org.ats_config or {}).get("base_url") or "").rstrip("/")
            jd_url = f"{base}{fill_path if fill_path.startswith('/') else '/' + fill_path}"

    if not jd_url:
        raise HTTPException(status_code=404, detail="No JD file URL for this job")

    headers: dict[str, str] = {}
    fn = getattr(provider, "_headers", None)
    if callable(fn):
        headers = dict(fn())
    try:
        resp = requests.get(jd_url, headers=headers, timeout=30)
    except requests.RequestException as ex:
        raise HTTPException(status_code=502, detail=f"JD download failed: {ex}") from ex
    if resp.status_code >= 400:
        raise HTTPException(
            status_code=502,
            detail=f"ATS JD file not available (HTTP {resp.status_code}). The role may have no uploaded JD file.",
        )
    media = resp.headers.get("Content-Type") or "application/octet-stream"
    return Response(
        content=resp.content,
        media_type=media,
        headers={
            "Content-Disposition": f'inline; filename="{filename}"',
            "Cache-Control": "private, max-age=60",
        },
    )


@router.get("/candidates/{external_id}/file")
def preview_ats_candidate_file(
    external_id: str,
    request_id: Optional[str] = Query(None),
    user: User = Depends(require_writer),
    db: Session = Depends(get_db),
):
    """Proxy resume download for in-browser preview."""
    org = _org(db, user)
    provider = get_provider(org)
    try:
        try:
            remote = provider.get_candidate(external_id.strip(), parent_id=request_id)
        except TypeError:
            remote = provider.get_candidate(external_id.strip())
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve)) from ve
    if not remote.cv_url:
        raise HTTPException(status_code=404, detail="No resume URL for this candidate")
    headers = {}
    fn = getattr(provider, "_headers", None)
    if callable(fn):
        headers = dict(fn())
    try:
        resp = requests.get(remote.cv_url, headers=headers, timeout=30)
    except requests.RequestException as ex:
        raise HTTPException(status_code=502, detail=f"Resume download failed: {ex}") from ex
    if resp.status_code >= 400:
        raise HTTPException(status_code=502, detail=f"Resume download HTTP {resp.status_code}")
    filename = remote.cv_filename or f"{remote.external_id}_resume"
    media = resp.headers.get("Content-Type") or "application/octet-stream"
    return Response(
        content=resp.content,
        media_type=media,
        headers={
            "Content-Disposition": f'inline; filename="{filename}"',
            "Cache-Control": "private, max-age=60",
        },
    )


@router.post("/import/candidate", response_model=CandidateOut)
def import_ats_candidate(
    body: AtsImportRequest,
    user: User = Depends(require_writer),
    db: Session = Depends(get_db),
):
    org = _org(db, user)
    # parent_id used when provider needs it — import_service uses get_candidate
    row = import_candidate(db, user, org, body.external_id.strip(), parent_id=body.parent_id)
    return CandidateOut.model_validate(row)


@router.post("/import/job", response_model=JobPostingOut)
def import_ats_job(
    body: AtsImportRequest,
    user: User = Depends(require_writer),
    db: Session = Depends(get_db),
):
    org = _org(db, user)
    row = import_job(db, user, org, body.external_id.strip())
    return JobPostingOut.model_validate(row)
