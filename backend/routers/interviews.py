"""Interview schedule / list / cancel APIs (Phase: interview persistence)."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import List, Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from auth.deps import get_current_user, get_db, require_writer
from db.models import User
from interview_persist import (
    cancel_scheduled_interview,
    create_scheduled_interview,
    list_scheduled_interviews,
)
from language_profiles import resolve_language_mode

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/interviews", tags=["interviews"])


class QuestionBankItem(BaseModel):
    id: str
    difficulty: str
    source: str
    question: str


class ScheduleInterviewRequest(BaseModel):
    meeting_url: str = Field(..., min_length=8)
    candidate_id: UUID
    job_posting_id: UUID
    candidate_name: str = Field(..., min_length=1, max_length=255)
    job_title: str = Field(..., min_length=2, max_length=255)
    jdText: str = Field(..., min_length=100)
    cvText: str = Field(..., min_length=50)
    questions: List[QuestionBankItem] = Field(..., min_length=1)
    language_mode: Literal["english", "hinglish"] = "english"
    bot_name: Optional[str] = Field(None, max_length=100)
    greeting_message: Optional[str] = None
    document_extraction_id: Optional[UUID] = None

    @field_validator("meeting_url", "candidate_name", "job_title", "jdText", "cvText")
    @classmethod
    def strip_text(cls, v: str) -> str:
        return v.strip()


class ScheduledInterviewOut(BaseModel):
    id: UUID
    candidate_id: UUID
    job_posting_id: UUID
    candidate_name: str
    job_title: str
    meeting_url: str
    language_mode: str
    bot_name: str
    questions_planned: int
    created_at: datetime
    candidate_full_name: Optional[str] = None
    job_posting_title: Optional[str] = None


class ScheduleInterviewResponse(BaseModel):
    success: bool = True
    interview: ScheduledInterviewOut
    message: str = "Interview scheduled. Send to lobby when the candidate is ready."


@router.post("/schedule", response_model=ScheduleInterviewResponse)
def schedule_interview(
    body: ScheduleInterviewRequest,
    user: User = Depends(require_writer),
    db: Session = Depends(get_db),
):
    try:
        language = resolve_language_mode(body.language_mode)
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve)) from ve

    session = create_scheduled_interview(
        db,
        user,
        meeting_url=body.meeting_url,
        candidate_id=body.candidate_id,
        job_posting_id=body.job_posting_id,
        candidate_name=body.candidate_name,
        job_title=body.job_title,
        jd_text=body.jdText,
        cv_text=body.cvText,
        questions=[q.model_dump() for q in body.questions],
        language_mode=language,
        bot_name=body.bot_name or "Prabhat",
        greeting_message=body.greeting_message,
        document_extraction_id=body.document_extraction_id,
    )

    from sqlalchemy import select
    from db.models import InterviewConfig

    cfg = db.scalar(
        select(InterviewConfig).where(InterviewConfig.interview_id == session.id)
    )
    planned_count = cfg.questions_planned_count if cfg else len(body.questions)

    return ScheduleInterviewResponse(
        interview=ScheduledInterviewOut(
            id=session.id,
            candidate_id=session.candidate_id,
            job_posting_id=session.job_posting_id,
            candidate_name=body.candidate_name,
            job_title=body.job_title,
            meeting_url=session.meeting_url,
            language_mode=session.language_mode,
            bot_name=session.bot_name,
            questions_planned=planned_count,
            created_at=session.created_at,
        )
    )


@router.get("/scheduled", response_model=List[ScheduledInterviewOut])
def get_scheduled_interviews(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rows = list_scheduled_interviews(db, user)
    return [ScheduledInterviewOut(**row) for row in rows]


@router.post(
    "/scheduled/{interview_id}/cancel",
    response_model=ScheduledInterviewOut,
)
def cancel_scheduled(
    interview_id: UUID,
    user: User = Depends(require_writer),
    db: Session = Depends(get_db),
):
    """
    Cancel a scheduled interview that has not been sent to lobby yet.
    Distinct from POST /api/interviews/{bot_id}/cancel (live lobby teardown).
    """
    session = cancel_scheduled_interview(db, user, interview_id)
    from sqlalchemy import select
    from db.models import InterviewConfig

    cfg = db.scalar(
        select(InterviewConfig).where(InterviewConfig.interview_id == session.id)
    )
    return ScheduledInterviewOut(
        id=session.id,
        candidate_id=session.candidate_id,
        job_posting_id=session.job_posting_id,
        candidate_name=cfg.candidate_name if cfg else "",
        job_title=cfg.job_title if cfg else "",
        meeting_url=session.meeting_url,
        language_mode=session.language_mode,
        bot_name=session.bot_name,
        questions_planned=cfg.questions_planned_count if cfg else 0,
        created_at=session.created_at,
    )
