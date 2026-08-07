"""Production JD ↔ CV fit scoring.

Hybrid pipeline
---------------
1) Deterministic skill / domain overlap from structured parse + text signals
2) Groq LLM judgment for experience fit + skill *usage* evidence
3) Weighted blend → final score 0–100 with transparent breakdown + reasons

Scores are always relative to one job posting (never candidate-vs-candidate).
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)

MODEL_VERSION = "jd_cv_hybrid_v2_10pt_stable"

# Weights for final blend (must sum to 1.0)
_W_SKILLS = 0.35
_W_EXPERIENCE = 0.25
_W_USAGE = 0.25
_W_DOMAIN = 0.15

_MAX_JD_CHARS = 4500
_MAX_CV_CHARS = 5500


def _normalize_for_hash(text: str) -> str:
    """Collapse whitespace so trivial spacing edits do not change the fingerprint."""
    return re.sub(r"\s+", " ", (text or "").strip()).lower()


def match_content_fingerprint(
    *,
    jd_text: str,
    cv_text: str,
    jd_structured: Optional[dict[str, Any]] = None,
    cv_structured: Optional[dict[str, Any]] = None,
    jd_domain_tags: Optional[list[str]] = None,
    cv_domain_tags: Optional[list[str]] = None,
    model_version: str = MODEL_VERSION,
) -> str:
    """Stable fingerprint for a JD↔CV scoring input set.

    Used to skip re-scoring when force=true but content/model are unchanged.
    """
    jd_skills = sorted(
        {_norm_skill(s) for s in _skills_from_structured(jd_structured, kind="jd") if _norm_skill(s)}
    )
    cv_skills = sorted(
        {_norm_skill(s) for s in _skills_from_structured(cv_structured, kind="cv") if _norm_skill(s)}
    )
    jd_tags = sorted(
        {
            _norm_skill(t)
            for t in _tags_from_entity(jd_structured, jd_domain_tags, kind="jd")
            if _norm_skill(t)
        }
    )
    cv_tags = sorted(
        {
            _norm_skill(t)
            for t in _tags_from_entity(cv_structured, cv_domain_tags, kind="cv")
            if _norm_skill(t)
        }
    )
    payload = {
        "v": model_version,
        "jd": _normalize_for_hash(jd_text)[:_MAX_JD_CHARS],
        "cv": _normalize_for_hash(cv_text)[:_MAX_CV_CHARS],
        "jd_skills": jd_skills,
        "cv_skills": cv_skills,
        "jd_tags": jd_tags,
        "cv_tags": cv_tags,
        "weights": {
            "skills": _W_SKILLS,
            "experience": _W_EXPERIENCE,
            "usage": _W_USAGE,
            "domain": _W_DOMAIN,
        },
    }
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:40]


def fingerprint_from_breakdown(breakdown: Optional[dict[str, Any]]) -> Optional[str]:
    if not isinstance(breakdown, dict):
        return None
    value = breakdown.get("content_fingerprint")
    return str(value) if value else None


@dataclass
class MatchScoreResult:
    score: float
    score_breakdown: dict[str, Any]
    reasons_json: dict[str, Any]
    domain_overlap: list[str] = field(default_factory=list)
    model_version: str = MODEL_VERSION


def _norm_skill(value: str) -> str:
    text = (value or "").strip().lower()
    text = re.sub(r"[^a-z0-9+#.\s\-]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _skills_from_structured(structured: Optional[dict[str, Any]], *, kind: str) -> list[str]:
    if not isinstance(structured, dict):
        return []
    payload = structured.get(f"parsed_{kind}") or structured
    if not isinstance(payload, dict):
        return []
    if kind == "jd":
        raw = payload.get("required_skills") or payload.get("skills") or []
    else:
        raw = payload.get("skills") or []
    out: list[str] = []
    seen: set[str] = set()
    for item in raw if isinstance(raw, list) else []:
        skill = _norm_skill(str(item))
        if skill and skill not in seen:
            seen.add(skill)
            out.append(skill)
    return out


def _tags_from_entity(
    structured: Optional[dict[str, Any]],
    domain_tags: Optional[list[str]],
    *,
    kind: str,
) -> list[str]:
    tags: list[str] = []
    seen: set[str] = set()
    for source in (domain_tags or [],):
        for item in source:
            tag = _norm_skill(str(item))
            if tag and tag not in seen:
                seen.add(tag)
                tags.append(tag)
    if isinstance(structured, dict):
        payload = structured.get(f"parsed_{kind}") or structured
        if isinstance(payload, dict):
            for item in payload.get("domain_tags") or []:
                tag = _norm_skill(str(item))
                if tag and tag not in seen:
                    seen.add(tag)
                    tags.append(tag)
    return tags


def _skill_coverage(jd_skills: list[str], cv_skills: list[str]) -> tuple[float, list[str], list[str]]:
    """Return (0–100 coverage of JD skills present in CV, matched, missing)."""
    if not jd_skills:
        # No explicit JD skills — use overlap ratio vs CV as weak signal
        if not cv_skills:
            return 50.0, [], []
        return 55.0, cv_skills[:8], []

    cv_set = set(cv_skills)
    # Also allow substring containment (e.g. "sql" in "postgresql")
    matched: list[str] = []
    missing: list[str] = []
    for skill in jd_skills:
        hit = skill in cv_set or any(
            skill in c or c in skill for c in cv_set if len(skill) >= 3 and len(c) >= 3
        )
        if hit:
            matched.append(skill)
        else:
            missing.append(skill)
    coverage = 100.0 * (len(matched) / max(1, len(jd_skills)))
    return round(coverage, 2), matched, missing


def _domain_overlap(jd_tags: list[str], cv_tags: list[str]) -> tuple[float, list[str]]:
    if not jd_tags and not cv_tags:
        return 50.0, []
    if not jd_tags or not cv_tags:
        return 35.0, []
    jd_set, cv_set = set(jd_tags), set(cv_tags)
    overlap = sorted(jd_set & cv_set)
    # Jaccard-ish with bias toward JD coverage
    union = jd_set | cv_set
    jaccard = len(overlap) / max(1, len(union))
    jd_cov = len(overlap) / max(1, len(jd_set))
    score = 100.0 * (0.55 * jd_cov + 0.45 * jaccard)
    return round(score, 2), overlap


def _clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, float(value)))


def _to_ten_scale(score_100: float) -> float:
    """Map 0–100 blend → recruiter-facing 1.0–10.0 (one decimal)."""
    return round(_clamp(float(score_100) / 10.0, 1.0, 10.0), 1)


def _strip_fences(raw: str) -> str:
    text = (raw or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _parse_llm_json(raw: str) -> dict[str, Any]:
    text = _strip_fences(raw)
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass
    # Best-effort salvage of first JSON object
    start, end = text.find("{"), text.rfind("}")
    if start >= 0 and end > start:
        data = json.loads(text[start : end + 1])
        if isinstance(data, dict):
            return data
    raise ValueError("LLM did not return a JSON object")


def _llm_fit_judgment(
    *,
    job_title: str,
    jd_text: str,
    cv_text: str,
    jd_skills: list[str],
    cv_skills: list[str],
    matched_skills: list[str],
    missing_skills: list[str],
) -> dict[str, Any]:
    """Ask Groq for experience_fit, skill_usage, strengths/gaps. Raises on hard failure."""
    import config as app_config
    from groq import Groq

    api_key = getattr(app_config, "GROQ_API_KEY", "") or ""
    if not api_key:
        raise RuntimeError("GROQ_API_KEY is not configured")

    model = getattr(app_config, "GROQ_EVALUATOR_MODEL", None) or getattr(
        app_config, "GROQ_MODEL", "llama-3.1-8b-instant"
    )
    client = Groq(api_key=api_key)

    prompt = f"""Score how well this candidate CV fits THIS job description only.
Do NOT compare to other candidates. Judge only JD ↔ CV fit.

Return STRICT JSON with keys:
- experience_fit: number 0-100 (years + role relevance to the JD; internal scale)
- skill_usage: number 0-100 (evidence skills were USED in projects/roles, not only listed)
- overall_llm: number 0-100 (holistic JD fit; internal scale)
- strengths: array of 2-5 short strings
- gaps: array of 1-5 short strings (missing vs JD)
- summary: one short sentence for a recruiter (do not mention /100)

Job title: {job_title or "(untitled)"}
JD required skills (known): {", ".join(jd_skills[:25]) or "(none extracted)"}
CV skills (known): {", ".join(cv_skills[:30]) or "(none extracted)"}
Already matched skills: {", ".join(matched_skills[:20]) or "(none)"}
Missing JD skills: {", ".join(missing_skills[:20]) or "(none)"}

JOB DESCRIPTION:
{jd_text[:_MAX_JD_CHARS]}

CANDIDATE CV:
{cv_text[:_MAX_CV_CHARS]}
"""

    resp = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a strict technical recruiter scoring one CV against one JD. "
                    "Return valid JSON only. Scores are 0-100 integers/numbers. "
                    "Penalize resume keyword stuffing without usage evidence. "
                    "Reward clear, relevant experience for the JD."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        temperature=0,
        max_tokens=700,
        timeout=60,
        response_format={"type": "json_object"},
    )
    raw = resp.choices[0].message.content or ""
    return _parse_llm_json(raw)


def _fallback_llm_scores(skill_cov: float, domain_score: float) -> dict[str, Any]:
    """Deterministic fallback when Groq is unavailable or fails."""
    experience = round(0.55 * skill_cov + 0.45 * domain_score, 2)
    usage = round(0.70 * skill_cov + 0.30 * domain_score, 2)
    overall = round(0.60 * skill_cov + 0.40 * domain_score, 2)
    return {
        "experience_fit": experience,
        "skill_usage": usage,
        "overall_llm": overall,
        "strengths": ["Scored with deterministic fallback (LLM unavailable)"],
        "gaps": ["LLM judgment skipped — re-run scoring when Groq is available"],
        "summary": "Fallback score from skill/domain overlap only.",
        "_fallback": True,
    }


def score_cv_against_jd(
    *,
    job_title: str,
    jd_text: str,
    cv_text: str,
    jd_structured: Optional[dict[str, Any]] = None,
    cv_structured: Optional[dict[str, Any]] = None,
    jd_domain_tags: Optional[list[str]] = None,
    cv_domain_tags: Optional[list[str]] = None,
) -> MatchScoreResult:
    """Score one CV against one JD. Production entry point for a single pair."""
    jd_body = (jd_text or "").strip()
    cv_body = (cv_text or "").strip()
    if len(jd_body) < 40:
        raise ValueError("JD text is too short to score against")
    if len(cv_body) < 40:
        raise ValueError("CV text is too short to score")

    jd_skills = _skills_from_structured(jd_structured, kind="jd")
    cv_skills = _skills_from_structured(cv_structured, kind="cv")
    jd_tags = _tags_from_entity(jd_structured, jd_domain_tags, kind="jd")
    cv_tags = _tags_from_entity(cv_structured, cv_domain_tags, kind="cv")

    skill_cov, matched, missing = _skill_coverage(jd_skills, cv_skills)
    domain_score, overlap = _domain_overlap(jd_tags, cv_tags)
    fingerprint = match_content_fingerprint(
        jd_text=jd_body,
        cv_text=cv_body,
        jd_structured=jd_structured,
        cv_structured=cv_structured,
        jd_domain_tags=jd_domain_tags,
        cv_domain_tags=cv_domain_tags,
    )

    try:
        llm = _llm_fit_judgment(
            job_title=job_title,
            jd_text=jd_body,
            cv_text=cv_body,
            jd_skills=jd_skills,
            cv_skills=cv_skills,
            matched_skills=matched,
            missing_skills=missing,
        )
        llm_source = "groq"
    except Exception as exc:  # noqa: BLE001
        logger.warning("[jd_cv_match] LLM scoring failed, using fallback: %s", exc)
        llm = _fallback_llm_scores(skill_cov, domain_score)
        llm_source = "fallback"

    experience = _clamp(float(llm.get("experience_fit") or 0))
    usage = _clamp(float(llm.get("skill_usage") or 0))
    overall_llm = _clamp(float(llm.get("overall_llm") or 0))

    # Blend deterministic + LLM on 0–100, then expose final as 1–10 for recruiters.
    final_100 = (
        _W_SKILLS * skill_cov
        + _W_EXPERIENCE * (0.7 * experience + 0.3 * overall_llm)
        + _W_USAGE * (0.7 * usage + 0.3 * overall_llm)
        + _W_DOMAIN * domain_score
    )
    final_100 = round(_clamp(final_100), 2)
    final = _to_ten_scale(final_100)

    strengths = [str(x).strip() for x in (llm.get("strengths") or []) if str(x).strip()][:6]
    gaps = [str(x).strip() for x in (llm.get("gaps") or []) if str(x).strip()][:6]
    if missing and "missing skills" not in " ".join(gaps).lower():
        gaps.append("Missing JD skills: " + ", ".join(missing[:8]))

    breakdown = {
        "scale": "1-10",
        "skills_match": skill_cov,
        "experience_fit": round(experience, 2),
        "skill_usage": round(usage, 2),
        "domain_alignment": domain_score,
        "overall_llm": round(overall_llm, 2),
        "final_100": final_100,
        "weights": {
            "skills_match": _W_SKILLS,
            "experience_fit": _W_EXPERIENCE,
            "skill_usage": _W_USAGE,
            "domain_alignment": _W_DOMAIN,
        },
        "matched_skills": matched[:30],
        "missing_skills": missing[:30],
        "llm_source": llm_source,
        "content_fingerprint": fingerprint,
        "final": final,
    }
    reasons = {
        "summary": str(llm.get("summary") or "").strip()
        or f"Fit score {final:.1f}/10 for this job.",
        "strengths": strengths,
        "gaps": gaps,
        "matched_skills": matched[:20],
        "missing_skills": missing[:20],
    }

    return MatchScoreResult(
        score=final,
        score_breakdown=breakdown,
        reasons_json=reasons,
        domain_overlap=overlap[:40],
        model_version=MODEL_VERSION,
    )


def match_result_dict(result: MatchScoreResult) -> dict[str, Any]:
    return asdict(result)
