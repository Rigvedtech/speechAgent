"""Custom HTTP ATS — config-driven JSON lists + downloads."""

from __future__ import annotations

import os
from typing import Any, Optional
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

import requests

from ats.base import AtsJobsPage, AtsRemoteCandidate, AtsRemoteJob


def _dig(obj: Any, path: Optional[str]) -> Any:
    if not path:
        return None
    cur = obj
    for part in str(path).split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def _fill(template: str, **kwargs: str) -> str:
    out = template
    for key, value in kwargs.items():
        out = out.replace("{" + key + "}", str(value))
    return out


def _as_list(data: Any, preferred_keys: tuple[str, ...]) -> list:
    if isinstance(data, list):
        return data
    if not isinstance(data, dict):
        return []
    for key in preferred_keys:
        items = data.get(key)
        if isinstance(items, list):
            return items
    for key in ("items", "data", "results", "records"):
        items = data.get(key)
        if isinstance(items, list):
            return items
    return []


def _str_or_none(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _append_query(url: str, **params: str) -> str:
    """Merge query params into url (skip empty values)."""
    parsed = urlparse(url)
    existing = dict(parse_qsl(parsed.query, keep_blank_values=True))
    for key, value in params.items():
        if value is not None and str(value).strip() != "":
            existing[key] = str(value)
    return urlunparse(parsed._replace(query=urlencode(existing)))


def _parse_pagination(data: Any, *, page: int, page_size: int, item_count: int) -> dict[str, Any]:
    meta: dict[str, Any] = {
        "page": page,
        "page_size": page_size,
        "total": None,
        "total_pages": None,
        "has_next": item_count >= page_size,
        "has_prev": page > 1,
    }
    if not isinstance(data, dict):
        return meta
    block = data.get("pagination") if isinstance(data.get("pagination"), dict) else data
    if not isinstance(block, dict):
        return meta
    for src, dest in (
        ("page", "page"),
        ("page_size", "page_size"),
        ("total", "total"),
        ("total_pages", "total_pages"),
        ("has_next", "has_next"),
        ("has_prev", "has_prev"),
    ):
        if src in block and block[src] is not None:
            meta[dest] = block[src]
    # coerce types
    try:
        meta["page"] = int(meta["page"])
    except (TypeError, ValueError):
        meta["page"] = page
    try:
        meta["page_size"] = int(meta["page_size"])
    except (TypeError, ValueError):
        meta["page_size"] = page_size
    if meta["total"] is not None:
        try:
            meta["total"] = int(meta["total"])
        except (TypeError, ValueError):
            meta["total"] = None
    if meta["total_pages"] is not None:
        try:
            meta["total_pages"] = int(meta["total_pages"])
        except (TypeError, ValueError):
            meta["total_pages"] = None
    if isinstance(meta.get("has_next"), str):
        meta["has_next"] = meta["has_next"].lower() in ("1", "true", "yes")
    if isinstance(meta.get("has_prev"), str):
        meta["has_prev"] = meta["has_prev"].lower() in ("1", "true", "yes")
    return meta


class CustomAtsProvider:
    """
    Config (organization.ats_config), example:

    {
      "base_url": "http://localhost:1010",
      "auth": { "type": "api_key_header", "header_name": "X-API-Key" },
      "extra_headers": { "X-Original-Domain": "localhost:1010" },
      "jobs": {
        "list_path": "/api/external/v1/requirements",
        "list_query": { "page": "1", "page_size": "10" },
        "id_field": "request_id",
        "title_field": "job_title",
        "description_field": "job_description",
        "status_field": "status",
        "items_key": "requirements"
      },
      "candidates": {
        "list_path": "/api/external/v1/requirements/{request_id}/candidates",
        "list_depends_on": "request_id",
        "id_field": "student_id",
        "name_field": "full_name",
        "email_field": "email",
        "items_key": "candidates"
      },
      "downloads": {
        "jd_path": "/api/external/v1/requirements/{request_id}/jd",
        "resume_path": "/api/external/v1/candidates/{student_id}/resume"
      }
    }

    Legacy flat keys still work: candidates_path, jobs_path, api_key_env.
    api_key is injected by factory from organization.ats_api_key_encrypted.
    """

    name = "custom"

    def __init__(self, config: dict[str, Any], *, api_key: str = ""):
        self.config = config or {}
        self.base_url = str(self.config.get("base_url") or "").rstrip("/")
        if not self.base_url:
            raise ValueError("custom ATS requires ats_config.base_url")

        self.jobs_cfg = dict(self.config.get("jobs") or {})
        self.candidates_cfg = dict(self.config.get("candidates") or {})
        self.downloads_cfg = dict(self.config.get("downloads") or {})
        self.auth_cfg = dict(self.config.get("auth") or {})
        self.extra_headers = {
            str(k): str(v)
            for k, v in dict(self.config.get("extra_headers") or {}).items()
        }
        self.timeout = float(self.config.get("timeout_sec") or 20)

        # Legacy path fallbacks
        if not self.jobs_cfg.get("list_path"):
            self.jobs_cfg["list_path"] = self.config.get("jobs_path") or "/jobs"
        if not self.candidates_cfg.get("list_path"):
            self.candidates_cfg["list_path"] = (
                self.config.get("candidates_path") or "/candidates"
            )

        self.api_key = (api_key or "").strip()
        if not self.api_key:
            env_name = str(self.config.get("api_key_env") or "").strip()
            if env_name:
                self.api_key = os.getenv(env_name, "").strip()

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json", **self.extra_headers}
        if not self.api_key:
            return headers

        auth_type = str(self.auth_cfg.get("type") or "bearer").strip().lower()
        if auth_type in ("api_key_header", "header", "x-api-key"):
            header_name = str(self.auth_cfg.get("header_name") or "X-API-Key").strip()
            headers[header_name] = self.api_key
        else:
            scheme = str(self.auth_cfg.get("scheme") or "Bearer").strip()
            headers["Authorization"] = f"{scheme} {self.api_key}".strip()
        return headers

    def _url(self, path: str) -> str:
        if path.startswith("http://") or path.startswith("https://"):
            return path
        return urljoin(self.base_url + "/", path.lstrip("/"))

    def _get(
        self,
        path: str,
        params: Optional[dict[str, Any]] = None,
        *,
        expect_json: bool = True,
    ) -> Any:
        url = self._url(path)
        try:
            resp = requests.get(
                url,
                headers=self._headers(),
                params=params or {},
                timeout=self.timeout,
            )
        except requests.RequestException as ex:
            raise ValueError(f"ATS request failed: {ex}") from ex
        if resp.status_code >= 400:
            raise ValueError(f"ATS HTTP {resp.status_code}: {resp.text[:300]}")
        if not expect_json:
            return resp
        try:
            return resp.json()
        except Exception as ex:
            raise ValueError("ATS response is not JSON") from ex

    def _parse_job(self, item: dict[str, Any]) -> AtsRemoteJob:
        cfg = self.jobs_cfg
        ext = _dig(item, cfg.get("id_field")) or item.get("external_id") or item.get("id")
        if not ext:
            raise ValueError("ATS job missing id field")
        title = (
            _dig(item, cfg.get("title_field"))
            or item.get("job_title")
            or item.get("title")
            or "Untitled role"
        )
        description = _dig(item, cfg.get("description_field")) or item.get(
            "job_description"
        ) or item.get("description")
        jd_text = (
            _dig(item, cfg.get("jd_text_field"))
            or item.get("jd_text")
            or (str(description) if description else None)
        )
        status = _dig(item, cfg.get("status_field")) or item.get("status")

        # Prefer absolute URL from payload
        jd_url = _str_or_none(
            _dig(item, cfg.get("jd_url_field"))
            or item.get("jd_download_url")
            or item.get("jd_url")
        )
        jd_filename = _str_or_none(
            _dig(item, cfg.get("jd_filename_field"))
            or item.get("jd_file_name")
            or item.get("jd_filename")
        )
        if not jd_url:
            jd_path = self.downloads_cfg.get("jd_path")
            if jd_path:
                jd_url = self._url(
                    _fill(
                        str(jd_path),
                        request_id=str(ext),
                        id=str(ext),
                    )
                )

        return AtsRemoteJob(
            external_id=str(ext),
            job_title=str(title).strip() or "Untitled role",
            jd_text=_str_or_none(jd_text),
            jd_url=jd_url,
            jd_filename=jd_filename,
            description=_str_or_none(status) or _str_or_none(
                item.get("company_name")
            ) or _str_or_none(description),
            raw=item,
        )

    def _parse_candidate(
        self,
        item: dict[str, Any],
        *,
        parent_id: Optional[str] = None,
        requirement: Optional[dict[str, Any]] = None,
    ) -> AtsRemoteCandidate:
        cfg = self.candidates_cfg
        ext = (
            _dig(item, cfg.get("id_field"))
            or item.get("student_id")
            or item.get("external_id")
            or item.get("id")
        )
        if not ext:
            raise ValueError("ATS candidate missing id field")
        name = (
            _dig(item, cfg.get("name_field"))
            or item.get("full_name")
            or item.get("name")
            or "Unknown"
        )
        email = _dig(item, cfg.get("email_field")) or item.get("email")
        phone = (
            _dig(item, cfg.get("phone_field"))
            or item.get("contact_no")
            or item.get("phone")
            or item.get("mobile")
        )
        cv_text = _dig(item, cfg.get("cv_text_field")) or item.get("cv_text") or item.get(
            "resume_text"
        )

        cv_url = _str_or_none(
            _dig(item, cfg.get("cv_url_field"))
            or item.get("resume_download_url")
            or item.get("cv_url")
            or item.get("resume_url")
        )
        cv_filename = _str_or_none(
            _dig(item, cfg.get("cv_filename_field"))
            or item.get("resume_file_name")
            or item.get("cv_filename")
            or item.get("resume_filename")
        )

        if not cv_url:
            resume_path = self.downloads_cfg.get("resume_path")
            if resume_path:
                cv_url = self._url(
                    _fill(
                        str(resume_path),
                        student_id=str(ext),
                        id=str(ext),
                        request_id=str(parent_id or ""),
                    )
                )
                if parent_id:
                    cv_url = _append_query(cv_url, request_id=str(parent_id))
        elif parent_id and "request_id=" not in cv_url:
            cv_url = _append_query(cv_url, request_id=str(parent_id))

        raw = {**item, "_parent_request_id": parent_id} if parent_id else dict(item)
        if requirement:
            raw["_requirement"] = requirement

        return AtsRemoteCandidate(
            external_id=str(ext),
            full_name=str(name).strip() or "Unknown",
            email=_str_or_none(email),
            phone=_str_or_none(phone),
            cv_text=_str_or_none(cv_text),
            cv_url=cv_url,
            cv_filename=cv_filename,
            raw=raw,
        )

    def test_connection(self) -> dict[str, Any]:
        page = self.list_jobs(page=1, page_size=10)
        jobs = page.items
        depends = str(self.candidates_cfg.get("list_depends_on") or "").strip()
        cand_count: Optional[int] = None
        if depends and jobs:
            cands = self.list_candidates(parent_id=jobs[0].external_id)
            cand_count = len(cands)
        elif not depends:
            cand_count = len(self.list_candidates())
        return {
            "ok": True,
            "provider": self.name,
            "base_url": self.base_url,
            "candidates": cand_count,
            "jobs": page.total if page.total is not None else len(jobs),
            "message": "Custom ATS reachable.",
        }

    def list_jobs(
        self,
        *,
        q: Optional[str] = None,
        page: int = 1,
        page_size: int = 10,
    ) -> AtsJobsPage:
        path = str(self.jobs_cfg.get("list_path") or "/jobs")
        params: dict[str, Any] = {}
        list_query = self.jobs_cfg.get("list_query")
        if isinstance(list_query, dict):
            params.update({str(k): v for k, v in list_query.items()})

        page = max(1, int(page or 1))
        page_size = max(1, min(int(page_size or 10), 100))
        page_param = str(
            (self.jobs_cfg.get("pagination") or {}).get("page_param")
            or self.jobs_cfg.get("page_param")
            or "page"
        )
        size_param = str(
            (self.jobs_cfg.get("pagination") or {}).get("page_size_param")
            or self.jobs_cfg.get("page_size_param")
            or "page_size"
        )
        params[page_param] = page
        params[size_param] = page_size
        if q:
            params["q"] = q

        data = self._get(path, params=params)
        preferred = (
            (
                str(self.jobs_cfg["items_key"]),
                "jobs",
                "requirements",
            )
            if self.jobs_cfg.get("items_key")
            else ("jobs", "requirements")
        )
        items = _as_list(data, preferred)
        rows = [self._parse_job(i) for i in items if isinstance(i, dict)]
        if q:
            needle = q.strip().lower()
            rows = [j for j in rows if needle in j.job_title.lower()]

        meta = _parse_pagination(data, page=page, page_size=page_size, item_count=len(rows))
        return AtsJobsPage(
            items=rows,
            page=int(meta["page"]),
            page_size=int(meta["page_size"]),
            total=meta.get("total"),
            total_pages=meta.get("total_pages"),
            has_next=bool(meta.get("has_next")),
            has_prev=bool(meta.get("has_prev")),
        )

    def list_candidates(
        self,
        *,
        q: Optional[str] = None,
        parent_id: Optional[str] = None,
    ) -> list[AtsRemoteCandidate]:
        path_tmpl = str(self.candidates_cfg.get("list_path") or "/candidates")
        depends = str(self.candidates_cfg.get("list_depends_on") or "").strip()

        if depends and not parent_id:
            return []

        if depends and parent_id:
            path = _fill(path_tmpl, **{depends: parent_id, "request_id": parent_id, "id": parent_id})
        else:
            path = path_tmpl

        params: dict[str, Any] = {}
        list_query = self.candidates_cfg.get("list_query")
        if isinstance(list_query, dict):
            params.update({str(k): v for k, v in list_query.items()})
        if q:
            params["q"] = q

        data = self._get(path, params=params)
        preferred = (
            (
                str(self.candidates_cfg["items_key"]),
                "candidates",
                "students",
            )
            if self.candidates_cfg.get("items_key")
            else ("candidates", "students")
        )
        items = _as_list(data, preferred)
        requirement = data.get("requirement") if isinstance(data, dict) else None
        if not isinstance(requirement, dict):
            requirement = None

        rows = [
            self._parse_candidate(i, parent_id=parent_id, requirement=requirement)
            for i in items
            if isinstance(i, dict)
        ]
        if q:
            needle = q.strip().lower()
            rows = [
                c
                for c in rows
                if needle in c.full_name.lower()
                or (c.email and needle in c.email.lower())
            ]
        return rows

    def get_candidate(
        self,
        external_id: str,
        *,
        parent_id: Optional[str] = None,
    ) -> AtsRemoteCandidate:
        if parent_id:
            for c in self.list_candidates(parent_id=parent_id):
                if c.external_id == external_id:
                    return c
        else:
            depends = str(self.candidates_cfg.get("list_depends_on") or "").strip()
            if depends:
                page = 1
                while True:
                    jobs_page = self.list_jobs(page=page, page_size=50)
                    for job in jobs_page.items:
                        for c in self.list_candidates(parent_id=job.external_id):
                            if c.external_id == external_id:
                                return c
                    if not jobs_page.has_next:
                        break
                    page += 1
            else:
                for c in self.list_candidates():
                    if c.external_id == external_id:
                        return c

        detail = self.candidates_cfg.get("detail_path")
        if detail:
            path = _fill(
                str(detail),
                student_id=external_id,
                id=external_id,
                request_id=parent_id or "",
            )
            data = self._get(path)
            item = (
                data.get("candidate")
                if isinstance(data, dict) and "candidate" in data
                else data
            )
            if isinstance(item, dict):
                return self._parse_candidate(item, parent_id=parent_id)

        raise ValueError(f"ATS candidate not found: {external_id}")

    def get_job(self, external_id: str) -> AtsRemoteJob:
        page = 1
        while True:
            jobs_page = self.list_jobs(page=page, page_size=50)
            for j in jobs_page.items:
                if j.external_id == external_id:
                    # Enrich JD URL/filename from candidates endpoint requirement block
                    return self._enrich_job_from_candidates_endpoint(j)
            if not jobs_page.has_next:
                break
            page += 1

        detail = self.jobs_cfg.get("detail_path")
        if detail:
            path = _fill(str(detail), request_id=external_id, id=external_id)
            data = self._get(path)
            item = data.get("job") if isinstance(data, dict) and "job" in data else data
            if isinstance(item, dict):
                return self._parse_job(item)
        path = f"{str(self.jobs_cfg.get('list_path') or '/jobs').rstrip('/')}/{external_id}"
        try:
            data = self._get(path)
            item = data.get("job") if isinstance(data, dict) and "job" in data else data
            if isinstance(item, dict):
                return self._parse_job(item)
        except ValueError:
            pass
        raise ValueError(f"ATS job not found: {external_id}")

    def _enrich_job_from_candidates_endpoint(self, job: AtsRemoteJob) -> AtsRemoteJob:
        """Pull jd_download_url / jd_file_name from …/requirements/{id}/candidates."""
        if job.jd_url and job.jd_filename:
            return job
        depends = str(self.candidates_cfg.get("list_depends_on") or "").strip()
        if not depends:
            return job
        try:
            path_tmpl = str(self.candidates_cfg.get("list_path") or "")
            if not path_tmpl:
                return job
            path = _fill(
                path_tmpl,
                **{depends: job.external_id, "request_id": job.external_id, "id": job.external_id},
            )
            data = self._get(path)
        except ValueError:
            return job
        if not isinstance(data, dict):
            return job
        req = data.get("requirement")
        if not isinstance(req, dict):
            return job
        jd_url = _str_or_none(req.get("jd_download_url") or req.get("jd_url")) or job.jd_url
        jd_filename = _str_or_none(req.get("jd_file_name") or req.get("jd_filename")) or job.jd_filename
        jd_text = job.jd_text or _str_or_none(req.get("job_description"))
        return AtsRemoteJob(
            external_id=job.external_id,
            job_title=job.job_title,
            jd_text=jd_text,
            jd_url=jd_url,
            jd_filename=jd_filename,
            description=job.description,
            raw={**job.raw, "_requirement": req},
        )
