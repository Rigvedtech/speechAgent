"""Auto-assign shared-bank tasks for an interview (language + count)."""

from __future__ import annotations

import random
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import CodingSubmission, CodingTask, InterviewCodingConfig, InterviewSession
from services.coding_bank_constants import MAX_ASSIGNED_PER_INTERVIEW


def pick_tasks_for_interview(
    db: Session,
    *,
    organization_id: UUID,
    language: str,
    count: int,
    job_posting_id: Optional[UUID] = None,
    candidate_id: Optional[UUID] = None,
) -> list[UUID]:
    """Pick up to `count` least-used org bank tasks that support `language`."""
    lang = (language or "python").strip().lower()
    n = max(1, min(int(count), MAX_ASSIGNED_PER_INTERVIEW))

    pool = list(
        db.scalars(
            select(CodingTask).where(
                CodingTask.organization_id == organization_id,
                CodingTask.is_active.is_(True),
            )
        ).all()
    )
    eligible = [
        t
        for t in pool
        if not t.allowed_languages
        or lang in [str(x).lower() for x in t.allowed_languages]
    ]
    if not eligible:
        eligible = pool
    if not eligible:
        return []

    used_counts: dict[UUID, int] = {t.id: 0 for t in eligible}
    for cfg in db.scalars(
        select(InterviewCodingConfig).where(InterviewCodingConfig.enabled.is_(True))
    ).all():
        for tid in cfg.task_ids or []:
            if tid in used_counts:
                used_counts[tid] += 1

    candidate_seen: set[UUID] = set()
    if candidate_id is not None:
        sessions = db.scalars(
            select(InterviewSession).where(
                InterviewSession.organization_id == organization_id,
                InterviewSession.candidate_id == candidate_id,
            )
        ).all()
        interview_ids = [s.id for s in sessions]
        if interview_ids:
            for sub in db.scalars(
                select(CodingSubmission).where(
                    CodingSubmission.interview_id.in_(interview_ids),
                    CodingSubmission.is_demo.is_(False),
                )
            ).all():
                candidate_seen.add(sub.task_id)

    job_used: set[UUID] = set()
    if job_posting_id is not None:
        sessions = db.scalars(
            select(InterviewSession).where(
                InterviewSession.organization_id == organization_id,
                InterviewSession.job_posting_id == job_posting_id,
            )
        ).all()
        iids = [s.id for s in sessions]
        if iids:
            for cfg in db.scalars(
                select(InterviewCodingConfig).where(
                    InterviewCodingConfig.interview_id.in_(iids),
                    InterviewCodingConfig.enabled.is_(True),
                )
            ).all():
                for tid in cfg.task_ids or []:
                    job_used.add(tid)

    ranked = sorted(
        eligible,
        key=lambda task: (
            1 if task.id in candidate_seen else 0,
            1 if task.id in job_used else 0,
            used_counts.get(task.id, 0),
            random.random(),
        ),
    )
    return [t.id for t in ranked[:n]]
