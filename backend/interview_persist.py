"""Persist interview sessions, live answers/transcripts, and reports to Postgres."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

import config as app_config
from db.models import (
    Candidate,
    CandidateFeedback,
    InterviewAnswer,
    InterviewConfig,
    InterviewQuestion,
    InterviewReport,
    InterviewSession,
    JobPosting,
    SessionEvent,
    TranscriptTurn,
    User,
)
from db.session import get_session_factory, is_db_configured
from interview_engine import BankQuestion, QuestionSelector, normalize_difficulty, parse_bank_questions
from recall_bot_service import normalize_meeting_url

logger = logging.getLogger(__name__)

# bot_id (str) -> interview_sessions.id (str); avoids a DB round-trip per transcript line
_bot_interview_cache: dict[str, str] = {}

_VALID_SOURCES = frozenset({"jd", "resume", "other"})
_VALID_TURN_TYPES = frozenset(
    {
        "greeting",
        "introduction",
        "question",
        "answer",
        "clarifier",
        "rephrase",
        "repeat",
        "presence_check",
        "continuation",
        "closing",
        "other",
    }
)
_VALID_EVENTS = frozenset(
    {
        "bot_created",
        "bot_joined_meeting",
        "lobby_timeout",
        "interview_started",
        "question_asked",
        "answer_scored",
        "localization_completed",
        "localization_failed",
        "playback_done",
        "interview_ended",
        "bot_left",
        "error",
    }
)


def normalize_source(raw: str) -> str:
    s = (raw or "jd").strip().lower()
    if s in ("resume", "cv", "candidate"):
        return "resume"
    if s in ("other",):
        return "other"
    return "jd"


def _assert_candidate(db: Session, user: User, candidate_id: UUID) -> Candidate:
    row = db.get(Candidate, candidate_id)
    if (
        row is None
        or row.organization_id != user.organization_id
        or row.deleted_at is not None
    ):
        raise HTTPException(status_code=404, detail="Candidate not found")
    return row


def _assert_job(db: Session, user: User, job_posting_id: UUID) -> JobPosting:
    row = db.get(JobPosting, job_posting_id)
    if (
        row is None
        or row.organization_id != user.organization_id
        or row.deleted_at is not None
    ):
        raise HTTPException(status_code=404, detail="Job posting not found")
    return row


def get_org_interview(db: Session, user: User, interview_id: UUID) -> InterviewSession:
    row = db.get(InterviewSession, interview_id)
    if row is None or row.organization_id != user.organization_id:
        raise HTTPException(status_code=404, detail="Interview not found")
    if user.role == "recruiter" and row.created_by != user.id:
        raise HTTPException(status_code=404, detail="Interview not found")
    return row


def _planned_from_bank(questions: list[dict[str, Any]]) -> list[BankQuestion]:
    bank = parse_bank_questions(questions)
    return QuestionSelector.select(bank, app_config.MAX_QUESTIONS)


def _add_questions(
    db: Session,
    interview_id: UUID,
    planned: list[BankQuestion],
) -> None:
    for i, q in enumerate(planned):
        text = (q.question or "").strip()
        if len(text) < 10:
            raise HTTPException(
                status_code=400,
                detail=f"Question slot {i + 1} is too short (min 10 characters)",
            )
        db.add(
            InterviewQuestion(
                interview_id=interview_id,
                slot=i + 1,
                external_question_id=str(q.id)[:64],
                difficulty=normalize_difficulty(q.difficulty),
                source=normalize_source(q.source),
                question_text=text,
                status="pending",
            )
        )


def create_scheduled_interview(
    db: Session,
    user: User,
    *,
    meeting_url: str,
    candidate_id: UUID,
    job_posting_id: UUID,
    candidate_name: str,
    job_title: str,
    jd_text: str,
    cv_text: str,
    questions: list[dict[str, Any]],
    language_mode: str = "english",
    bot_name: str = "Prabhat",
    greeting_message: Optional[str] = None,
    document_extraction_id: Optional[UUID] = None,
) -> InterviewSession:
    """Save interview setup with bot_id NULL (Schedule)."""
    candidate = _assert_candidate(db, user, candidate_id)
    job = _assert_job(db, user, job_posting_id)

    jd = (jd_text or "").strip()
    cv = (cv_text or "").strip()
    if len(jd) < 100:
        raise HTTPException(status_code=400, detail="jdText must be at least 100 characters")
    if len(cv) < 50:
        raise HTTPException(status_code=400, detail="cvText must be at least 50 characters")

    title = (job_title or job.job_title or "").strip()
    if len(title) < 2:
        raise HTTPException(status_code=400, detail="job_title is required")

    name = (candidate_name or candidate.full_name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="candidate_name is required")

    planned = _planned_from_bank(questions)
    meeting_key = normalize_meeting_url(meeting_url)

    session = InterviewSession(
        bot_id=None,
        organization_id=user.organization_id,
        created_by=user.id,
        candidate_id=candidate_id,
        job_posting_id=job_posting_id,
        meeting_url=meeting_url.strip(),
        meeting_url_normalized=meeting_key,
        bot_name=(bot_name or "Prabhat").strip()[:100] or "Prabhat",
        language_mode=language_mode,
        interview_started=False,
        interview_ended=False,
        is_active=True,
        stopped_reason="none",
    )
    db.add(session)
    db.flush()

    settings: dict[str, Any] = {"language_mode": language_mode}
    if greeting_message:
        settings["greeting_message"] = greeting_message.strip()

    db.add(
        InterviewConfig(
            interview_id=session.id,
            job_posting_id=job_posting_id,
            document_extraction_id=document_extraction_id,
            job_title=title[:255],
            recruiter_name=(user.full_name or user.email)[:255],
            candidate_name=name[:255],
            jd_text=jd,
            cv_text=cv,
            continue_threshold=Decimal(str(app_config.CONTINUE_AVG_THRESHOLD)),
            rolling_window=int(app_config.ROLLING_WINDOW),
            questions_planned_count=len(planned),
            settings_json=settings,
        )
    )
    _add_questions(db, session.id, planned)
    db.commit()
    db.refresh(session)
    logger.info(
        "[interview] scheduled id=%s user=%s candidate=%s job=%s qs=%d",
        session.id,
        user.email,
        candidate_id,
        job_posting_id,
        len(planned),
    )
    return session


def create_interview_with_bot(
    db: Session,
    user: User,
    *,
    bot_id: str,
    meeting_url: str,
    candidate_id: UUID,
    job_posting_id: UUID,
    candidate_name: str,
    job_title: str,
    jd_text: str,
    cv_text: str,
    planned: list[BankQuestion],
    language_mode: str = "english",
    bot_name: str = "Prabhat",
    greeting_message: Optional[str] = None,
    document_extraction_id: Optional[UUID] = None,
) -> InterviewSession:
    """Create interview row already linked to a Recall bot (direct Send to lobby)."""
    _assert_candidate(db, user, candidate_id)
    job = _assert_job(db, user, job_posting_id)

    jd = (jd_text or "").strip()
    cv = (cv_text or "").strip()
    if len(jd) < 100:
        raise HTTPException(status_code=400, detail="jdText must be at least 100 characters")
    if len(cv) < 50:
        raise HTTPException(status_code=400, detail="cvText must be at least 50 characters")

    title = (job_title or job.job_title or "").strip()
    if len(title) < 2:
        raise HTTPException(status_code=400, detail="job_title is required")

    name = (candidate_name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="candidate_name is required")

    try:
        bot_uuid = UUID(str(bot_id))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid bot_id") from exc

    meeting_key = normalize_meeting_url(meeting_url)
    session = InterviewSession(
        bot_id=bot_uuid,
        organization_id=user.organization_id,
        created_by=user.id,
        candidate_id=candidate_id,
        job_posting_id=job_posting_id,
        meeting_url=meeting_url.strip(),
        meeting_url_normalized=meeting_key,
        bot_name=(bot_name or "Prabhat").strip()[:100] or "Prabhat",
        language_mode=language_mode,
        interview_started=False,
        interview_ended=False,
        is_active=True,
        stopped_reason="none",
    )
    db.add(session)
    db.flush()

    settings: dict[str, Any] = {"language_mode": language_mode}
    if greeting_message:
        settings["greeting_message"] = greeting_message.strip()

    db.add(
        InterviewConfig(
            interview_id=session.id,
            job_posting_id=job_posting_id,
            document_extraction_id=document_extraction_id,
            job_title=title[:255],
            recruiter_name=(user.full_name or user.email)[:255],
            candidate_name=name[:255],
            jd_text=jd,
            cv_text=cv,
            continue_threshold=Decimal(str(app_config.CONTINUE_AVG_THRESHOLD)),
            rolling_window=int(app_config.ROLLING_WINDOW),
            questions_planned_count=len(planned),
            settings_json=settings,
        )
    )
    _add_questions(db, session.id, planned)
    db.add(
        SessionEvent(
            interview_id=session.id,
            event_type="bot_created",
            payload={"bot_id": str(bot_uuid)},
        )
    )
    db.commit()
    db.refresh(session)
    register_bot_interview(str(bot_uuid), session.id)
    logger.info(
        "[interview] created with bot id=%s bot=%s user=%s",
        session.id,
        str(bot_uuid)[:8],
        user.email,
    )
    return session


def attach_bot_to_interview(
    db: Session,
    user: User,
    interview_id: UUID,
    bot_id: str,
    *,
    replace_existing: bool = False,
) -> InterviewSession:
    """Link a Recall bot to a previously scheduled interview."""
    session = get_org_interview(db, user, interview_id)
    if session.interview_ended:
        raise HTTPException(status_code=409, detail="Interview already ended")
    if not session.is_active:
        raise HTTPException(status_code=409, detail="Interview is cancelled")
    if session.bot_id is not None and not replace_existing:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Interview already has a bot. Open the live session or replace via join.",
                "bot_id": str(session.bot_id),
                "interview_id": str(session.id),
            },
        )

    try:
        bot_uuid = UUID(str(bot_id))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid bot_id") from exc

    session.bot_id = bot_uuid
    db.add(
        SessionEvent(
            interview_id=session.id,
            event_type="bot_created",
            payload={"bot_id": str(bot_uuid), "replaced": replace_existing},
        )
    )
    db.commit()
    db.refresh(session)
    register_bot_interview(str(bot_uuid), session.id)
    logger.info(
        "[interview] attached bot id=%s bot=%s",
        session.id,
        str(bot_uuid)[:8],
    )
    return session


def load_join_payload(db: Session, user: User, interview_id: UUID) -> dict[str, Any]:
    """Load frozen config + questions for Send to lobby / join by interview_id."""
    session = get_org_interview(db, user, interview_id)
    if session.interview_ended or not session.is_active:
        raise HTTPException(status_code=409, detail="Interview is not available to start")

    cfg = db.scalar(
        select(InterviewConfig).where(InterviewConfig.interview_id == session.id)
    )
    if cfg is None:
        raise HTTPException(status_code=500, detail="Interview config missing")

    q_rows = db.scalars(
        select(InterviewQuestion)
        .where(InterviewQuestion.interview_id == session.id)
        .order_by(InterviewQuestion.slot.asc())
    ).all()
    if not q_rows:
        raise HTTPException(status_code=500, detail="Interview questions missing")

    settings = cfg.settings_json or {}
    return {
        "interview": session,
        "config": cfg,
        "meeting_url": session.meeting_url,
        "bot_name": session.bot_name,
        "candidate_name": cfg.candidate_name,
        "job_title": cfg.job_title,
        "jdText": cfg.jd_text,
        "cvText": cfg.cv_text,
        "language_mode": session.language_mode,
        "greeting_message": settings.get("greeting_message"),
        "questions": [
            {
                "id": q.external_question_id,
                "difficulty": q.difficulty,
                "source": q.source,
                "question": q.question_text,
            }
            for q in q_rows
        ],
        "planned_bank": [
            BankQuestion(
                id=q.external_question_id,
                difficulty=q.difficulty,
                source=q.source,
                question=q.question_text,
            )
            for q in q_rows
        ],
        "candidate_id": session.candidate_id,
        "job_posting_id": session.job_posting_id,
        "document_extraction_id": cfg.document_extraction_id,
    }


def list_scheduled_interviews(db: Session, user: User) -> list[dict[str, Any]]:
    stmt = (
        select(InterviewSession, InterviewConfig, Candidate, JobPosting)
        .join(InterviewConfig, InterviewConfig.interview_id == InterviewSession.id)
        .join(Candidate, Candidate.id == InterviewSession.candidate_id)
        .join(JobPosting, JobPosting.id == InterviewSession.job_posting_id)
        .where(
            InterviewSession.organization_id == user.organization_id,
            InterviewSession.bot_id.is_(None),
            InterviewSession.interview_ended.is_(False),
            InterviewSession.is_active.is_(True),
        )
        .order_by(InterviewSession.created_at.desc())
    )
    if user.role == "recruiter":
        stmt = stmt.where(InterviewSession.created_by == user.id)

    rows = db.execute(stmt).all()
    out: list[dict[str, Any]] = []
    for session, cfg, candidate, job in rows:
        out.append(
            {
                "id": session.id,
                "candidate_id": session.candidate_id,
                "job_posting_id": session.job_posting_id,
                "candidate_name": cfg.candidate_name,
                "job_title": cfg.job_title,
                "meeting_url": session.meeting_url,
                "language_mode": session.language_mode,
                "bot_name": session.bot_name,
                "questions_planned": cfg.questions_planned_count,
                "created_at": session.created_at,
                "candidate_full_name": candidate.full_name,
                "job_posting_title": job.job_title,
            }
        )
    return out


def cancel_scheduled_interview(db: Session, user: User, interview_id: UUID) -> InterviewSession:
    session = get_org_interview(db, user, interview_id)
    if session.bot_id is not None:
        raise HTTPException(
            status_code=409,
            detail="Cannot cancel after bot was sent to lobby. Leave from the live session.",
        )
    if session.interview_ended:
        raise HTTPException(status_code=409, detail="Interview already ended")
    session.is_active = False
    db.commit()
    db.refresh(session)
    return session


def detach_bot_after_lobby_cancel(bot_id: str) -> None:
    """
    After live Cancel setup removes the Recall bot:
    - If interview never started → clear bot_id so it returns to Scheduled.
    - If already started → mark ended (manual).
    """
    if not bot_id:
        return
    _run_safe("detach_bot", lambda db: _detach_bot(db, bot_id))
    _bot_interview_cache.pop(str(bot_id), None)


def _detach_bot(db: Session, bot_id: str) -> None:
    try:
        bot_uuid = UUID(str(bot_id))
    except ValueError:
        return
    row = db.scalar(
        select(InterviewSession).where(InterviewSession.bot_id == bot_uuid)
    )
    if row is None:
        return
    now = datetime.now(timezone.utc)
    if row.interview_started and not row.interview_ended:
        row.interview_ended = True
        row.is_active = False
        row.stopped_reason = "manual"
        row.completed_at = now
        db.add(
            SessionEvent(
                interview_id=row.id,
                event_type="interview_ended",
                payload={"stopped_reason": "manual", "source": "lobby_cancel"},
            )
        )
    else:
        # Not started yet — restore to scheduled (bot_id NULL)
        row.bot_id = None
        db.add(
            SessionEvent(
                interview_id=row.id,
                event_type="bot_left",
                payload={"bot_id": str(bot_uuid), "source": "lobby_cancel"},
            )
        )


def mark_interview_started(interview_id: str | UUID) -> None:
    _run_safe("mark_started", lambda db: _mark_started(db, interview_id))


def _mark_started(db: Session, interview_id: str | UUID) -> None:
    row = db.get(InterviewSession, UUID(str(interview_id)))
    if row is None:
        return
    now = datetime.now(timezone.utc)
    row.interview_started = True
    if row.started_at is None:
        row.started_at = now
    db.add(
        SessionEvent(
            interview_id=row.id,
            event_type="interview_started",
            payload={},
        )
    )


def mark_interview_ended(
    interview_id: str | UUID,
    stopped_reason: str = "none",
) -> None:
    reason = stopped_reason if stopped_reason in (
        "none",
        "completed_all_questions",
        "low_recent_average",
        "abuse",
        "manual",
    ) else "none"
    _run_safe("mark_ended", lambda db: _mark_ended(db, interview_id, reason))


def _mark_ended(db: Session, interview_id: str | UUID, stopped_reason: str) -> None:
    row = db.get(InterviewSession, UUID(str(interview_id)))
    if row is None:
        return
    now = datetime.now(timezone.utc)
    row.interview_ended = True
    row.is_active = False
    row.stopped_reason = stopped_reason
    row.completed_at = now
    # Mark remaining pending questions
    pending = db.scalars(
        select(InterviewQuestion).where(
            InterviewQuestion.interview_id == row.id,
            InterviewQuestion.status.in_(("pending", "in_progress")),
        )
    ).all()
    for q in pending:
        q.status = "remaining"
    db.add(
        SessionEvent(
            interview_id=row.id,
            event_type="interview_ended",
            payload={"stopped_reason": stopped_reason},
        )
    )


def persist_answer(interview_id: str | UUID, record: Any) -> None:
    _run_safe("persist_answer", lambda db: _persist_answer(db, interview_id, record))


def _persist_answer(db: Session, interview_id: str | UUID, record: Any) -> None:
    iid = UUID(str(interview_id))
    q_index = int(record.question_index)
    existing = db.scalar(
        select(InterviewAnswer).where(
            InterviewAnswer.interview_id == iid,
            InterviewAnswer.question_index == q_index,
        )
    )
    if existing is not None:
        return

    iq = db.scalar(
        select(InterviewQuestion).where(
            InterviewQuestion.interview_id == iid,
            InterviewQuestion.external_question_id == str(record.question_id),
        )
    )
    now = datetime.now(timezone.utc)
    if iq is not None:
        iq.status = "completed"
        iq.completed_at = now
        if iq.asked_at is None:
            iq.asked_at = now

    db.add(
        InterviewAnswer(
            interview_id=iid,
            interview_question_id=iq.id if iq else None,
            question_index=q_index,
            external_question_id=str(record.question_id)[:64],
            difficulty=normalize_difficulty(getattr(record, "difficulty", "Low")),
            source=normalize_source(getattr(record, "source", "jd")),
            question_text=(record.question_text or "")[:10000],
            answer_text=(record.answer_text or "")[:20000],
            score=max(0, min(10, int(record.score))),
            confident=bool(getattr(record, "confident", False)),
            relevant=bool(getattr(record, "relevant", True)),
            strengths=str(getattr(record, "strengths", "") or ""),
            develop=str(getattr(record, "develop", "") or ""),
            fix=str(getattr(record, "fix", "") or ""),
            abuse_flag=bool(getattr(record, "abuse_flag", False)),
            evaluated_at=now,
        )
    )
    db.add(
        SessionEvent(
            interview_id=iid,
            event_type="answer_scored",
            payload={
                "question_index": q_index,
                "score": int(record.score),
                "question_id": str(record.question_id),
            },
        )
    )


def persist_transcript_turn(
    interview_id: str | UUID,
    role: str,
    text: str,
    turn_type: str = "other",
) -> None:
    _run_safe(
        "persist_transcript",
        lambda db: _persist_transcript(db, interview_id, role, text, turn_type),
    )


def _persist_transcript(
    db: Session,
    interview_id: str | UUID,
    role: str,
    text: str,
    turn_type: str,
) -> None:
    cleaned = (text or "").strip()
    if not cleaned:
        return
    role_norm = "assistant" if role == "assistant" else "user"
    type_norm = turn_type if turn_type in _VALID_TURN_TYPES else "other"
    iid = UUID(str(interview_id))
    next_seq = (
        db.scalar(
            select(func.coalesce(func.max(TranscriptTurn.sequence_num), 0)).where(
                TranscriptTurn.interview_id == iid
            )
        )
        or 0
    ) + 1
    db.add(
        TranscriptTurn(
            interview_id=iid,
            sequence_num=int(next_seq),
            role=role_norm,
            text=cleaned,
            turn_type=type_norm,
            spoken_at=datetime.now(timezone.utc),
        )
    )


def update_spoken_questions(interview_id: str | UUID, cache: dict[str, str]) -> None:
    if not cache:
        return
    _run_safe("spoken_cache", lambda db: _update_spoken(db, interview_id, cache))


def _update_spoken(db: Session, interview_id: str | UUID, cache: dict[str, str]) -> None:
    iid = UUID(str(interview_id))
    rows = db.scalars(
        select(InterviewQuestion).where(InterviewQuestion.interview_id == iid)
    ).all()
    for q in rows:
        spoken = cache.get(q.external_question_id)
        if spoken:
            q.spoken_question = spoken
    db.add(
        SessionEvent(
            interview_id=iid,
            event_type="localization_completed",
            payload={"count": len(cache)},
        )
    )


def save_interview_report(
    interview_id: str | UUID,
    report: dict[str, Any],
    *,
    job_title: str = "",
    recruiter_name: str = "",
) -> None:
    _run_safe(
        "save_report",
        lambda db: _save_report(db, interview_id, report, job_title, recruiter_name),
    )


def _parse_bot_uuid(bot_id: str | UUID | None) -> Optional[UUID]:
    if bot_id is None:
        return None
    try:
        return UUID(str(bot_id).strip())
    except (TypeError, ValueError):
        return None


def find_interview_id_by_bot(bot_id: str) -> Optional[str]:
    """Return interview_sessions.id for a Recall bot_id, if present."""
    cached = _bot_interview_cache.get(str(bot_id).strip())
    if cached:
        return cached
    if not is_db_configured():
        return None
    bid = _parse_bot_uuid(bot_id)
    if bid is None:
        return None
    db = get_session_factory()()
    try:
        row = db.scalar(
            select(InterviewSession)
            .where(InterviewSession.bot_id == bid)
            .order_by(InterviewSession.created_at.desc())
        )
        if row is None:
            return None
        iid = str(row.id)
        _bot_interview_cache[str(bot_id).strip()] = iid
        return iid
    except Exception as ex:
        logger.warning("[interview] find_interview_id_by_bot failed: %s", ex)
        return None
    finally:
        db.close()


def load_report_by_bot_id(bot_id: str) -> Optional[dict[str, Any]]:
    """Load full report payload from interview_reports.report_json (DB-first)."""
    if not is_db_configured():
        return None
    bid = _parse_bot_uuid(bot_id)
    if bid is None:
        return None
    db = get_session_factory()()
    try:
        session = db.scalar(
            select(InterviewSession)
            .where(InterviewSession.bot_id == bid)
            .order_by(InterviewSession.created_at.desc())
        )
        if session is None:
            return None
        row = db.scalar(
            select(InterviewReport).where(InterviewReport.interview_id == session.id)
        )
        if row is None:
            return None
        payload = dict(row.report_json) if isinstance(row.report_json, dict) else {}
        payload.setdefault("candidate_name", row.candidate_name)
        payload.setdefault("bot_id", str(session.bot_id) if session.bot_id else str(bot_id))
        payload.setdefault("stopped_reason", row.stopped_reason)
        payload.setdefault("questions_planned", row.questions_planned)
        payload.setdefault("questions_scored", row.questions_scored)
        payload.setdefault(
            "overall_average",
            float(row.overall_average) if row.overall_average is not None else None,
        )
        payload.setdefault(
            "last_4_average",
            float(row.last_n_average) if row.last_n_average is not None else None,
        )
        payload.setdefault("summary_develop", list(row.summary_develop or []))
        payload.setdefault("summary_fix", list(row.summary_fix or []))
        payload["interview_completed"] = True
        payload["completed_at"] = (
            row.completed_at.isoformat() if row.completed_at else payload.get("completed_at")
        )
        payload["interview_id"] = str(session.id)
        return payload
    except Exception as ex:
        logger.warning("[interview] load_report_by_bot_id failed: %s", ex)
        return None
    finally:
        db.close()


def list_db_report_summaries() -> list[dict[str, Any]]:
    """Lightweight report list from Postgres, newest first."""
    if not is_db_configured():
        return []
    db = get_session_factory()()
    try:
        rows = db.execute(
            select(InterviewReport, InterviewSession.bot_id, CandidateFeedback.id)
            .join(InterviewSession, InterviewSession.id == InterviewReport.interview_id)
            .outerjoin(
                CandidateFeedback,
                CandidateFeedback.interview_id == InterviewReport.interview_id,
            )
            .order_by(InterviewReport.completed_at.desc())
        ).all()
        out: list[dict[str, Any]] = []
        for report, bot_uuid, feedback_id in rows:
            out.append(
                {
                    "bot_id": str(bot_uuid) if bot_uuid else None,
                    "candidate_name": report.candidate_name,
                    "overall_average": (
                        float(report.overall_average)
                        if report.overall_average is not None
                        else None
                    ),
                    "questions_scored": report.questions_scored,
                    "questions_planned": report.questions_planned,
                    "stopped_reason": report.stopped_reason,
                    "completed_at": (
                        report.completed_at.isoformat() if report.completed_at else None
                    ),
                    "has_feedback": feedback_id is not None,
                    "interview_id": str(report.interview_id),
                }
            )
        return out
    except Exception as ex:
        logger.warning("[interview] list_db_report_summaries failed: %s", ex)
        return []
    finally:
        db.close()


def candidate_feedback_exists(bot_id: str) -> bool:
    if not is_db_configured():
        return False
    bid = _parse_bot_uuid(bot_id)
    if bid is None:
        return False
    db = get_session_factory()()
    try:
        row = db.scalar(select(CandidateFeedback.id).where(CandidateFeedback.bot_id == bid))
        return row is not None
    except Exception as ex:
        logger.warning("[interview] candidate_feedback_exists failed: %s", ex)
        return False
    finally:
        db.close()


def load_candidate_feedback(bot_id: str) -> Optional[dict[str, Any]]:
    if not is_db_configured():
        return None
    bid = _parse_bot_uuid(bot_id)
    if bid is None:
        return None
    db = get_session_factory()()
    try:
        row = db.scalar(select(CandidateFeedback).where(CandidateFeedback.bot_id == bid))
        if row is None:
            return None
        return {
            "bot_id": str(row.bot_id),
            "overall_rating": int(row.overall_rating),
            "clarity_rating": int(row.clarity_rating),
            "tech_issues": row.tech_issues,
            "improve_text": row.improve_text,
            "would_repeat": row.would_repeat,
            "candidate_name": row.candidate_name,
            "submitted_at": row.submitted_at.isoformat() if row.submitted_at else None,
            "interview_id": str(row.interview_id),
        }
    except Exception as ex:
        logger.warning("[interview] load_candidate_feedback failed: %s", ex)
        return None
    finally:
        db.close()


def save_candidate_feedback(bot_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    """
    Persist feedback to candidate_feedback.
    Requires an interview_sessions row for this bot_id.
    Raises ValueError on validation / duplicate / missing interview.
    """
    if not is_db_configured():
        raise ValueError("Database is not configured")

    bid = _parse_bot_uuid(bot_id)
    if bid is None:
        raise ValueError("Invalid bot_id")

    overall = payload.get("overall_rating")
    clarity = payload.get("clarity_rating")
    tech = payload.get("tech_issues")
    improve = (payload.get("improve_text") or "").strip()
    would_repeat = payload.get("would_repeat")

    if not isinstance(overall, int) or not 1 <= overall <= 5:
        raise ValueError("overall_rating must be 1–5")
    if not isinstance(clarity, int) or not 1 <= clarity <= 5:
        raise ValueError("clarity_rating must be 1–5")
    if tech not in ("none", "minor", "major"):
        raise ValueError("tech_issues must be none, minor, or major")
    if not improve:
        raise ValueError("improve_text is required")
    if len(improve) > 500:
        raise ValueError("improve_text must be at most 500 characters")
    if would_repeat is not None and would_repeat not in ("yes", "maybe", "no"):
        raise ValueError("would_repeat must be yes, maybe, or no")

    db = get_session_factory()()
    try:
        session = db.scalar(
            select(InterviewSession)
            .where(InterviewSession.bot_id == bid)
            .order_by(InterviewSession.created_at.desc())
        )
        if session is None:
            raise ValueError("Interview not found in database for this bot")

        existing = db.scalar(
            select(CandidateFeedback).where(
                or_(
                    CandidateFeedback.bot_id == bid,
                    CandidateFeedback.interview_id == session.id,
                )
            )
        )
        if existing is not None:
            raise ValueError("Feedback already submitted for this interview")

        now = datetime.now(timezone.utc)
        row = CandidateFeedback(
            interview_id=session.id,
            bot_id=bid,
            overall_rating=overall,
            clarity_rating=clarity,
            tech_issues=tech,
            improve_text=improve,
            would_repeat=would_repeat,
            candidate_name=(payload.get("candidate_name") or None),
            submitted_at=now,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return {
            "bot_id": str(row.bot_id),
            "overall_rating": int(row.overall_rating),
            "clarity_rating": int(row.clarity_rating),
            "tech_issues": row.tech_issues,
            "improve_text": row.improve_text,
            "would_repeat": row.would_repeat,
            "candidate_name": row.candidate_name,
            "submitted_at": row.submitted_at.isoformat() if row.submitted_at else None,
            "interview_id": str(row.interview_id),
        }
    except ValueError:
        db.rollback()
        raise
    except Exception as ex:
        db.rollback()
        logger.warning("[interview] save_candidate_feedback failed: %s", ex, exc_info=True)
        raise ValueError(f"Failed to save feedback: {ex}") from ex
    finally:
        db.close()


def _save_report(
    db: Session,
    interview_id: str | UUID,
    report: dict[str, Any],
    job_title: str,
    recruiter_name: str,
) -> None:
    iid = UUID(str(interview_id))
    session = db.get(InterviewSession, iid)
    if session is None:
        return

    cfg = db.scalar(select(InterviewConfig).where(InterviewConfig.interview_id == iid))
    title = (job_title or (cfg.job_title if cfg else "") or "Interview").strip()[:255]
    recruiter = (
        recruiter_name or (cfg.recruiter_name if cfg else "") or "Recruiter"
    ).strip()[:255]
    candidate = str(report.get("candidate_name") or (cfg.candidate_name if cfg else "")).strip()[
        :255
    ]

    stopped = str(report.get("stopped_reason") or "none")
    if stopped not in (
        "none",
        "completed_all_questions",
        "low_recent_average",
        "abuse",
        "manual",
    ):
        stopped = "none"

    stage1_scores = []
    for item in report.get("per_question") or []:
        try:
            idx = int(item.get("question_index", 0))
            if 1 <= idx <= int(app_config.STAGE1_QUESTION_COUNT):
                stage1_scores.append(int(item.get("score", 0)))
        except (TypeError, ValueError):
            continue
    stage1_avg = (
        round(sum(stage1_scores) / len(stage1_scores), 2) if stage1_scores else None
    )
    threshold = float(
        report.get("continue_threshold")
        or (cfg.continue_threshold if cfg else app_config.CONTINUE_AVG_THRESHOLD)
    )
    qualified = bool(stage1_avg is not None and stage1_avg >= threshold)

    existing = db.scalar(
        select(InterviewReport).where(InterviewReport.interview_id == iid)
    )
    now = datetime.now(timezone.utc)
    enriched_report = {
        **report,
        "interview_completed": True,
        "completed_at": now.isoformat(),
        "bot_id": report.get("bot_id")
        or (str(session.bot_id) if session.bot_id else None),
        "candidate_name": candidate or report.get("candidate_name") or "Candidate",
    }
    payload = {
        "job_title": title,
        "recruiter_name": recruiter,
        "candidate_name": candidate or "Candidate",
        "questions_planned": int(report.get("questions_planned") or 0),
        "questions_scored": int(report.get("questions_scored") or 0),
        "overall_average": _dec(report.get("overall_average")),
        "last_n_average": _dec(report.get("last_4_average")),
        "stage1_average": _dec(stage1_avg),
        "stage1_question_count": len(stage1_scores) if stage1_scores else None,
        "rolling_window": int(report.get("rolling_window") or app_config.ROLLING_WINDOW),
        "continue_threshold": Decimal(str(threshold)),
        "qualified": qualified,
        "abuse_warnings": int(report.get("abuse_warnings") or 0),
        "stopped_reason": stopped,
        "summary_develop": list(report.get("summary_develop") or []),
        "summary_fix": list(report.get("summary_fix") or []),
        "report_json": enriched_report,
        "completed_at": now,
    }

    if existing is None:
        db.add(InterviewReport(interview_id=iid, **payload))
    else:
        for k, v in payload.items():
            setattr(existing, k, v)

    session.interview_ended = True
    session.is_active = False
    session.stopped_reason = stopped
    session.completed_at = now


def record_event(
    interview_id: str | UUID,
    event_type: str,
    payload: Optional[dict[str, Any]] = None,
) -> None:
    if event_type not in _VALID_EVENTS:
        return
    _run_safe(
        "event",
        lambda db: _record_event(db, interview_id, event_type, payload or {}),
    )


def _record_event(
    db: Session,
    interview_id: str | UUID,
    event_type: str,
    payload: dict[str, Any],
) -> None:
    db.add(
        SessionEvent(
            interview_id=UUID(str(interview_id)),
            event_type=event_type,
            payload=payload,
        )
    )


def register_bot_interview(bot_id: str, interview_id: str | UUID) -> None:
    if bot_id and interview_id:
        _bot_interview_cache[str(bot_id)] = str(interview_id)


def get_cached_interview_id(bot_id: Optional[str]) -> Optional[str]:
    if not bot_id:
        return None
    return _bot_interview_cache.get(str(bot_id))


def find_interview_id_by_bot(bot_id: str) -> Optional[str]:
    if not bot_id:
        return None
    cached = _bot_interview_cache.get(str(bot_id))
    if cached:
        return cached
    if not is_db_configured():
        return None
    try:
        bot_uuid = UUID(str(bot_id))
    except ValueError:
        return None
    db = get_session_factory()()
    try:
        row = db.scalar(
            select(InterviewSession).where(InterviewSession.bot_id == bot_uuid)
        )
        if row:
            _bot_interview_cache[str(bot_id)] = str(row.id)
            return str(row.id)
        return None
    except Exception as ex:
        logger.warning("[interview] find by bot failed: %s", ex)
        return None
    finally:
        db.close()


def _dec(value: Any) -> Optional[Decimal]:
    if value is None:
        return None
    try:
        return Decimal(str(round(float(value), 2)))
    except (TypeError, ValueError):
        return None


def _run_safe(label: str, fn) -> None:
    if not is_db_configured():
        return
    db = get_session_factory()()
    try:
        fn(db)
        db.commit()
    except Exception as ex:
        db.rollback()
        logger.warning("[interview] %s failed: %s", label, ex, exc_info=True)
    finally:
        db.close()
