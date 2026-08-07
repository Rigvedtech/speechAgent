"""Coding round APIs: task bank, interview config, submit, and demo sessions."""

from __future__ import annotations

import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, List, Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

import config as app_config
from auth.deps import get_current_user, get_db, require_writer
from db.models import (
    CodingDomain,
    CodingSubmission,
    CodingTask,
    InterviewCodingConfig,
    InterviewSession,
    User,
)
from services.coding_languages import (
    SUPPORTED_LANGUAGES,
    language_entry,
    languages_for_api,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/coding", tags=["coding"])

MAX_PROBLEMS_PER_DOMAIN = 5
SEED_TASK_IDS = [
    UUID("a1111111-1111-4111-8111-111111111101"),
    UUID("a1111111-1111-4111-8111-111111111102"),
    UUID("a1111111-1111-4111-8111-111111111103"),
]
SEED_DOMAIN_IDS = {
    "python": UUID("b1111111-1111-4111-8111-111111111101"),
    "javascript": UUID("b1111111-1111-4111-8111-111111111102"),
}


# ── Schemas ──────────────────────────────────────────────────────────────────


class CodingExample(BaseModel):
    input: str
    output: str
    explanation: Optional[str] = None


class CodingTaskSummary(BaseModel):
    id: UUID
    slug: str
    title: str
    difficulty: str
    skill_tags: List[str]
    allowed_languages: List[str]
    domain_id: Optional[UUID] = None
    is_org_owned: bool = False
    estimated_time_min: int = 25


class CodingTaskDetail(CodingTaskSummary):
    statement: str
    examples: List[CodingExample]
    constraints_text: str
    starter_code: dict[str, str]
    entry_function: Optional[str] = None


class CodingDomainOut(BaseModel):
    id: UUID
    slug: str
    name: str
    language: str
    description: str
    is_active: bool
    problem_count: int = 0
    max_problems: int = MAX_PROBLEMS_PER_DOMAIN
    can_generate: bool = True
    is_org_owned: bool = False


class CodingDomainCreateIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    language: str
    description: str = ""

    @field_validator("language")
    @classmethod
    def normalize_language(cls, value: str) -> str:
        lang = (value or "").strip().lower()
        if lang not in SUPPORTED_LANGUAGES:
            raise ValueError(f"Unsupported language: {lang}")
        return lang

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        name = (value or "").strip()
        if len(name) < 2:
            raise ValueError("name too short")
        return name


class InterviewCodingConfigIn(BaseModel):
    enabled: bool = False
    domain_id: Optional[UUID] = None
    allowed_languages: List[str] = Field(default_factory=lambda: ["python", "javascript"])
    default_language: str = "python"
    task_ids: List[UUID] = Field(default_factory=list, max_length=5)
    assigned_task_id: Optional[UUID] = None
    time_limit_min: int = Field(default=25, ge=5, le=180)
    # task_id string -> minutes (recruiter override; AI estimate used as default in UI)
    task_time_limits: dict[str, int] = Field(default_factory=dict)

    @field_validator("allowed_languages")
    @classmethod
    def validate_languages(cls, values: List[str]) -> List[str]:
        cleaned = []
        for raw in values:
            lang = (raw or "").strip().lower()
            if not lang:
                continue
            if lang not in SUPPORTED_LANGUAGES:
                raise ValueError(f"Unsupported language: {lang}")
            if lang not in cleaned:
                cleaned.append(lang)
        if not cleaned:
            raise ValueError("allowed_languages cannot be empty")
        return cleaned

    @field_validator("default_language")
    @classmethod
    def normalize_default_language(cls, value: str) -> str:
        lang = (value or "").strip().lower()
        if lang not in SUPPORTED_LANGUAGES:
            raise ValueError(f"Unsupported default_language: {lang}")
        return lang

    @field_validator("task_time_limits")
    @classmethod
    def validate_task_time_limits(cls, values: dict[str, int]) -> dict[str, int]:
        cleaned: dict[str, int] = {}
        for key, raw in (values or {}).items():
            try:
                minutes = int(raw)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"Invalid time limit for task {key}") from exc
            if minutes < 5 or minutes > 180:
                raise ValueError(f"time limit for task {key} must be between 5 and 180")
            cleaned[str(key)] = minutes
        return cleaned


class InterviewCodingConfigOut(BaseModel):
    interview_id: UUID
    enabled: bool
    domain_id: Optional[UUID] = None
    allowed_languages: List[str]
    default_language: str
    task_ids: List[UUID]
    assigned_task_id: Optional[UUID]
    time_limit_min: int
    task_time_limits: dict[str, int] = Field(default_factory=dict)
    coding_uri: Optional[str] = None
    wrapup_message: Optional[str] = None


class CodingAssignedTaskProgress(BaseModel):
    task_id: UUID
    title: str
    difficulty: str
    time_limit_min: int
    status: str  # pending | draft | submitted
    is_current: bool = False


class CodingWorkspace(BaseModel):
    files: dict[str, str] = Field(default_factory=dict)
    activePath: str = "main.py"
    entryPath: str = "main.py"


class CodingSessionOut(BaseModel):
    interview_id: Optional[UUID] = None
    bot_id: Optional[str] = None
    demo_token: Optional[str] = None
    access_token: Optional[str] = None
    enabled: bool = True
    language: str
    allowed_languages: List[str]
    language_locked: bool = True
    domain_id: Optional[UUID] = None
    domain_name: Optional[str] = None
    time_limit_min: int
    started_at: Optional[datetime] = None
    ends_at: Optional[datetime] = None
    task: CodingTaskDetail
    submission_status: str = "draft"
    code: str = ""
    workspace: CodingWorkspace = Field(default_factory=CodingWorkspace)
    coding_uri: Optional[str] = None
    task_index: int = 1
    task_count: int = 1
    has_next_task: bool = False
    assigned_tasks: List[CodingAssignedTaskProgress] = Field(default_factory=list)


class CodingSubmitIn(BaseModel):
    language: str
    code: str = Field(default="")
    status: Literal["draft", "submitted"] = "submitted"
    workspace: Optional[CodingWorkspace] = None

    @field_validator("language")
    @classmethod
    def normalize_language(cls, value: str) -> str:
        lang = (value or "").strip().lower()
        if lang not in SUPPORTED_LANGUAGES:
            raise ValueError(f"Unsupported language: {lang}")
        return lang

    @field_validator("code")
    @classmethod
    def strip_code(cls, value: str) -> str:
        return value if value is not None else ""


class CodingSubmitOut(BaseModel):
    id: UUID
    status: str
    language: str
    submitted_at: Optional[datetime]
    task_id: UUID
    interview_id: Optional[UUID] = None
    demo_token: Optional[str] = None
    has_next_task: bool = False
    next_task_id: Optional[UUID] = None
    task_index: int = 1
    task_count: int = 1


class DemoStartIn(BaseModel):
    task_id: Optional[UUID] = None
    domain_id: Optional[UUID] = None
    language: Optional[str] = None

    @field_validator("language")
    @classmethod
    def normalize_language(cls, value: Optional[str]) -> Optional[str]:
        if value is None or value == "":
            return None
        lang = value.strip().lower()
        if lang not in SUPPORTED_LANGUAGES:
            raise ValueError(f"Unsupported language: {lang}")
        return lang


class CodingRunIn(BaseModel):
    language: str
    code: str = ""
    stdin: str = ""
    timeout_sec: float = Field(default=5.0, ge=1.0, le=15.0)
    workspace: Optional[CodingWorkspace] = None

    @field_validator("language")
    @classmethod
    def normalize_language(cls, value: str) -> str:
        lang = (value or "").strip().lower()
        if lang not in SUPPORTED_LANGUAGES:
            raise ValueError(f"Unsupported language: {lang}")
        return lang


class CodingRunOut(BaseModel):
    ok: bool
    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool
    language: str
    error: Optional[str] = None


class CodingRunExamplesIn(BaseModel):
    language: str
    code: str = ""
    task_id: UUID
    timeout_sec: float = Field(default=5.0, ge=1.0, le=15.0)
    workspace: Optional[CodingWorkspace] = None

    @field_validator("language")
    @classmethod
    def normalize_language(cls, value: str) -> str:
        lang = (value or "").strip().lower()
        if lang not in SUPPORTED_LANGUAGES:
            raise ValueError(f"Unsupported language: {lang}")
        return lang


class CodingExampleRunResult(BaseModel):
    index: int
    input: str
    expected: str
    actual: str
    stderr: str
    exit_code: int
    timed_out: bool
    passed: bool
    error: Optional[str] = None


class CodingComplexityOut(BaseModel):
    time: str
    space: str
    note: str = ""
    confidence: str = "medium"


class CodingRunExamplesOut(BaseModel):
    passed: int
    total: int
    all_passed: bool
    results: List[CodingExampleRunResult]
    complexity: Optional[CodingComplexityOut] = None


# ── Helpers ───────────────────────────────────────────────────────────────────


def _frontend_base() -> str:
    configured = (getattr(app_config, "FRONTEND_BASE_URL", "") or "").strip().rstrip("/")
    if configured:
        return configured
    origins = getattr(app_config, "CORS_ORIGINS", None) or []
    for origin in origins:
        o = (origin or "").strip().rstrip("/")
        if o and "localhost" in o:
            return o
    for origin in origins:
        o = (origin or "").strip().rstrip("/")
        if o:
            return o
    return "http://localhost:5173"


def _coding_uri_for_token(token: str) -> str:
    """Candidate-only public URI (no recruiter shell / navbar)."""
    return f"{_frontend_base()}/c/{token}"


def _wrapup_message(coding_uri: str) -> str:
    return (
        "Thank you for the interview. Let's wrap up now. "
        "We are sharing one link with you — please open it and complete the coding task. "
        f"Your coding task link is: {coding_uri}"
    )


def _default_workspace(language: str, starter: str) -> CodingWorkspace:
    entry = language_entry(language)
    return CodingWorkspace(
        files={entry: starter or ""},
        activePath=entry,
        entryPath=entry,
    )


def _workspace_from_row(row: CodingSubmission, language: str) -> CodingWorkspace:
    raw = row.workspace_json if isinstance(row.workspace_json, dict) else {}
    files = raw.get("files") if isinstance(raw.get("files"), dict) else None
    if files:
        return CodingWorkspace(
            files={str(k): str(v) for k, v in files.items()},
            activePath=str(raw.get("activePath") or next(iter(files.keys()))),
            entryPath=str(raw.get("entryPath") or next(iter(files.keys()))),
        )
    return _default_workspace(language, row.code or "")


def _workspace_to_json(workspace: CodingWorkspace) -> dict:
    return {
        "files": dict(workspace.files or {}),
        "activePath": workspace.activePath,
        "entryPath": workspace.entryPath,
    }


def _active_code(workspace: CodingWorkspace) -> str:
    if workspace.activePath in workspace.files:
        return workspace.files[workspace.activePath]
    if workspace.entryPath in workspace.files:
        return workspace.files[workspace.entryPath]
    if workspace.files:
        return next(iter(workspace.files.values()))
    return ""


def _task_visible_to_org(task: CodingTask, org_id: UUID) -> bool:
    return task.organization_id is None or task.organization_id == org_id


def _estimated_time_for_task(task: CodingTask) -> int:
    raw = getattr(task, "estimated_time_min", None)
    try:
        minutes = int(raw) if raw is not None else 25
    except (TypeError, ValueError):
        minutes = 25
    return max(5, min(180, minutes))


def _difficulty_default_minutes(difficulty: str) -> int:
    d = (difficulty or "medium").strip().lower()
    if d == "easy":
        return 15
    if d == "hard":
        return 45
    return 25


def _clamp_estimated_minutes(raw: Any, difficulty: str = "medium") -> int:
    try:
        minutes = int(raw)
    except (TypeError, ValueError):
        minutes = _difficulty_default_minutes(difficulty)
    return max(5, min(180, minutes))


def _task_to_summary(task: CodingTask) -> CodingTaskSummary:
    return CodingTaskSummary(
        id=task.id,
        slug=task.slug,
        title=task.title,
        difficulty=task.difficulty,
        skill_tags=list(task.skill_tags or []),
        allowed_languages=list(task.allowed_languages or []),
        domain_id=task.domain_id,
        is_org_owned=task.organization_id is not None,
        estimated_time_min=_estimated_time_for_task(task),
    )


def _task_time_limits_map(cfg: InterviewCodingConfig) -> dict[str, int]:
    raw = getattr(cfg, "task_time_limits_json", None) or {}
    if not isinstance(raw, dict):
        return {}
    out: dict[str, int] = {}
    for key, val in raw.items():
        try:
            minutes = int(val)
        except (TypeError, ValueError):
            continue
        out[str(key)] = max(5, min(180, minutes))
    return out


def _time_limit_for_task(
    cfg: InterviewCodingConfig,
    task_id: UUID,
    *,
    task: Optional[CodingTask] = None,
) -> int:
    limits = _task_time_limits_map(cfg)
    key = str(task_id)
    if key in limits:
        return limits[key]
    if task is not None:
        return _estimated_time_for_task(task)
    if cfg.assigned_task_id == task_id and cfg.time_limit_min:
        return int(cfg.time_limit_min)
    return int(cfg.time_limit_min or 30)


def _ordered_task_ids(cfg: InterviewCodingConfig) -> List[UUID]:
    ids = list(cfg.task_ids or [])
    if cfg.assigned_task_id and cfg.assigned_task_id not in ids:
        ids = [cfg.assigned_task_id, *ids]
    return ids


def _normalize_task_time_limits(
    task_ids: List[UUID],
    raw_limits: dict[str, int],
    tasks_by_id: dict[UUID, CodingTask],
) -> dict[str, int]:
    out: dict[str, int] = {}
    for task_id in task_ids:
        key = str(task_id)
        if key in raw_limits:
            out[key] = max(5, min(180, int(raw_limits[key])))
        else:
            task = tasks_by_id.get(task_id)
            out[key] = (
                _estimated_time_for_task(task)
                if task is not None
                else 25
            )
    return out


def _task_to_detail(task: CodingTask) -> CodingTaskDetail:
    examples_raw = task.examples_json or []
    examples: List[CodingExample] = []
    if isinstance(examples_raw, list):
        for item in examples_raw:
            if not isinstance(item, dict):
                continue
            examples.append(
                CodingExample(
                    input=str(item.get("input", "")),
                    output=str(item.get("output", "")),
                    explanation=(
                        str(item["explanation"])
                        if item.get("explanation") is not None
                        else None
                    ),
                )
            )
    starter = task.starter_code_json or {}
    starter_code = {
        str(k): str(v) for k, v in starter.items() if isinstance(k, str) and v is not None
    }
    summary = _task_to_summary(task)
    return CodingTaskDetail(
        **summary.model_dump(),
        statement=task.statement,
        examples=examples,
        constraints_text=task.constraints_text or "",
        starter_code=starter_code,
        entry_function=task.entry_function,
    )


def _get_task_for_org(db: Session, user: User, task_id: UUID) -> CodingTask:
    task = db.get(CodingTask, task_id)
    if task is None or not task.is_active or not _task_visible_to_org(task, user.organization_id):
        raise HTTPException(status_code=404, detail="Coding task not found")
    return task


def _get_org_interview(db: Session, user: User, interview_id: UUID) -> InterviewSession:
    row = db.get(InterviewSession, interview_id)
    if row is None or row.organization_id != user.organization_id:
        raise HTTPException(status_code=404, detail="Interview not found")
    return row


def _resolve_interview_by_bot_or_id(
    db: Session,
    user: User,
    *,
    bot_id: Optional[str] = None,
    interview_id: Optional[UUID] = None,
) -> InterviewSession:
    if interview_id is not None:
        return _get_org_interview(db, user, interview_id)
    if not bot_id:
        raise HTTPException(status_code=400, detail="bot_id or interview_id is required")
    try:
        bot_uuid = UUID(str(bot_id).strip())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid bot_id") from exc
    row = db.scalar(
        select(InterviewSession).where(
            InterviewSession.bot_id == bot_uuid,
            InterviewSession.organization_id == user.organization_id,
        )
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Interview not found for bot_id")
    return row


def _validate_config_tasks(
    db: Session,
    user: User,
    body: InterviewCodingConfigIn,
) -> None:
    if not body.enabled:
        return

    task_ids = list(body.task_ids or [])
    if body.assigned_task_id is not None and body.assigned_task_id not in task_ids:
        task_ids.insert(0, body.assigned_task_id)
    # Deduplicate while preserving order
    seen: set[UUID] = set()
    ordered: List[UUID] = []
    for tid in task_ids:
        if tid not in seen:
            seen.add(tid)
            ordered.append(tid)
    task_ids = ordered

    if not task_ids:
        raise HTTPException(
            status_code=400,
            detail="Select at least one coding task when coding is enabled",
        )
    if len(task_ids) > MAX_PROBLEMS_PER_DOMAIN:
        raise HTTPException(
            status_code=400,
            detail=f"At most {MAX_PROBLEMS_PER_DOMAIN} tasks can be assigned",
        )

    domain = None
    if body.domain_id is not None:
        domain = _get_domain_for_org(db, user, body.domain_id)
        # Lock interview to this domain's single language — candidate cannot switch.
        body.allowed_languages = [domain.language]
        body.default_language = domain.language

    if body.default_language not in body.allowed_languages:
        raise HTTPException(
            status_code=400,
            detail="default_language must be included in allowed_languages",
        )

    tasks_by_id: dict[UUID, CodingTask] = {}
    for task_id in task_ids:
        task = _get_task_for_org(db, user, task_id)
        tasks_by_id[task_id] = task
        if domain is not None and task.domain_id and task.domain_id != domain.id:
            raise HTTPException(
                status_code=400,
                detail=f"Task '{task.title}' is not in the selected domain",
            )
        overlap = set(task.allowed_languages or []) & set(body.allowed_languages)
        if not overlap:
            raise HTTPException(
                status_code=400,
                detail=f"Task '{task.title}' does not support selected languages",
            )

    limits = _normalize_task_time_limits(
        task_ids, body.task_time_limits or {}, tasks_by_id
    )
    body.task_ids = task_ids
    body.assigned_task_id = task_ids[0]
    body.task_time_limits = limits
    body.time_limit_min = limits[str(task_ids[0])]


def upsert_interview_coding_config(
    db: Session,
    user: User,
    interview_id: UUID,
    body: InterviewCodingConfigIn,
) -> InterviewCodingConfig:
    """Create/update coding config for an interview (used by schedule + dedicated API)."""
    _get_org_interview(db, user, interview_id)
    _validate_config_tasks(db, user, body)

    row = db.scalar(
        select(InterviewCodingConfig).where(
            InterviewCodingConfig.interview_id == interview_id
        )
    )
    if row is None:
        row = InterviewCodingConfig(interview_id=interview_id)
        db.add(row)

    row.enabled = bool(body.enabled)
    row.domain_id = body.domain_id if body.enabled else None
    row.allowed_languages = list(body.allowed_languages)
    row.default_language = body.default_language
    row.task_ids = list(body.task_ids or []) if body.enabled else []
    row.assigned_task_id = body.assigned_task_id if body.enabled else None
    row.time_limit_min = int(body.time_limit_min)
    row.task_time_limits_json = dict(body.task_time_limits or {}) if body.enabled else {}
    if body.enabled:
        if not row.access_token:
            row.access_token = secrets.token_urlsafe(24)
        _ensure_interview_submissions(db, user, interview_id=interview_id, cfg=row)
    row.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(row)
    return row


def _ensure_submission_for_task(
    db: Session,
    user: User,
    *,
    interview_id: UUID,
    cfg: InterviewCodingConfig,
    task: CodingTask,
    start_timer: bool = False,
) -> CodingSubmission:
    row = db.scalar(
        select(CodingSubmission).where(
            CodingSubmission.interview_id == interview_id,
            CodingSubmission.task_id == task.id,
            CodingSubmission.is_demo.is_(False),
        )
    )
    lang = cfg.default_language or "python"
    starter = ""
    if task.starter_code_json:
        starter = str(task.starter_code_json.get(lang) or "")
    workspace = _default_workspace(lang, starter)
    now = datetime.now(timezone.utc)
    if row is None:
        row = CodingSubmission(
            interview_id=interview_id,
            task_id=task.id,
            organization_id=user.organization_id,
            language=lang,
            code=starter,
            status="draft",
            is_demo=False,
            demo_token=cfg.access_token,
            workspace_json=_workspace_to_json(workspace),
            started_at=now if start_timer else now,
        )
        db.add(row)
        db.flush()
    else:
        if not row.demo_token and cfg.access_token:
            row.demo_token = cfg.access_token
        if not row.workspace_json:
            row.workspace_json = _workspace_to_json(workspace)
        if start_timer and row.status != "submitted" and row.started_at is None:
            row.started_at = now
    return row


def _ensure_interview_submissions(
    db: Session,
    user: User,
    *,
    interview_id: UUID,
    cfg: InterviewCodingConfig,
) -> List[CodingSubmission]:
    task_ids = _ordered_task_ids(cfg)
    if not task_ids:
        raise HTTPException(status_code=400, detail="At least one coding task is required")
    rows: List[CodingSubmission] = []
    for idx, task_id in enumerate(task_ids):
        task = db.get(CodingTask, task_id)
        if task is None:
            raise HTTPException(status_code=404, detail="Coding task not found")
        rows.append(
            _ensure_submission_for_task(
                db,
                user,
                interview_id=interview_id,
                cfg=cfg,
                task=task,
                start_timer=(idx == 0),
            )
        )
    # Current pointer = first incomplete task
    cfg.assigned_task_id = _current_task_id(db, cfg) or task_ids[0]
    cfg.time_limit_min = _time_limit_for_task(cfg, cfg.assigned_task_id)
    return rows


def _ensure_interview_submission(
    db: Session,
    user: User,
    *,
    interview_id: UUID,
    cfg: InterviewCodingConfig,
) -> CodingSubmission:
    """Backward-compatible helper: ensure drafts for all tasks; return current."""
    rows = _ensure_interview_submissions(
        db, user, interview_id=interview_id, cfg=cfg
    )
    current_id = cfg.assigned_task_id or (rows[0].task_id if rows else None)
    for row in rows:
        if row.task_id == current_id:
            return row
    return rows[0]


def _submission_status_for_task(
    db: Session, interview_id: UUID, task_id: UUID
) -> str:
    row = db.scalar(
        select(CodingSubmission).where(
            CodingSubmission.interview_id == interview_id,
            CodingSubmission.task_id == task_id,
            CodingSubmission.is_demo.is_(False),
        )
    )
    if row is None:
        return "pending"
    return row.status or "draft"


def _current_task_id(db: Session, cfg: InterviewCodingConfig) -> Optional[UUID]:
    task_ids = _ordered_task_ids(cfg)
    if not task_ids:
        return None
    for task_id in task_ids:
        status = _submission_status_for_task(db, cfg.interview_id, task_id)
        if status != "submitted":
            return task_id
    return task_ids[-1]


def _assigned_task_progress(
    db: Session, cfg: InterviewCodingConfig
) -> List[CodingAssignedTaskProgress]:
    task_ids = _ordered_task_ids(cfg)
    current = _current_task_id(db, cfg)
    out: List[CodingAssignedTaskProgress] = []
    for task_id in task_ids:
        task = db.get(CodingTask, task_id)
        if task is None:
            continue
        out.append(
            CodingAssignedTaskProgress(
                task_id=task_id,
                title=task.title,
                difficulty=task.difficulty,
                time_limit_min=_time_limit_for_task(cfg, task_id, task=task),
                status=_submission_status_for_task(db, cfg.interview_id, task_id),
                is_current=current == task_id,
            )
        )
    return out


def _advance_to_next_task(
    db: Session,
    *,
    cfg: InterviewCodingConfig,
    interview: InterviewSession,
    public_token: Optional[str] = None,
) -> Optional[UUID]:
    """After submitting current task, point config at the next incomplete task."""
    task_ids = _ordered_task_ids(cfg)
    next_id = None
    for task_id in task_ids:
        status = _submission_status_for_task(db, cfg.interview_id, task_id)
        if status != "submitted":
            next_id = task_id
            break
    if next_id is None:
        return None

    cfg.assigned_task_id = next_id
    cfg.time_limit_min = _time_limit_for_task(cfg, next_id)
    cfg.updated_at = datetime.now(timezone.utc)

    task = db.get(CodingTask, next_id)
    if task is None:
        return None

    lang = cfg.default_language or "python"
    starter = ""
    if task.starter_code_json:
        starter = str(task.starter_code_json.get(lang) or "")
    workspace = _default_workspace(lang, starter)
    now = datetime.now(timezone.utc)
    row = db.scalar(
        select(CodingSubmission).where(
            CodingSubmission.interview_id == cfg.interview_id,
            CodingSubmission.task_id == next_id,
            CodingSubmission.is_demo.is_(False),
        )
    )
    token = public_token or cfg.access_token
    if row is None:
        row = CodingSubmission(
            interview_id=cfg.interview_id,
            task_id=next_id,
            organization_id=interview.organization_id,
            language=lang,
            code=starter,
            status="draft",
            is_demo=False,
            demo_token=token,
            workspace_json=_workspace_to_json(workspace),
            started_at=now,
        )
        db.add(row)
    else:
        if token and not row.demo_token:
            row.demo_token = token
        if row.status != "submitted":
            # Fresh timer for the next problem
            row.started_at = now
            if not row.code and starter:
                row.code = starter
            if not row.workspace_json:
                row.workspace_json = _workspace_to_json(workspace)
    db.flush()
    return next_id


def build_coding_config_out(
    db: Session, interview: InterviewSession, cfg: InterviewCodingConfig
) -> InterviewCodingConfigOut:
    uri = None
    wrap = None
    task_ids = _ordered_task_ids(cfg)
    if cfg.enabled and task_ids and cfg.access_token:
        uri = _coding_uri_for_token(cfg.access_token)
        wrap = _wrapup_message(uri)
    return InterviewCodingConfigOut(
        interview_id=interview.id,
        enabled=cfg.enabled,
        domain_id=cfg.domain_id,
        allowed_languages=list(cfg.allowed_languages or []),
        default_language=cfg.default_language,
        task_ids=task_ids,
        assigned_task_id=cfg.assigned_task_id,
        time_limit_min=cfg.time_limit_min,
        task_time_limits=_task_time_limits_map(cfg),
        coding_uri=uri,
        wrapup_message=wrap,
    )


# ── Domains + AI problem bank ─────────────────────────────────────────────────


def _slugify(value: str) -> str:
    import re

    raw = re.sub(r"[^a-z0-9]+", "-", (value or "").strip().lower()).strip("-")
    return (raw or "problem")[:60]


def _get_domain_for_org(db: Session, user: User, domain_id: UUID) -> CodingDomain:
    domain = db.get(CodingDomain, domain_id)
    if (
        domain is None
        or not domain.is_active
        or (
            domain.organization_id is not None
            and domain.organization_id != user.organization_id
        )
    ):
        raise HTTPException(status_code=404, detail="Coding domain not found")
    return domain


def _org_problem_count(db: Session, user: User, domain_id: UUID) -> int:
    rows = db.scalars(
        select(CodingTask).where(
            CodingTask.domain_id == domain_id,
            CodingTask.organization_id == user.organization_id,
            CodingTask.is_active.is_(True),
        )
    ).all()
    return len(rows)


def _domain_out(db: Session, user: User, domain: CodingDomain) -> CodingDomainOut:
    count = _org_problem_count(db, user, domain.id)
    return CodingDomainOut(
        id=domain.id,
        slug=domain.slug,
        name=domain.name,
        language=domain.language,
        description=domain.description or "",
        is_active=domain.is_active,
        problem_count=count,
        max_problems=MAX_PROBLEMS_PER_DOMAIN,
        can_generate=count < MAX_PROBLEMS_PER_DOMAIN,
        is_org_owned=domain.organization_id is not None,
    )


def _locked_langs_for_session(
    db: Session,
    *,
    cfg: Optional[InterviewCodingConfig] = None,
    task: Optional[CodingTask] = None,
    domain_id: Optional[UUID] = None,
) -> tuple[List[str], Optional[UUID], Optional[str]]:
    """Return (allowed_languages, domain_id, domain_name) locked to one language when domain set."""
    domain = None
    did = domain_id or (cfg.domain_id if cfg else None) or (task.domain_id if task else None)
    if did:
        domain = db.get(CodingDomain, did)
    if domain is not None:
        return [domain.language], domain.id, domain.name
    if cfg and cfg.allowed_languages:
        langs = list(cfg.allowed_languages)
        return langs, cfg.domain_id, None
    if task and task.allowed_languages:
        return list(task.allowed_languages), task.domain_id, None
    return ["python"], None, None


@router.get("/languages")
def list_coding_languages(user: User = Depends(get_current_user)):
    """Languages available for domains / editor / AI generate."""
    _ = user
    return {"languages": languages_for_api()}


@router.get("/domains", response_model=List[CodingDomainOut])
def list_coding_domains(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """All unlocked domains (global + org)."""
    rows = db.scalars(
        select(CodingDomain)
        .where(
            CodingDomain.is_active.is_(True),
            or_(
                CodingDomain.organization_id.is_(None),
                CodingDomain.organization_id == user.organization_id,
            ),
        )
        .order_by(CodingDomain.sort_order, CodingDomain.name)
    ).all()
    return [_domain_out(db, user, row) for row in rows]


@router.post("/domains", response_model=CodingDomainOut)
def create_coding_domain(
    body: CodingDomainCreateIn,
    user: User = Depends(require_writer),
    db: Session = Depends(get_db),
):
    """Create an org-owned domain track (language locked for candidates)."""
    base_slug = _slugify(body.name)
    slug = base_slug
    n = 1
    while db.scalar(
        select(CodingDomain).where(
            CodingDomain.organization_id == user.organization_id,
            CodingDomain.slug == slug,
        )
    ):
        n += 1
        slug = f"{base_slug}-{n}"

    # Place org domains after globals
    max_sort = db.scalar(
        select(CodingDomain.sort_order)
        .where(
            or_(
                CodingDomain.organization_id.is_(None),
                CodingDomain.organization_id == user.organization_id,
            )
        )
        .order_by(CodingDomain.sort_order.desc())
        .limit(1)
    )
    row = CodingDomain(
        organization_id=user.organization_id,
        slug=slug,
        name=body.name,
        language=body.language,
        description=(body.description or "").strip(),
        is_active=True,
        sort_order=int(max_sort or 0) + 1,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    logger.info(
        "[coding] domain created org=%s slug=%s lang=%s",
        user.organization_id,
        row.slug,
        row.language,
    )
    return _domain_out(db, user, row)


@router.get("/domains/{domain_id}/tasks", response_model=List[CodingTaskSummary])
def list_domain_tasks(
    domain_id: UUID,
    owned_only: bool = Query(
        False,
        description="If true, only org-owned problems (dashboard bank). If false, include global seeds.",
    ),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    domain = _get_domain_for_org(db, user, domain_id)
    stmt = select(CodingTask).where(
        CodingTask.domain_id == domain.id,
        CodingTask.is_active.is_(True),
    )
    if owned_only:
        stmt = stmt.where(CodingTask.organization_id == user.organization_id)
    else:
        stmt = stmt.where(
            or_(
                CodingTask.organization_id.is_(None),
                CodingTask.organization_id == user.organization_id,
            )
        )
    rows = db.scalars(stmt.order_by(CodingTask.created_at.desc())).all()
    return [_task_to_summary(row) for row in rows]


@router.delete("/domains/{domain_id}/tasks")
def deactivate_all_domain_tasks(
    domain_id: UUID,
    user: User = Depends(require_writer),
    db: Session = Depends(get_db),
):
    """Deactivate all org-owned problems in this domain (seeds untouched)."""
    domain = _get_domain_for_org(db, user, domain_id)
    rows = db.scalars(
        select(CodingTask).where(
            CodingTask.domain_id == domain.id,
            CodingTask.organization_id == user.organization_id,
            CodingTask.is_active.is_(True),
        )
    ).all()
    now = datetime.now(timezone.utc)
    for row in rows:
        row.is_active = False
        row.updated_at = now
    db.commit()
    return {"ok": True, "deleted": len(rows)}


@router.post("/domains/{domain_id}/tasks/generate", response_model=CodingTaskDetail)
def generate_domain_task(
    domain_id: UUID,
    user: User = Depends(require_writer),
    db: Session = Depends(get_db),
):
    """AI-generate and save one DSA problem. Disabled when org already has 5 in domain."""
    from services.coding_problem_generator import generate_dsa_problem

    domain = _get_domain_for_org(db, user, domain_id)
    count = _org_problem_count(db, user, domain.id)
    if count >= MAX_PROBLEMS_PER_DOMAIN:
        raise HTTPException(
            status_code=400,
            detail=f"Domain already has {MAX_PROBLEMS_PER_DOMAIN} problems. Delete one to generate more.",
        )

    existing = db.scalars(
        select(CodingTask).where(
            CodingTask.domain_id == domain.id,
            CodingTask.is_active.is_(True),
            or_(
                CodingTask.organization_id.is_(None),
                CodingTask.organization_id == user.organization_id,
            ),
        )
    ).all()
    titles = [t.title for t in existing]
    tags: list[str] = []
    for t in existing:
        tags.extend([str(x) for x in (t.skill_tags or []) if str(x).strip()])

    draft = generate_dsa_problem(
        language=domain.language,
        domain_name=domain.name,
        existing_titles=titles,
        existing_tags=tags,
    )
    if not draft:
        raise HTTPException(
            status_code=503,
            detail=(
                "AI generate failed. Wait ~1 minute if Groq rate-limited you, then try "
                "Generate once more. Check GROQ_API_KEY if it keeps failing."
            ),
        )

    base_slug = _slugify(draft["title"])
    slug = base_slug
    n = 1
    while db.scalar(
        select(CodingTask).where(
            CodingTask.organization_id == user.organization_id,
            CodingTask.slug == slug,
        )
    ):
        n += 1
        slug = f"{base_slug}-{n}"

    lang = domain.language
    estimated = _clamp_estimated_minutes(
        draft.get("estimated_minutes"), draft.get("difficulty") or "medium"
    )
    row = CodingTask(
        organization_id=user.organization_id,
        domain_id=domain.id,
        slug=slug,
        title=draft["title"],
        difficulty=draft["difficulty"],
        statement=draft["statement"],
        examples_json=draft["examples"],
        constraints_text=draft.get("constraints_text") or "",
        starter_code_json={lang: draft["starter_code"]},
        entry_function=draft["entry_function"],
        allowed_languages=[lang],
        skill_tags=draft.get("skill_tags") or [],
        estimated_time_min=estimated,
        is_active=True,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    logger.info(
        "[coding] generated task org=%s domain=%s slug=%s",
        user.organization_id,
        domain.slug,
        row.slug,
    )
    return _task_to_detail(row)


@router.delete("/domains/{domain_id}/tasks/{task_id}")
def deactivate_domain_task(
    domain_id: UUID,
    task_id: UUID,
    user: User = Depends(require_writer),
    db: Session = Depends(get_db),
):
    domain = _get_domain_for_org(db, user, domain_id)
    task = db.get(CodingTask, task_id)
    if (
        task is None
        or task.domain_id != domain.id
        or task.organization_id != user.organization_id
    ):
        raise HTTPException(status_code=404, detail="Org-owned task not found")
    task.is_active = False
    task.updated_at = datetime.now(timezone.utc)
    db.commit()
    return {"ok": True, "id": str(task.id)}


# ── Task bank ────────────────────────────────────────────────────────────────


@router.get("/tasks", response_model=List[CodingTaskSummary])
def list_coding_tasks(
    difficulty: Optional[str] = Query(None),
    domain_id: Optional[UUID] = Query(None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    stmt = select(CodingTask).where(
        CodingTask.is_active.is_(True),
        or_(
            CodingTask.organization_id.is_(None),
            CodingTask.organization_id == user.organization_id,
        ),
    )
    if difficulty:
        stmt = stmt.where(CodingTask.difficulty == difficulty.strip().lower())
    if domain_id:
        stmt = stmt.where(CodingTask.domain_id == domain_id)
    stmt = stmt.order_by(CodingTask.difficulty, CodingTask.title)
    rows = db.scalars(stmt).all()
    return [_task_to_summary(row) for row in rows]


@router.get("/tasks/{task_id}", response_model=CodingTaskDetail)
def get_coding_task(
    task_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return _task_to_detail(_get_task_for_org(db, user, task_id))


# ── Interview coding config ──────────────────────────────────────────────────


@router.put(
    "/interviews/{interview_id}/config",
    response_model=InterviewCodingConfigOut,
)
def put_interview_coding_config(
    interview_id: UUID,
    body: InterviewCodingConfigIn,
    user: User = Depends(require_writer),
    db: Session = Depends(get_db),
):
    interview = _get_org_interview(db, user, interview_id)
    cfg = upsert_interview_coding_config(db, user, interview_id, body)
    return build_coding_config_out(db, interview, cfg)


@router.get(
    "/interviews/{interview_id}/config",
    response_model=InterviewCodingConfigOut,
)
def get_interview_coding_config(
    interview_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    interview = _get_org_interview(db, user, interview_id)
    cfg = db.scalar(
        select(InterviewCodingConfig).where(
            InterviewCodingConfig.interview_id == interview_id
        )
    )
    if cfg is None:
        return InterviewCodingConfigOut(
            interview_id=interview_id,
            enabled=False,
            domain_id=None,
            allowed_languages=["python", "javascript"],
            default_language="python",
            task_ids=[],
            assigned_task_id=None,
            time_limit_min=30,
            task_time_limits={},
            coding_uri=None,
            wrapup_message=None,
        )
    return build_coding_config_out(db, interview, cfg)


# ── Candidate / recruiter coding session by interview ────────────────────────


@router.get("/interviews/by-bot/{bot_id}/session", response_model=CodingSessionOut)
def get_coding_session_by_bot(
    bot_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    interview = _resolve_interview_by_bot_or_id(db, user, bot_id=bot_id)
    return _build_interview_session(db, user, interview)


@router.get("/interviews/{interview_id}/session", response_model=CodingSessionOut)
def get_coding_session_by_interview(
    interview_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    interview = _get_org_interview(db, user, interview_id)
    return _build_interview_session(db, user, interview)


def _build_interview_session(
    db: Session,
    user: User,
    interview: InterviewSession,
) -> CodingSessionOut:
    cfg = db.scalar(
        select(InterviewCodingConfig).where(
            InterviewCodingConfig.interview_id == interview.id
        )
    )
    task_ids = _ordered_task_ids(cfg) if cfg else []
    if cfg is None or not cfg.enabled or not task_ids:
        raise HTTPException(
            status_code=404,
            detail="Coding round is not enabled for this interview",
        )

    current_id = _current_task_id(db, cfg) or task_ids[0]
    cfg.assigned_task_id = current_id
    task = _get_task_for_org(db, user, current_id)
    time_limit = _time_limit_for_task(cfg, current_id, task=task)
    cfg.time_limit_min = time_limit

    submission = db.scalar(
        select(CodingSubmission).where(
            CodingSubmission.interview_id == interview.id,
            CodingSubmission.task_id == task.id,
            CodingSubmission.is_demo.is_(False),
        )
    )
    language = cfg.default_language
    code = ""
    status = "draft"
    if submission is not None:
        language = submission.language or language
        code = submission.code or ""
        status = submission.status
    elif task.starter_code_json:
        code = str(task.starter_code_json.get(language) or "")

    locked_langs, domain_id, domain_name = _locked_langs_for_session(
        db, cfg=cfg, task=task
    )
    language = locked_langs[0]
    bot_id = str(interview.bot_id) if interview.bot_id else None
    workspace = (
        _workspace_from_row(submission, language)
        if submission is not None
        else _default_workspace(language, code)
    )
    token = cfg.access_token or (submission.demo_token if submission else None)
    started = submission.started_at if submission is not None else None
    started, ends = _session_timing(
        started_at=started, time_limit_min=time_limit
    )
    progress = _assigned_task_progress(db, cfg)
    idx = next((i for i, p in enumerate(progress) if p.is_current), 0)
    has_next = any(
        p.status != "submitted" and p.task_id != current_id for p in progress
    )
    return CodingSessionOut(
        interview_id=interview.id,
        bot_id=bot_id,
        access_token=token,
        enabled=True,
        language=language,
        allowed_languages=locked_langs,
        language_locked=True,
        domain_id=domain_id,
        domain_name=domain_name,
        time_limit_min=time_limit,
        started_at=started,
        ends_at=ends,
        task=_task_to_detail(task),
        submission_status=status,
        code=_active_code(workspace) or code,
        workspace=workspace,
        coding_uri=_coding_uri_for_token(token) if token else None,
        task_index=idx + 1,
        task_count=len(progress) or 1,
        has_next_task=has_next,
        assigned_tasks=progress,
    )


@router.post(
    "/interviews/by-bot/{bot_id}/submit",
    response_model=CodingSubmitOut,
)
def submit_coding_by_bot(
    bot_id: str,
    body: CodingSubmitIn,
    user: User = Depends(require_writer),
    db: Session = Depends(get_db),
):
    interview = _resolve_interview_by_bot_or_id(db, user, bot_id=bot_id)
    return _submit_for_interview(db, user, interview, body)


@router.post(
    "/interviews/{interview_id}/submit",
    response_model=CodingSubmitOut,
)
def submit_coding_by_interview(
    interview_id: UUID,
    body: CodingSubmitIn,
    user: User = Depends(require_writer),
    db: Session = Depends(get_db),
):
    interview = _get_org_interview(db, user, interview_id)
    return _submit_for_interview(db, user, interview, body)


def _submit_for_interview(
    db: Session,
    user: User,
    interview: InterviewSession,
    body: CodingSubmitIn,
) -> CodingSubmitOut:
    cfg = db.scalar(
        select(InterviewCodingConfig).where(
            InterviewCodingConfig.interview_id == interview.id
        )
    )
    task_ids = _ordered_task_ids(cfg) if cfg else []
    if cfg is None or not cfg.enabled or not task_ids:
        raise HTTPException(
            status_code=400,
            detail="Coding round is not enabled for this interview",
        )
    if body.language not in (cfg.allowed_languages or []):
        raise HTTPException(status_code=400, detail="Language not allowed for this interview")

    current_id = _current_task_id(db, cfg) or task_ids[0]
    cfg.assigned_task_id = current_id
    task = _get_task_for_org(db, user, current_id)
    row = db.scalar(
        select(CodingSubmission).where(
            CodingSubmission.interview_id == interview.id,
            CodingSubmission.task_id == task.id,
            CodingSubmission.is_demo.is_(False),
        )
    )
    now = datetime.now(timezone.utc)
    if row is None:
        row = CodingSubmission(
            interview_id=interview.id,
            task_id=task.id,
            organization_id=user.organization_id,
            language=body.language,
            code=body.code,
            status=body.status,
            is_demo=False,
            started_at=now,
        )
        db.add(row)
    else:
        if row.status == "submitted" and body.status == "draft":
            raise HTTPException(status_code=400, detail="Submission already finalized")
        row.language = body.language
        row.code = body.code
        row.status = body.status
        row.updated_at = now

    if body.status == "submitted":
        row.submitted_at = now

    next_id = None
    if body.status == "submitted":
        db.flush()
        next_id = _advance_to_next_task(db, cfg=cfg, interview=interview)

    progress = _assigned_task_progress(db, cfg)
    idx = next(
        (i for i, p in enumerate(progress) if p.task_id == row.task_id),
        0,
    )
    db.commit()
    db.refresh(row)
    return CodingSubmitOut(
        id=row.id,
        status=row.status,
        language=row.language,
        submitted_at=row.submitted_at,
        task_id=row.task_id,
        interview_id=row.interview_id,
        has_next_task=next_id is not None,
        next_task_id=next_id,
        task_index=idx + 1,
        task_count=len(progress) or 1,
    )


# ── Run code / examples (local subprocess runner) ─────────────────────────────


@router.post("/run", response_model=CodingRunOut)
def run_coding_snippet(
    body: CodingRunIn,
    user: User = Depends(require_writer),
):
    """Execute candidate code once with optional stdin. Auth required."""
    from services.coding_runner import run_code

    _ = user
    files = body.workspace.files if body.workspace else None
    entry = body.workspace.entryPath if body.workspace else None
    result = run_code(
        language=body.language,
        code=body.code,
        stdin=body.stdin or "",
        timeout_sec=body.timeout_sec,
        files=files,
        entry_path=entry,
    )
    return CodingRunOut(
        ok=result.ok,
        exit_code=result.exit_code,
        stdout=result.stdout,
        stderr=result.stderr,
        timed_out=result.timed_out,
        language=result.language,
        error=result.error,
    )


@router.post("/run-examples", response_model=CodingRunExamplesOut)
def run_coding_examples(
    body: CodingRunExamplesIn,
    user: User = Depends(require_writer),
    db: Session = Depends(get_db),
):
    """Run code against the task's public examples and compare outputs."""
    from services.coding_complexity import analyze_complexity
    from services.coding_runner import run_examples

    task = _get_task_for_org(db, user, body.task_id)
    examples = task.examples_json if isinstance(task.examples_json, list) else []
    if not examples:
        raise HTTPException(status_code=400, detail="Task has no examples to run")
    files = body.workspace.files if body.workspace else None
    entry = body.workspace.entryPath if body.workspace else None
    code = body.code or ""
    payload = run_examples(
        language=body.language,
        code=code,
        examples=examples,
        timeout_sec=body.timeout_sec,
        files=files,
        entry_path=entry,
        entry_function=getattr(task, "entry_function", None),
    )
    complexity = analyze_complexity(language=body.language, code=code)
    return CodingRunExamplesOut(**payload, complexity=CodingComplexityOut(**complexity))


# ── Demo path (no full interview needed) ─────────────────────────────────────


@router.post("/demo/start", response_model=CodingSessionOut)
def start_demo_coding_session(
    body: DemoStartIn,
    user: User = Depends(require_writer),
    db: Session = Depends(get_db),
):
    """Start a disposable coding session. Domain locks candidate to one language."""
    domain = None
    if body.domain_id:
        domain = _get_domain_for_org(db, user, body.domain_id)

    task_id = body.task_id
    if task_id is None and domain is not None:
        first = db.scalar(
            select(CodingTask)
            .where(
                CodingTask.domain_id == domain.id,
                CodingTask.is_active.is_(True),
                or_(
                    CodingTask.organization_id.is_(None),
                    CodingTask.organization_id == user.organization_id,
                ),
            )
            .order_by(CodingTask.created_at.asc())
            .limit(1)
        )
        if first is None:
            raise HTTPException(
                status_code=400,
                detail="No problems in this domain yet. Generate one from the Coding dashboard.",
            )
        task_id = first.id
    task_id = task_id or SEED_TASK_IDS[0]
    task = _get_task_for_org(db, user, task_id)

    if domain is None and task.domain_id:
        domain = db.get(CodingDomain, task.domain_id)

    language = (
        domain.language
        if domain is not None
        else (body.language or (task.allowed_languages or ["python"])[0])
    )
    if language not in (task.allowed_languages or []):
        # Prefer domain lock; if seed task allows both, still lock to domain language
        if domain is None:
            raise HTTPException(
                status_code=400,
                detail=f"Language '{language}' not allowed for this task",
            )

    token = secrets.token_urlsafe(24)
    starter = ""
    if task.starter_code_json:
        starter = str(task.starter_code_json.get(language) or "")
        if not starter and domain is not None:
            # Fall back to any starter then rewrite extension via workspace
            starter = str(next(iter(task.starter_code_json.values()), "") or "")
    workspace = _default_workspace(language, starter)

    row = CodingSubmission(
        interview_id=None,
        task_id=task.id,
        organization_id=user.organization_id,
        language=language,
        code=starter,
        status="draft",
        is_demo=True,
        demo_token=token,
        workspace_json=_workspace_to_json(workspace),
        started_at=datetime.now(timezone.utc),
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    uri = _coding_uri_for_token(token)
    locked = [language]
    logger.info(
        "[coding] demo session started org=%s task=%s lang=%s token=%s…",
        user.organization_id,
        task.slug,
        language,
        token[:8],
    )
    return CodingSessionOut(
        demo_token=token,
        access_token=token,
        enabled=True,
        language=language,
        allowed_languages=locked,
        language_locked=True,
        domain_id=domain.id if domain else task.domain_id,
        domain_name=domain.name if domain else None,
        time_limit_min=30,
        started_at=row.started_at,
        ends_at=_session_timing(started_at=row.started_at, time_limit_min=30)[1],
        task=_task_to_detail(task),
        submission_status="draft",
        code=starter,
        workspace=workspace,
        coding_uri=uri,
    )


@router.get("/demo/{demo_token}", response_model=CodingSessionOut)
def get_demo_coding_session(
    demo_token: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = db.scalar(
        select(CodingSubmission).where(
            CodingSubmission.demo_token == demo_token,
            CodingSubmission.is_demo.is_(True),
            CodingSubmission.organization_id == user.organization_id,
        )
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Demo coding session not found")
    task = _get_task_for_org(db, user, row.task_id)
    workspace = _workspace_from_row(row, row.language)
    locked, domain_id, domain_name = _locked_langs_for_session(
        db, task=task, domain_id=task.domain_id
    )
    lang = row.language if row.language in locked else locked[0]
    return CodingSessionOut(
        demo_token=row.demo_token,
        access_token=row.demo_token,
        enabled=True,
        language=lang,
        allowed_languages=locked,
        language_locked=True,
        domain_id=domain_id,
        domain_name=domain_name,
        time_limit_min=30,
        started_at=row.started_at,
        ends_at=_session_timing(started_at=row.started_at, time_limit_min=30)[1],
        task=_task_to_detail(task),
        submission_status=row.status,
        code=_active_code(workspace),
        workspace=workspace,
        coding_uri=_coding_uri_for_token(demo_token),
    )


@router.post("/demo/{demo_token}/submit", response_model=CodingSubmitOut)
def submit_demo_coding_session(
    demo_token: str,
    body: CodingSubmitIn,
    user: User = Depends(require_writer),
    db: Session = Depends(get_db),
):
    row = db.scalar(
        select(CodingSubmission).where(
            CodingSubmission.demo_token == demo_token,
            CodingSubmission.is_demo.is_(True),
            CodingSubmission.organization_id == user.organization_id,
        )
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Demo coding session not found")
    task = _get_task_for_org(db, user, row.task_id)
    if body.language not in (task.allowed_languages or []):
        raise HTTPException(status_code=400, detail="Language not allowed for this task")
    if row.status == "submitted" and body.status == "draft":
        raise HTTPException(status_code=400, detail="Submission already finalized")

    now = datetime.now(timezone.utc)
    workspace = body.workspace or _workspace_from_row(row, body.language)
    row.language = body.language
    row.code = body.code or _active_code(workspace)
    row.workspace_json = _workspace_to_json(workspace)
    row.status = body.status
    row.updated_at = now
    if body.status == "submitted":
        row.submitted_at = now
    db.commit()
    db.refresh(row)
    return CodingSubmitOut(
        id=row.id,
        status=row.status,
        language=row.language,
        submitted_at=row.submitted_at,
        task_id=row.task_id,
        demo_token=row.demo_token,
    )


# ── Public candidate APIs (token only — no recruiter login) ───────────────────


def _resolve_public_submission(
    db: Session, token: str
) -> tuple[CodingSubmission, CodingTask, str, Optional[InterviewCodingConfig]]:
    """Resolve candidate token → current submission + task (+ config when interview)."""
    token = (token or "").strip()
    if not token:
        raise HTTPException(status_code=404, detail="Coding session not found")

    cfg = db.scalar(
        select(InterviewCodingConfig).where(
            InterviewCodingConfig.access_token == token,
            InterviewCodingConfig.enabled.is_(True),
        )
    )
    if cfg is not None:
        interview = db.get(InterviewSession, cfg.interview_id)
        if interview is None:
            raise HTTPException(status_code=404, detail="Coding session not found")
        task_ids = _ordered_task_ids(cfg)
        if not task_ids:
            raise HTTPException(status_code=404, detail="Coding session not found")

        current_id = _current_task_id(db, cfg) or task_ids[0]
        cfg.assigned_task_id = current_id
        task = db.get(CodingTask, current_id)
        if task is None or not task.is_active:
            raise HTTPException(status_code=404, detail="Coding task not found")

        row = db.scalar(
            select(CodingSubmission).where(
                CodingSubmission.interview_id == cfg.interview_id,
                CodingSubmission.task_id == current_id,
                CodingSubmission.is_demo.is_(False),
            )
        )
        now = datetime.now(timezone.utc)
        if row is None:
            lang = cfg.default_language or "python"
            starter = ""
            if task.starter_code_json:
                starter = str(task.starter_code_json.get(lang) or "")
            workspace = _default_workspace(lang, starter)
            row = CodingSubmission(
                interview_id=cfg.interview_id,
                task_id=current_id,
                organization_id=interview.organization_id,
                language=lang,
                code=starter,
                status="draft",
                is_demo=False,
                demo_token=token,
                workspace_json=_workspace_to_json(workspace),
                started_at=now,
            )
            db.add(row)
            db.commit()
            db.refresh(row)
        else:
            if not row.demo_token:
                row.demo_token = token
            if row.status != "submitted" and row.started_at is None:
                row.started_at = now
            db.commit()
            db.refresh(row)
        return row, task, token, cfg

    # Demo / legacy: resolve by submission demo_token
    row = db.scalar(
        select(CodingSubmission).where(CodingSubmission.demo_token == token)
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Coding session not found")

    interview_cfg = None
    if row.interview_id:
        interview_cfg = db.scalar(
            select(InterviewCodingConfig).where(
                InterviewCodingConfig.interview_id == row.interview_id
            )
        )
        if interview_cfg is not None and interview_cfg.enabled:
            # Prefer current incomplete task for multi-task rounds
            current_id = _current_task_id(db, interview_cfg)
            if current_id and current_id != row.task_id:
                current_row = db.scalar(
                    select(CodingSubmission).where(
                        CodingSubmission.interview_id == row.interview_id,
                        CodingSubmission.task_id == current_id,
                        CodingSubmission.is_demo.is_(False),
                    )
                )
                if current_row is not None:
                    row = current_row

    task = db.get(CodingTask, row.task_id)
    if task is None or not task.is_active:
        raise HTTPException(status_code=404, detail="Coding task not found")
    return row, task, token, interview_cfg


def _session_timing(
    *,
    started_at: Optional[datetime],
    time_limit_min: int,
) -> tuple[Optional[datetime], Optional[datetime]]:
    if started_at is None:
        return None, None
    start = started_at
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    ends = start + timedelta(minutes=max(1, int(time_limit_min or 30)))
    return start, ends


def _public_session_out(
    row: CodingSubmission,
    task: CodingTask,
    *,
    public_token: str,
    time_limit_min: int = 30,
    allowed_languages: Optional[List[str]] = None,
    domain_id: Optional[UUID] = None,
    domain_name: Optional[str] = None,
    cfg: Optional[InterviewCodingConfig] = None,
    db: Optional[Session] = None,
) -> CodingSessionOut:
    workspace = _workspace_from_row(row, row.language)
    locked = allowed_languages or [row.language]
    started, ends = _session_timing(
        started_at=row.started_at, time_limit_min=time_limit_min
    )
    progress: List[CodingAssignedTaskProgress] = []
    task_index = 1
    task_count = 1
    has_next = False
    if cfg is not None and db is not None:
        progress = _assigned_task_progress(db, cfg)
        task_count = len(progress) or 1
        task_index = next(
            (i + 1 for i, p in enumerate(progress) if p.task_id == row.task_id),
            1,
        )
        has_next = any(
            p.status != "submitted" and p.task_id != row.task_id for p in progress
        )
    return CodingSessionOut(
        interview_id=row.interview_id,
        demo_token=public_token or None,
        access_token=public_token or None,
        enabled=True,
        language=locked[0] if locked else row.language,
        allowed_languages=locked,
        language_locked=True,
        domain_id=domain_id,
        domain_name=domain_name,
        time_limit_min=time_limit_min,
        started_at=started,
        ends_at=ends,
        task=_task_to_detail(task),
        submission_status=row.status,
        code=_active_code(workspace),
        workspace=workspace,
        coding_uri=_coding_uri_for_token(public_token) if public_token else None,
        task_index=task_index,
        task_count=task_count,
        has_next_task=has_next,
        assigned_tasks=progress,
    )


@router.get("/public/{token}", response_model=CodingSessionOut)
def get_public_coding_session(token: str, db: Session = Depends(get_db)):
    """Candidate opens shared URI — no auth cookie/JWT required."""
    row, task, public_token, cfg = _resolve_public_submission(db, token)
    # Ensure timer has a start if older rows lack started_at
    if row.started_at is None and row.status != "submitted":
        row.started_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(row)

    time_limit = 30
    if cfg is not None:
        time_limit = _time_limit_for_task(cfg, row.task_id, task=task)
    elif row.interview_id:
        cfg = db.scalar(
            select(InterviewCodingConfig).where(
                InterviewCodingConfig.interview_id == row.interview_id
            )
        )
        if cfg:
            time_limit = _time_limit_for_task(cfg, row.task_id, task=task)
    locked, domain_id, domain_name = _locked_langs_for_session(
        db, cfg=cfg, task=task
    )
    return _public_session_out(
        row,
        task,
        public_token=public_token,
        time_limit_min=time_limit,
        allowed_languages=locked,
        domain_id=domain_id,
        domain_name=domain_name,
        cfg=cfg,
        db=db,
    )


@router.post("/public/{token}/save", response_model=CodingSubmitOut)
def save_public_coding_session(
    token: str,
    body: CodingSubmitIn,
    db: Session = Depends(get_db),
):
    row, task, public_token, cfg = _resolve_public_submission(db, token)
    locked, _domain_id, _domain_name = _locked_langs_for_session(db, cfg=cfg, task=task)
    if body.language not in locked:
        raise HTTPException(
            status_code=400,
            detail="Language is locked for this coding session",
        )
    if body.language not in (task.allowed_languages or []) and body.language not in locked:
        raise HTTPException(status_code=400, detail="Language not allowed for this task")
    if row.status == "submitted" and body.status == "draft":
        raise HTTPException(status_code=400, detail="Submission already finalized")

    workspace = body.workspace or _workspace_from_row(row, body.language)
    if len(workspace.files) > 20:
        raise HTTPException(status_code=400, detail="Too many files (max 20)")

    now = datetime.now(timezone.utc)
    row.language = body.language
    row.code = body.code or _active_code(workspace)
    row.workspace_json = _workspace_to_json(workspace)
    row.status = body.status
    row.updated_at = now
    if body.status == "submitted":
        row.submitted_at = now

    next_id = None
    task_index = 1
    task_count = 1
    if cfg is not None:
        progress = _assigned_task_progress(db, cfg)
        task_count = len(progress) or 1
        task_index = next(
            (i + 1 for i, p in enumerate(progress) if p.task_id == row.task_id),
            1,
        )
        if body.status == "submitted" and row.interview_id:
            interview = db.get(InterviewSession, row.interview_id)
            if interview is not None:
                db.flush()
                next_id = _advance_to_next_task(
                    db, cfg=cfg, interview=interview, public_token=public_token
                )

    db.commit()
    db.refresh(row)
    return CodingSubmitOut(
        id=row.id,
        status=row.status,
        language=row.language,
        submitted_at=row.submitted_at,
        task_id=row.task_id,
        interview_id=row.interview_id,
        demo_token=row.demo_token or public_token,
        has_next_task=next_id is not None,
        next_task_id=next_id,
        task_index=task_index,
        task_count=task_count,
    )


class PublicRunIn(BaseModel):
    language: Optional[str] = None
    code: str = ""
    workspace: Optional[CodingWorkspace] = None
    timeout_sec: float = Field(default=5.0, ge=1.0, le=15.0)


@router.post("/public/{token}/run-examples", response_model=CodingRunExamplesOut)
def run_public_coding_examples(
    token: str,
    body: PublicRunIn,
    db: Session = Depends(get_db),
):
    from services.coding_complexity import analyze_complexity
    from services.coding_runner import run_examples

    row, task, _public_token, _cfg = _resolve_public_submission(db, token)
    examples = task.examples_json if isinstance(task.examples_json, list) else []
    if not examples:
        raise HTTPException(status_code=400, detail="Task has no examples to run")
    language = (body.language or row.language or "python").strip().lower()
    workspace = body.workspace or _workspace_from_row(row, language)
    code = body.code or _active_code(workspace)
    payload = run_examples(
        language=language,
        code=code,
        examples=examples,
        timeout_sec=body.timeout_sec,
        files=workspace.files,
        entry_path=workspace.entryPath,
        entry_function=getattr(task, "entry_function", None),
    )
    complexity = analyze_complexity(language=language, code=code)
    return CodingRunExamplesOut(**payload, complexity=CodingComplexityOut(**complexity))
