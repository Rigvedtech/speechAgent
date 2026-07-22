"""Resolve ATS provider from organization settings."""

from __future__ import annotations

from typing import Any, Optional

from fastapi import HTTPException

from ats.crypto import decrypt_api_key
from ats.custom import CustomAtsProvider
from ats.demo import DemoAtsProvider
from db.models import Organization

SUPPORTED_PROVIDERS = ("demo", "custom")


def get_provider(org: Organization):
    provider = (org.ats_provider or "").strip().lower()
    if not provider:
        raise HTTPException(
            status_code=400,
            detail="ATS is not connected. Configure it in Settings → ATS.",
        )
    config = org.ats_config if isinstance(org.ats_config, dict) else {}
    try:
        if provider == "demo":
            return DemoAtsProvider(config)
        if provider == "custom":
            try:
                api_key = decrypt_api_key(getattr(org, "ats_api_key_encrypted", None))
            except ValueError as ve:
                raise HTTPException(status_code=400, detail=str(ve)) from ve
            return CustomAtsProvider(config, api_key=api_key)
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve)) from ve
    raise HTTPException(
        status_code=400,
        detail=f"Unsupported ATS provider '{provider}'. Supported: {', '.join(SUPPORTED_PROVIDERS)}",
    )


def sanitize_config_for_response(config: Any) -> dict[str, Any]:
    """Never echo secrets; only non-secret config keys."""
    if not isinstance(config, dict):
        return {}
    out = {k: v for k, v in config.items() if k not in ("api_key", "api_token", "password")}
    return out


def _clean_section(section: Any) -> dict[str, Any]:
    if not isinstance(section, dict):
        return {}
    cleaned: dict[str, Any] = {}
    for key, value in section.items():
        if value is None:
            continue
        if isinstance(value, str):
            value = value.strip()
            if value == "":
                continue
        cleaned[str(key)] = value
    return cleaned


def validate_provider_config(provider: str, config: Optional[dict[str, Any]]) -> dict[str, Any]:
    provider = (provider or "").strip().lower()
    cfg = dict(config or {})
    # strip secrets if client accidentally sent them inside config
    for key in ("api_key", "api_token", "password"):
        cfg.pop(key, None)

    if provider not in SUPPORTED_PROVIDERS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported provider. Use one of: {', '.join(SUPPORTED_PROVIDERS)}",
        )

    if provider != "custom":
        return {}

    base = str(cfg.get("base_url") or "").strip()
    if not base.startswith(("http://", "https://")):
        raise HTTPException(
            status_code=400,
            detail="custom provider requires ats_config.base_url (http/https)",
        )

    out: dict[str, Any] = {
        "base_url": base.rstrip("/"),
    }

    auth = _clean_section(cfg.get("auth"))
    if auth:
        out["auth"] = auth
    else:
        out["auth"] = {"type": "api_key_header", "header_name": "X-API-Key"}

    extra = cfg.get("extra_headers")
    if isinstance(extra, dict) and extra:
        out["extra_headers"] = {
            str(k): str(v) for k, v in extra.items() if str(k).strip() and v is not None
        }

    jobs = _clean_section(cfg.get("jobs"))
    if not jobs.get("list_path"):
        # legacy
        legacy_jobs = str(cfg.get("jobs_path") or "").strip()
        jobs["list_path"] = legacy_jobs or "/api/external/v1/requirements"
    jobs.setdefault("id_field", "request_id")
    jobs.setdefault("title_field", "job_title")
    jobs.setdefault("description_field", "job_description")
    jobs.setdefault("status_field", "status")
    jobs.setdefault("items_key", "requirements")
    out["jobs"] = jobs

    cands = _clean_section(cfg.get("candidates"))
    if not cands.get("list_path"):
        legacy_c = str(cfg.get("candidates_path") or "").strip()
        cands["list_path"] = (
            legacy_c or "/api/external/v1/requirements/{request_id}/candidates"
        )
    cands.setdefault("id_field", "student_id")
    cands.setdefault("name_field", "name")
    cands.setdefault("email_field", "email")
    cands.setdefault("phone_field", "contact_no")
    cands.setdefault("items_key", "candidates")
    if "list_depends_on" not in cands and "{request_id}" in str(cands.get("list_path")):
        cands["list_depends_on"] = "request_id"
    out["candidates"] = cands

    downloads = _clean_section(cfg.get("downloads"))
    if downloads:
        out["downloads"] = downloads
    else:
        out["downloads"] = {
            "jd_path": "/api/external/v1/requirements/{request_id}/jd",
            "resume_path": "/api/external/v1/candidates/{student_id}/resume",
        }

    if cfg.get("timeout_sec") is not None:
        try:
            out["timeout_sec"] = float(cfg["timeout_sec"])
        except (TypeError, ValueError):
            pass

    # Keep optional legacy env fallback if explicitly set
    env_name = str(cfg.get("api_key_env") or "").strip()
    if env_name:
        out["api_key_env"] = env_name

    return out
