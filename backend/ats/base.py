"""ATS provider contracts and remote record shapes."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, Protocol


@dataclass
class AtsRemoteCandidate:
    external_id: str
    full_name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    cv_text: Optional[str] = None
    cv_url: Optional[str] = None
    cv_filename: Optional[str] = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class AtsRemoteJob:
    external_id: str
    job_title: str
    jd_text: Optional[str] = None
    jd_url: Optional[str] = None
    jd_filename: Optional[str] = None
    description: Optional[str] = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class AtsJobsPage:
    items: list[AtsRemoteJob]
    page: int = 1
    page_size: int = 10
    total: Optional[int] = None
    total_pages: Optional[int] = None
    has_next: bool = False
    has_prev: bool = False


class AtsProvider(Protocol):
    name: str

    def test_connection(self) -> dict[str, Any]:
        """Raise ValueError on failure; return status payload on success."""
        ...

    def list_candidates(self, *, q: Optional[str] = None) -> list[AtsRemoteCandidate]:
        ...

    def list_jobs(self, *, q: Optional[str] = None) -> list[AtsRemoteJob]:
        ...

    def get_candidate(self, external_id: str) -> AtsRemoteCandidate:
        ...

    def get_job(self, external_id: str) -> AtsRemoteJob:
        ...
