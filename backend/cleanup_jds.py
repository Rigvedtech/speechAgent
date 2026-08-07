"""Find and soft-delete duplicate or unavailable local job descriptions.

Dry-run is the default:
    python cleanup_jds.py

Apply the reported cleanup:
    python cleanup_jds.py --apply

By default ATS jobs are excluded. Duplicate titles are compared after
case-folding and collapsing whitespace, within the same organization.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable
from uuid import UUID

from sqlalchemy import text

from db.session import get_engine


@dataclass(frozen=True)
class JobRow:
    id: UUID
    organization_id: UUID
    job_title: str
    source: str
    created_at: datetime
    jd_available: bool
    cv_count: int


@dataclass(frozen=True)
class CleanupAction:
    job: JobRow
    reason: str
    survivor_id: UUID | None = None


def _normalized_title(value: str) -> str:
    return " ".join((value or "").split()).casefold()


def _load_jobs(
    organization_id: UUID | None,
    include_ats: bool,
) -> list[JobRow]:
    conditions = [
        "j.deleted_at IS NULL",
        "j.is_active = TRUE",
    ]
    params: dict[str, object] = {}
    if organization_id:
        conditions.append("j.organization_id = :organization_id")
        params["organization_id"] = organization_id
    if not include_ats:
        conditions.append("j.source <> 'ats'")

    statement = text(
        f"""
        SELECT
            j.id,
            j.organization_id,
            j.job_title,
            j.source,
            j.created_at,
            (
                NULLIF(BTRIM(COALESCE(j.jd_text, '')), '') IS NOT NULL
                OR EXISTS (
                    SELECT 1
                    FROM documents d
                    WHERE d.id = j.jd_document_id
                      AND d.organization_id = j.organization_id
                      AND d.document_type = 'jd'
                      AND d.upload_status = 'ready'
                      AND NULLIF(BTRIM(COALESCE(d.extracted_text, '')), '') IS NOT NULL
                )
            ) AS jd_available,
            (
                SELECT COUNT(*)
                FROM documents cv
                WHERE cv.job_posting_id = j.id
                  AND cv.document_type = 'cv'
                  AND cv.source <> 'ats'
            ) AS cv_count
        FROM job_postings j
        WHERE {" AND ".join(conditions)}
        ORDER BY j.organization_id, j.created_at, j.id
        """
    )

    with get_engine().connect() as connection:
        rows = connection.execute(statement, params).mappings().all()
    return [
        JobRow(
            id=row["id"],
            organization_id=row["organization_id"],
            job_title=row["job_title"],
            source=row["source"],
            created_at=row["created_at"],
            jd_available=bool(row["jd_available"]),
            cv_count=int(row["cv_count"] or 0),
        )
        for row in rows
    ]


def _plan_cleanup(jobs: Iterable[JobRow]) -> list[CleanupAction]:
    jobs = list(jobs)
    actions: list[CleanupAction] = [
        CleanupAction(job=job, reason="jd_unavailable")
        for job in jobs
        if not job.jd_available
    ]

    available_groups: dict[tuple[UUID, str], list[JobRow]] = defaultdict(list)
    for job in jobs:
        if job.jd_available:
            available_groups[(job.organization_id, _normalized_title(job.job_title))].append(job)

    for group in available_groups.values():
        if len(group) < 2:
            continue
        # Preserve the row with the most linked local CVs; then prefer the oldest.
        ordered = sorted(
            group,
            key=lambda job: (-job.cv_count, job.created_at, str(job.id)),
        )
        survivor = ordered[0]
        actions.extend(
            CleanupAction(
                job=duplicate,
                reason="duplicate_title",
                survivor_id=survivor.id,
            )
            for duplicate in ordered[1:]
        )

    return sorted(
        actions,
        key=lambda action: (
            str(action.job.organization_id),
            _normalized_title(action.job.job_title),
            action.reason,
            str(action.job.id),
        ),
    )


def _print_plan(jobs: list[JobRow], actions: list[CleanupAction]) -> None:
    print(f"Active local jobs inspected: {len(jobs)}")
    print(f"Cleanup candidates: {len(actions)}")
    if not actions:
        print("No duplicate or unavailable JDs found.")
        return

    for action in actions:
        suffix = (
            f" keep={action.survivor_id}"
            if action.survivor_id
            else ""
        )
        print(
            f"- {action.reason}: id={action.job.id} "
            f'org={action.job.organization_id} title="{action.job.job_title}" '
            f"source={action.job.source} cvs={action.job.cv_count}{suffix}"
        )


def _apply_cleanup(actions: list[CleanupAction]) -> int:
    if not actions:
        return 0

    statement = text(
        """
        UPDATE job_postings
        SET is_active = FALSE,
            deleted_at = NOW(),
            updated_at = NOW()
        WHERE id = :job_id
          AND deleted_at IS NULL
          AND is_active = TRUE
        """
    )
    updated = 0
    with get_engine().begin() as connection:
        for action in actions:
            result = connection.execute(statement, {"job_id": action.job.id})
            updated += int(result.rowcount or 0)
    return updated


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Soft-delete duplicate-title and unavailable local JDs.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply the soft deletes. Without this flag the script is read-only.",
    )
    parser.add_argument(
        "--organization-id",
        type=UUID,
        help="Limit cleanup to one organization UUID.",
    )
    parser.add_argument(
        "--include-ats",
        action="store_true",
        help="Include ATS-sourced jobs (excluded by default).",
    )
    args = parser.parse_args()

    jobs = _load_jobs(args.organization_id, args.include_ats)
    actions = _plan_cleanup(jobs)
    _print_plan(jobs, actions)

    if not args.apply:
        print("\nDRY RUN: no data changed. Re-run with --apply to soft-delete these rows.")
        return 0

    updated = _apply_cleanup(actions)
    print(f"\nApplied cleanup: {updated} job posting(s) soft-deleted.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
