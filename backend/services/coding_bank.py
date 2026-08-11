"""Org shared DSA bank: seed, starters, counts."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import CodingTask, User
from services.coding_bank_catalog import build_seed_catalog
from services.coding_bank_constants import (
    BANK_STARTER_LANGUAGES,
    GENERATE_BATCH_SIZE,
    MAX_PROBLEMS_PER_ORG,
    SEED_TARGET_COUNT,
)
from services.coding_problem_generator import _default_starter

logger = logging.getLogger(__name__)


def _slugify(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (text or "").strip().lower())
    return s.strip("-")[:80] or "problem"


def multi_lang_starters(entry_function: str) -> dict[str, str]:
    entry = (entry_function or "solution").strip() or "solution"
    return {lang: _default_starter(lang, entry) for lang in BANK_STARTER_LANGUAGES}


def bank_languages() -> list[str]:
    return list(BANK_STARTER_LANGUAGES)


def org_active_problem_count(db: Session, organization_id: UUID) -> int:
    rows = db.scalars(
        select(CodingTask.id).where(
            CodingTask.organization_id == organization_id,
            CodingTask.is_active.is_(True),
        )
    ).all()
    return len(rows)


def free_slots(db: Session, organization_id: UUID) -> int:
    return max(0, MAX_PROBLEMS_PER_ORG - org_active_problem_count(db, organization_id))


def generate_batch_size_for_org(db: Session, organization_id: UUID) -> int:
    return min(GENERATE_BATCH_SIZE, free_slots(db, organization_id))


def list_org_bank_tasks(db: Session, organization_id: UUID) -> list[CodingTask]:
    return list(
        db.scalars(
            select(CodingTask)
            .where(
                CodingTask.organization_id == organization_id,
                CodingTask.is_active.is_(True),
            )
            .order_by(CodingTask.created_at.desc(), CodingTask.title)
        ).all()
    )


def _unique_slug(db: Session, organization_id: UUID, base: str) -> str:
    slug = _slugify(base)
    n = 1
    while db.scalar(
        select(CodingTask.id).where(
            CodingTask.organization_id == organization_id,
            CodingTask.slug == slug,
        )
    ):
        n += 1
        slug = f"{_slugify(base)}-{n}"
    return slug


def persist_bank_task(
    db: Session,
    *,
    organization_id: UUID,
    draft: dict[str, Any],
    slug_hint: Optional[str] = None,
) -> CodingTask:
    """Insert one language-agnostic org bank task."""
    title = str(draft.get("title") or "Untitled").strip() or "Untitled"
    entry = str(draft.get("entry_function") or "solution").strip() or "solution"
    starters = draft.get("starter_code_json")
    if not isinstance(starters, dict) or not starters:
        raw_starter = draft.get("starter_code")
        if isinstance(raw_starter, dict):
            starters = {str(k): str(v) for k, v in raw_starter.items()}
        elif isinstance(raw_starter, str) and raw_starter.strip():
            # Expand single-lang AI draft to full bank starters
            starters = multi_lang_starters(entry)
            # Prefer AI starter for python if present
            starters["python"] = raw_starter
        else:
            starters = multi_lang_starters(entry)

    slug = _unique_slug(db, organization_id, slug_hint or str(draft.get("slug") or title))
    now = datetime.now(timezone.utc)
    try:
        estimated = int(
            draft.get("estimated_time_min")
            or draft.get("estimated_minutes")
            or 25
        )
    except (TypeError, ValueError):
        estimated = 25
    estimated = max(5, min(180, estimated))
    row = CodingTask(
        organization_id=organization_id,
        slug=slug,
        title=title[:200],
        difficulty=str(draft.get("difficulty") or "medium").lower()[:20],
        statement=str(draft.get("statement") or ""),
        examples_json=draft.get("examples") or [],
        constraints_text=str(draft.get("constraints_text") or ""),
        starter_code_json=starters,
        entry_function=entry[:120],
        domain_id=None,
        allowed_languages=list(BANK_STARTER_LANGUAGES),
        skill_tags=[str(t) for t in (draft.get("skill_tags") or []) if str(t).strip()][:8],
        estimated_time_min=estimated,
        is_active=True,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.flush()
    return row


def seed_org_bank(
    db: Session,
    user: User,
    *,
    target: int = SEED_TARGET_COUNT,
) -> dict[str, int]:
    """Insert curated problems until org bank reaches target (max 100)."""
    org_id = user.organization_id
    target = max(0, min(int(target), MAX_PROBLEMS_PER_ORG))
    current = org_active_problem_count(db, org_id)
    if current >= target:
        return {"before": current, "inserted": 0, "after": current, "target": target}

    existing_slugs = {
        str(s)
        for s in db.scalars(
            select(CodingTask.slug).where(CodingTask.organization_id == org_id)
        ).all()
    }
    catalog = build_seed_catalog()
    inserted = 0
    for spec in catalog:
        if current + inserted >= target:
            break
        if free_slots(db, org_id) <= 0:
            break
        slug = str(spec["slug"])
        if slug in existing_slugs:
            continue
        draft = {
            **spec,
            "starter_code_json": multi_lang_starters(spec["entry_function"]),
        }
        persist_bank_task(db, organization_id=org_id, draft=draft, slug_hint=slug)
        existing_slugs.add(slug)
        inserted += 1

    db.commit()
    after = org_active_problem_count(db, org_id)
    logger.info(
        "[coding_bank] seed org=%s inserted=%s after=%s target=%s",
        org_id,
        inserted,
        after,
        target,
    )
    return {"before": current, "inserted": inserted, "after": after, "target": target}
