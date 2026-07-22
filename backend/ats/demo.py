"""Demo ATS — local sample data for development (no external API)."""

from __future__ import annotations

from typing import Any, Optional

from ats.base import AtsJobsPage, AtsRemoteCandidate, AtsRemoteJob


_DEFAULT_CANDIDATES = [
    {
        "external_id": "demo-cand-1",
        "full_name": "Aisha Khan",
        "email": "aisha.khan@example.com",
        "phone": "+91 98765 43210",
        "cv_text": (
            "Aisha Khan — Data Analyst\n"
            "Experience: 3 years SQL, Power BI, Excel.\n"
            "Projects: sales dashboards, cohort analysis, ETL with Python.\n"
            "Education: B.Sc. Statistics.\n"
        ),
        "cv_filename": "aisha_khan_cv.txt",
    },
    {
        "external_id": "demo-cand-2",
        "full_name": "Rohan Mehta",
        "email": "rohan.mehta@example.com",
        "phone": "+91 99887 76655",
        "cv_text": (
            "Rohan Mehta — Backend Engineer\n"
            "Experience: 4 years Python, FastAPI, PostgreSQL.\n"
            "Projects: interview automation APIs, webhook integrations.\n"
            "Education: B.Tech Computer Science.\n"
        ),
        "cv_filename": "rohan_mehta_cv.txt",
    },
]

_DEFAULT_JOBS = [
    {
        "external_id": "demo-job-1",
        "job_title": "Data Analyst",
        "jd_text": (
            "We are hiring a Data Analyst to build dashboards and analyze business metrics.\n"
            "Must-have: SQL joins and window functions, Excel, Power BI or Tableau.\n"
            "Nice-to-have: Python pandas, stakeholder communication.\n"
            "Responsibilities: ad-hoc reporting, KPI monitoring, data quality checks.\n"
        ),
        "jd_filename": "data_analyst_jd.txt",
        "description": "SQL + BI focused analyst role",
    },
    {
        "external_id": "demo-job-2",
        "job_title": "Backend Engineer",
        "jd_text": (
            "Backend Engineer for our AI interview platform.\n"
            "Must-have: Python, REST APIs, PostgreSQL, authentication.\n"
            "Nice-to-have: FastAPI, Redis, ATS integrations.\n"
            "Responsibilities: design APIs, reliability, integrations with third-party ATS.\n"
        ),
        "jd_filename": "backend_engineer_jd.txt",
        "description": "Python API engineer",
    },
]


def _as_candidate(item: dict[str, Any]) -> AtsRemoteCandidate:
    return AtsRemoteCandidate(
        external_id=str(item["external_id"]),
        full_name=str(item.get("full_name") or "").strip() or "Unknown",
        email=(item.get("email") or None),
        phone=(item.get("phone") or None),
        cv_text=(item.get("cv_text") or None),
        cv_url=(item.get("cv_url") or None),
        cv_filename=(item.get("cv_filename") or None),
        raw=item,
    )


def _as_job(item: dict[str, Any]) -> AtsRemoteJob:
    return AtsRemoteJob(
        external_id=str(item["external_id"]),
        job_title=str(item.get("job_title") or "").strip() or "Untitled role",
        jd_text=(item.get("jd_text") or None),
        jd_url=(item.get("jd_url") or None),
        jd_filename=(item.get("jd_filename") or None),
        description=(item.get("description") or None),
        raw=item,
    )


class DemoAtsProvider:
    name = "demo"

    def __init__(self, config: dict[str, Any]):
        self.config = config or {}
        self._candidates = [
            _as_candidate(c)
            for c in (self.config.get("demo_candidates") or _DEFAULT_CANDIDATES)
        ]
        self._jobs = [
            _as_job(j) for j in (self.config.get("demo_jobs") or _DEFAULT_JOBS)
        ]

    def test_connection(self) -> dict[str, Any]:
        return {
            "ok": True,
            "provider": self.name,
            "candidates": len(self._candidates),
            "jobs": len(self._jobs),
            "message": "Demo ATS ready (sample data, no external API).",
        }

    def list_candidates(
        self, *, q: Optional[str] = None, parent_id: Optional[str] = None
    ) -> list[AtsRemoteCandidate]:
        rows = self._candidates
        if q:
            needle = q.strip().lower()
            rows = [
                c
                for c in rows
                if needle in c.full_name.lower()
                or (c.email and needle in c.email.lower())
            ]
        return rows

    def list_jobs(
        self, *, q: Optional[str] = None, page: int = 1, page_size: int = 10
    ) -> AtsJobsPage:
        rows = self._jobs
        if q:
            needle = q.strip().lower()
            rows = [j for j in rows if needle in j.job_title.lower()]
        page = max(1, int(page or 1))
        page_size = max(1, min(int(page_size or 10), 100))
        total = len(rows)
        start = (page - 1) * page_size
        chunk = rows[start : start + page_size]
        total_pages = max(1, (total + page_size - 1) // page_size) if total else 1
        return AtsJobsPage(
            items=chunk,
            page=page,
            page_size=page_size,
            total=total,
            total_pages=total_pages,
            has_next=page < total_pages,
            has_prev=page > 1,
        )

    def get_candidate(
        self, external_id: str, *, parent_id: Optional[str] = None
    ) -> AtsRemoteCandidate:
        for c in self._candidates:
            if c.external_id == external_id:
                return c
        raise ValueError(f"Demo candidate not found: {external_id}")

    def get_job(self, external_id: str) -> AtsRemoteJob:
        for j in self._jobs:
            if j.external_id == external_id:
                return j
        raise ValueError(f"Demo job not found: {external_id}")
