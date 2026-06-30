"""
Forward JD/CV uploads to n8n and normalize the extraction response for the recruiter UI.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)

N8N_URI = os.getenv(
    "N8N_URI",
    "http://localhost:5678/webhook/jd-cv_detail_extraction",
).strip()

_DIFFICULTY_ALIASES = {
    "low": "Low",
    "easy": "Low",
    "beginner": "Low",
    "intermediate": "Intermediate",
    "medium": "Intermediate",
    "mid": "Intermediate",
    "hard": "Hard",
    "difficult": "Hard",
    "advanced": "Hard",
}


def _normalize_difficulty(raw: str) -> str:
    return _DIFFICULTY_ALIASES.get((raw or "").strip().lower(), "Intermediate")


def _normalize_source(raw: str) -> str:
    lower = (raw or "").strip().lower()
    if lower in ("job description", "jd") or lower.startswith("jd"):
        return "jd"
    if "resume" in lower or "cv" in lower:
        return "resume"
    return "other"


def _pick_string(obj: Dict[str, Any], keys: List[str]) -> Optional[str]:
    for key in keys:
        val = obj.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return None


def _unwrap_payload(raw: Any) -> Dict[str, Any]:
    """Flatten n8n shapes: [{ output: { questions }, jdText, cvText }, ...]."""
    if isinstance(raw, list) and raw:
        raw = raw[0]
    if not isinstance(raw, dict):
        return {}

    merged: Dict[str, Any] = dict(raw)

    output = raw.get("output")
    if isinstance(output, dict):
        for key, val in output.items():
            if key not in merged or merged.get(key) in (None, "", []):
                merged[key] = val

    for nest in ("data", "body", "json"):
        inner = merged.get(nest)
        if isinstance(inner, dict):
            nested = _unwrap_payload(inner)
            for key, val in nested.items():
                if key not in merged or merged.get(key) in (None, "", []):
                    merged[key] = val

    return merged


def _find_questions_list(obj: Dict[str, Any]) -> Any:
    output = obj.get("output")
    if isinstance(output, dict) and output.get("questions"):
        return output.get("questions")
    for key in (
        "questions",
        "question_bank",
        "planned_questions",
        "interview_questions",
    ):
        if obj.get(key):
            return obj.get(key)
    return None


def _parse_questions(raw: Any) -> Optional[List[Dict[str, str]]]:
    if not isinstance(raw, list):
        return None
    questions: List[Dict[str, str]] = []
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            continue
        text = _pick_string(item, ["question", "text", "question_text", "content"])
        if not text:
            continue
        questions.append(
            {
                "id": str(item.get("id") or item.get("question_id") or i + 1),
                "difficulty": _normalize_difficulty(str(item.get("difficulty") or item.get("level") or "Low")),
                "source": _normalize_source(str(item.get("source") or item.get("origin") or "jd")),
                "question": text,
            }
        )
    return questions or None


def parse_n8n_response(raw: Any) -> Dict[str, Any]:
    """Normalize n8n JSON into fields the frontend expects."""
    obj = _unwrap_payload(raw)
    return {
        "jdText": _pick_string(obj, ["jdText", "jd_text", "job_description", "jd", "JD"]),
        "cvText": _pick_string(obj, ["cvText", "cv_text", "resume", "cv", "CV", "candidate_resume"]),
        "candidate_name": _pick_string(obj, ["candidate_name", "candidateName", "name"]),
        "questions": _parse_questions(_find_questions_list(obj)),
    }


def extract_jd_cv_files(
    *,
    jd_bytes: Optional[bytes] = None,
    jd_filename: Optional[str] = None,
    cv_bytes: Optional[bytes] = None,
    cv_filename: Optional[str] = None,
    timeout_sec: float = 180.0,
) -> Dict[str, Any]:
    """
    POST multipart jd_file / cv_file to N8N_URI and return normalized extraction.
    """
    if not N8N_URI:
        raise ValueError("N8N_URI is not configured in backend .env")

    if not jd_bytes and not cv_bytes:
        raise ValueError("Upload at least one document (JD or CV)")

    files = []
    if jd_bytes is not None:
        files.append(
            ("jd_file", (jd_filename or "jd.pdf", jd_bytes, "application/octet-stream"))
        )
    if cv_bytes is not None:
        files.append(
            ("cv_file", (cv_filename or "cv.pdf", cv_bytes, "application/octet-stream"))
        )

    logger.info(
        "[N8N] POST %s jd=%s cv=%s",
        N8N_URI,
        bool(jd_bytes),
        bool(cv_bytes),
    )

    try:
        response = requests.post(N8N_URI, files=files, timeout=timeout_sec)
    except requests.RequestException as ex:
        logger.error("[N8N] request failed: %s", ex)
        raise ValueError(f"Could not reach n8n: {ex}") from ex

    if not response.ok:
        message = f"n8n extraction failed ({response.status_code})"
        try:
            body = response.json()
            if isinstance(body, dict) and body.get("message"):
                message = str(body["message"])
        except Exception:
            text = (response.text or "").strip()
            if text:
                message = text[:500]
        raise ValueError(message)

    try:
        payload = response.json()
    except Exception as ex:
        raise ValueError("n8n returned non-JSON response") from ex

    parsed = parse_n8n_response(payload)
    logger.info(
        "[N8N] parsed jd=%s cv=%s questions=%s",
        bool(parsed.get("jdText")),
        bool(parsed.get("cvText")),
        len(parsed.get("questions") or []),
    )
    return parsed
