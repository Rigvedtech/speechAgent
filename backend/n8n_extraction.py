"""
Forward JD/CV uploads and question generation to n8n and normalize responses for the recruiter UI.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)

N8N_CV_URI = os.getenv(
    "N8N_CV_URI",
    "http://localhost:5678/webhook/cv_textExtractor",
).strip()
N8N_JD_URI = os.getenv(
    "N8N_JD_URI",
    "http://localhost:5678/webhook/jd_textExtractor",
).strip()
N8N_QUESTIONS_URI = os.getenv(
    "N8N_QUESTIONS_URI",
    "http://localhost:5678/webhook/questionGenrator",
).strip()
N8N_EXTRACTION_TIMEOUT_SEC = float(os.getenv("N8N_EXTRACTION_TIMEOUT_SEC", "180"))

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


def _timeout_sec(timeout_sec: Optional[float] = None) -> float:
    return N8N_EXTRACTION_TIMEOUT_SEC if timeout_sec is None else timeout_sec


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


def _coerce_dict(raw: Any) -> Dict[str, Any]:
    """Parse n8n bodies that may be a dict, list wrapper, or stringified JSON."""
    if isinstance(raw, str):
        text = raw.strip()
        if text.startswith("{") or text.startswith("["):
            try:
                raw = json.loads(text)
            except json.JSONDecodeError:
                return {}
    if isinstance(raw, list) and raw:
        if len(raw) == 1:
            return _coerce_dict(raw[0])
        return {}
    if isinstance(raw, dict):
        return raw
    return {}


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
                "difficulty": _normalize_difficulty(
                    str(item.get("difficulty") or item.get("level") or "Low")
                ),
                "source": _normalize_source(str(item.get("source") or item.get("origin") or "jd")),
                "question": text,
            }
        )
    return questions or None


def _build_jd_text(structured: Dict[str, Any]) -> str:
    parts: List[str] = []
    if structured.get("job_title"):
        parts.append(f"Job Title: {structured['job_title']}")
    if structured.get("location"):
        parts.append(f"Location: {structured['location']}")
    if structured.get("experience_range"):
        parts.append(f"Experience: {structured['experience_range']}")
    if structured.get("minimum_qualification"):
        parts.append(f"Qualification: {structured['minimum_qualification']}")
    skills = structured.get("skills_required")
    if isinstance(skills, list) and skills:
        parts.append("Skills Required: " + ", ".join(str(skill) for skill in skills))
    if structured.get("jd_summary"):
        parts.append(str(structured["jd_summary"]))
    plain = _pick_string(structured, ["jdText", "jd_text", "job_description", "jd", "JD"])
    if plain and plain not in parts:
        parts.append(plain)
    return "\n\n".join(part.strip() for part in parts if part and str(part).strip())


def _build_cv_text(structured: Dict[str, Any]) -> str:
    raw = _pick_string(structured, ["raw_text", "cvText", "cv_text", "resume", "cv", "CV"])
    if raw:
        return raw
    summary = structured.get("summary")
    if isinstance(summary, str) and summary.strip():
        return summary.strip()
    return json.dumps(structured, ensure_ascii=False) if structured else ""


def parse_jd_response(raw: Any) -> Dict[str, Any]:
    obj = _coerce_dict(raw) or _unwrap_payload(raw)
    jd_text = _build_jd_text(obj)
    return {
        "jdText": jd_text,
        "jdStructured": obj or None,
    }


def parse_cv_response(raw: Any) -> Dict[str, Any]:
    obj = _coerce_dict(raw) or _unwrap_payload(raw)
    return {
        "cvText": _build_cv_text(obj),
        "cvStructured": obj or None,
        "candidate_name": _pick_string(obj, ["name", "candidate_name", "candidateName"]),
    }


def parse_questions_response(raw: Any) -> Dict[str, Any]:
    obj = _unwrap_payload(raw)
    if not obj and isinstance(raw, list):
        obj = _unwrap_payload(raw)
    return {"questions": _parse_questions(_find_questions_list(obj))}


def _post_n8n(
    uri: str,
    *,
    files: Optional[List[tuple]] = None,
    data: Optional[Dict[str, str]] = None,
    timeout_sec: Optional[float] = None,
) -> Any:
    if not uri:
        raise ValueError("n8n webhook URI is not configured in backend .env")

    try:
        response = requests.post(
            uri,
            files=files,
            data=data,
            timeout=_timeout_sec(timeout_sec),
        )
    except requests.RequestException as ex:
        logger.error("[N8N] request failed (%s): %s", uri, ex)
        raise ValueError(f"Could not reach n8n: {ex}") from ex

    if not response.ok:
        message = f"n8n request failed ({response.status_code})"
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
        return response.json()
    except Exception as ex:
        raise ValueError("n8n returned non-JSON response") from ex


def extract_cv_file(
    *,
    cv_bytes: bytes,
    cv_filename: Optional[str] = None,
    timeout_sec: Optional[float] = None,
) -> Dict[str, Any]:
    """POST multipart `cv` to N8N_CV_URI and return normalized CV extraction."""
    logger.info("[N8N] POST %s (cv file)", N8N_CV_URI)
    payload = _post_n8n(
        N8N_CV_URI,
        files=[("cv", (cv_filename or "cv.pdf", cv_bytes, "application/octet-stream"))],
        timeout_sec=timeout_sec,
    )
    parsed = parse_cv_response(payload)
    logger.info(
        "[N8N] parsed cv=%s candidate=%s",
        bool(parsed.get("cvText")),
        bool(parsed.get("candidate_name")),
    )
    return parsed


def extract_jd_file(
    *,
    jd_bytes: bytes,
    jd_filename: Optional[str] = None,
    timeout_sec: Optional[float] = None,
) -> Dict[str, Any]:
    """POST multipart `jd` to N8N_JD_URI and return normalized JD extraction."""
    logger.info("[N8N] POST %s (jd file)", N8N_JD_URI)
    payload = _post_n8n(
        N8N_JD_URI,
        files=[("jd", (jd_filename or "jd.pdf", jd_bytes, "application/octet-stream"))],
        timeout_sec=timeout_sec,
    )
    parsed = parse_jd_response(payload)
    logger.info("[N8N] parsed jd=%s", bool(parsed.get("jdText")))
    return parsed


def generate_questions(
    *,
    jd_text: str,
    cv_text: str,
    candidate_name: Optional[str] = None,
    language_mode: Optional[str] = None,
    timeout_sec: Optional[float] = None,
) -> Dict[str, Any]:
    """POST form `jdText` + `cvText` to N8N_QUESTIONS_URI and return normalized questions."""
    jd_text = (jd_text or "").strip()
    cv_text = (cv_text or "").strip()
    if not jd_text or not cv_text:
        raise ValueError("Both jdText and cvText are required to generate questions")

    data: Dict[str, str] = {"jdText": jd_text, "cvText": cv_text}
    if candidate_name and candidate_name.strip():
        data["candidate_name"] = candidate_name.strip()
    if language_mode and language_mode.strip():
        data["language_mode"] = language_mode.strip()

    logger.info("[N8N] POST %s (generate questions)", N8N_QUESTIONS_URI)
    payload = _post_n8n(N8N_QUESTIONS_URI, data=data, timeout_sec=timeout_sec)
    parsed = parse_questions_response(payload)
    logger.info("[N8N] parsed questions=%s", len(parsed.get("questions") or []))
    return parsed
