"""
JD/CV extraction adapters + interview question generation normalization.

- CV/JD extraction still proxies webhook calls (n8n-style payloads).
- Interview question generation now runs locally via Groq with strict JSON output.
"""

from __future__ import annotations

import json
import logging
import os
import re
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

def _build_question_prompt(jd_text: str, cv_text: str, plan) -> str:
    from question_plan import QuestionPlan, format_id_span

    if not isinstance(plan, QuestionPlan):
        raise TypeError("plan must be a QuestionPlan")
    low_span = format_id_span(*plan.id_range("beginner"))
    mid_span = format_id_span(*plan.id_range("intermediate"))
    hard_span = format_id_span(*plan.id_range("hard"))
    jd_span = format_id_span(1, plan.jd_count) if plan.jd_count else ""
    resume_span = format_id_span(*plan.id_range("hard")) if plan.resume_count else ""
    return f"""You are conducting a LIVE technical interview right now. The candidate is sitting across from you. You have already read their resume and the job description.

Your goal is to assess:
- Technical competency
- Depth of experience
- Practical implementation knowledge
- Authenticity of resume claims
- Match between candidate experience and job requirements

QUESTION DISTRIBUTION

Generate exactly {plan.total} questions.

{jd_span}:
- Based primarily on the skills, technologies, frameworks, tools, and responsibilities from the job description.
- Include a mix of conceptual understanding and practical implementation experience.
- Pull REAL nouns (specific tools, stack, technologies) from the JD into your questions.
- Ask questions naturally as a real interviewer would during a technical interview.
- source must be "jd"

{resume_span}:
- Based primarily on the candidate's Resume/CV.
- Focus on specific projects, work experience, achievements, technologies explicitly mentioned in the resume.
- USE THE ACTUAL PROJECT NAMES, COMPANY NAMES from the resume in your questions.
- Ask for implementation details, decisions made, challenges faced, tradeoffs, debugging approaches, and ownership.
- These questions verify whether the candidate genuinely worked on what they claim.
- source must be "resume"

DIFFICULTY DISTRIBUTION

{low_span}:
Difficulty: Low (beginner)
Count: {plan.beginner}
- Fundamentals
- Basic implementation experience
- Technology familiarity
- source: jd

{mid_span}:
Difficulty: Intermediate
Count: {plan.intermediate}
- Practical engineering knowledge
- Real-world development experience
- Design choices and tradeoffs
- source: jd

{hard_span}:
Difficulty: Hard
Count: {plan.hard}
- Deep resume validation
- Project implementation details
- Technical decisions
- Problem-solving experiences
- Ownership and impact
- source: resume

QUESTION STYLE RULES (for voice/TTS):

- Sound like a real interviewer speaking to a person, not like ChatGPT.
- Use natural conversational language.
- Keep questions SHORT (2-4 sentences max) - they will be read by TTS.
- Do NOT say: "your resume", "the job description", "our company", "this position"
- Do NOT use stiff openers like: "Explain the concept of...", "What is the difference between...", "Describe..."
- PREFER natural phrasing: "So...", "Tell me...", "Walk me through...", "How did you...", "I noticed..."
- One question = one ask. No multi-part laundry lists.
- No coding exercises.
- No LeetCode-style problems.
- No system design questions unless explicitly required in the JD.
- Prioritize practical experience over theory.

EXAMPLES OF GOOD QUESTIONS:
- "So you worked with React - how do you typically handle state management?"
- "In the HRMS project at Infosys, you built authentication - how did you decide between JWT and session-based auth?"
- "What are React hooks and when do you use them?"
- "Tell me about a time you had to optimize database queries."

OUTPUT FORMAT

Return ONLY a JSON object using this EXACT structure:

{{
  "questions": [
    {{
      "id": 1,
      "difficulty": "Low",
      "source": "jd",
      "question": "Your question text here"
    }},
    {{
      "id": 2,
      "difficulty": "Low",
      "source": "jd",
      "question": "Your question text here"
    }}
  ]
}}

CRITICAL:
- Include "id" field for each question (1 through {plan.total})
- Include "difficulty" field: "Low", "Intermediate", or "Hard"
- Include "source" field: "jd" or "resume"
- Include "question" field with the actual question text
- The questions array MUST contain exactly {plan.total} items
- Do not include explanations
- Do not include answers
- Do not include markdown
- Do not include any text outside the JSON object

TTS PRONUNCIATION RULES:

Avoid acronyms that sound awkward when spoken. Use these alternatives:

Technical Terms:
- Instead of "VLANs" -> say "virtual LANs" or "V-L-A-Ns" (with hyphens)
- Instead of "API" -> say "A-P-I" (with hyphens) or just "API endpoint"
- Instead of "JWT" -> say "J-W-T tokens" or "JSON web tokens"
- Instead of "SQL" -> say "S-Q-L" or "sequel" (choose one consistently)
- Instead of "CRUD" -> say "create, read, update, delete operations"
- Instead of "REST" -> say "REST-ful" or "R-E-S-T"
- Instead of "DNS" -> say "D-N-S" or "domain name system"
- Instead of "SSL/TLS" -> say "S-S-L" or "secure connections"

TTS PRONUNCIATION RULES:

Write ALL technical terms, acronyms, and technologies in LOWERCASE so TTS pronounces them correctly:
- vlans (not VLANs)
- api (not API)
- jwt (not JWT)
- mern (not MERN)
- tcp/ip (not TCP/IP)
- dns (not DNS)
- react, node, docker, aws (all lowercase)

NEVER use underscores (_) and (/) - use spaces instead:
- "user id" not "user_id"
- "api key" not "api_key"
- tcp-ip not tcp/ip

JOB DESCRIPTION:
{jd_text}

CANDIDATE RESUME:
{cv_text}
"""

_MAX_QUESTION_JD_CHARS = 2200
_MAX_QUESTION_CV_CHARS = 2500
_QUESTION_GEN_MAX_TOKENS = 3500

_QUESTION_ACRONYM_RE = re.compile(
    r"\b(API|JWT|SQL|CRUD|REST|DNS|SSL|TLS|MERN|TCP/IP|TCP|VLAN|VLANs|AWS)\b"
)


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


def _sanitize_question_for_tts(text: str) -> str:
    out = (text or "").strip()
    out = out.replace("_", " ")
    out = out.replace("/", "-")
    out = re.sub(r"\s+", " ", out).strip()
    out = _QUESTION_ACRONYM_RE.sub(lambda m: m.group(1).lower(), out)
    return out


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
                "question": _sanitize_question_for_tts(text),
            }
        )
    return questions or None


def _coerce_llm_json_object(raw: str) -> Dict[str, Any]:
    text = (raw or "").strip()
    if not text:
        return {}
    try:
        obj = json.loads(text)
        return obj if isinstance(obj, dict) else {}
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            try:
                obj = json.loads(text[start : end + 1])
                return obj if isinstance(obj, dict) else {}
            except Exception:
                return {}
    return {}


def _is_valid_generated_distribution(questions: List[Dict[str, str]], plan) -> bool:
    if len(questions) != plan.total:
        return False
    low_lo, low_hi = plan.id_range("beginner")
    mid_lo, mid_hi = plan.id_range("intermediate")
    hard_lo, hard_hi = plan.id_range("hard")
    for i, q in enumerate(questions, start=1):
        if str(q.get("id")) != str(i):
            return False
        difficulty = q.get("difficulty")
        source = q.get("source")
        if low_lo and low_lo <= i <= low_hi:
            if difficulty != "Low" or source != "jd":
                return False
        elif mid_lo and mid_lo <= i <= mid_hi:
            if difficulty != "Intermediate" or source != "jd":
                return False
        elif hard_lo and hard_lo <= i <= hard_hi:
            if difficulty != "Hard" or source != "resume":
                return False
        else:
            return False
    return True


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


def _clip_for_question_gen(text: str, limit: int) -> str:
    raw = (text or "").strip()
    if len(raw) <= limit:
        return raw
    return raw[:limit].rsplit(" ", 1)[0].strip() + "\n[truncated]"


def generate_questions(
    *,
    jd_text: str,
    cv_text: str,
    candidate_name: Optional[str] = None,
    language_mode: Optional[str] = None,
    timeout_sec: Optional[float] = None,
) -> Dict[str, Any]:
    """Generate questions locally (Groq) using strict JSON prompt + TTS-safe normalization."""
    jd_text = (jd_text or "").strip()
    cv_text = (cv_text or "").strip()
    if not jd_text or not cv_text:
        raise ValueError("Both jdText and cvText are required to generate questions")
    _ = candidate_name, language_mode

    try:
        import config as app_config
        from groq import Groq
        from groq_runtime import groq_kwargs
    except Exception as ex:
        logger.error("[QUESTION-GEN] Groq import failed: %s", ex)
        raise ValueError("Local question generation is unavailable") from ex

    api_key = getattr(app_config, "GROQ_API_KEY", "")
    if not api_key:
        raise ValueError("GROQ_API_KEY is not configured")

    jd_text = _clip_for_question_gen(jd_text, _MAX_QUESTION_JD_CHARS)
    cv_text = _clip_for_question_gen(cv_text, _MAX_QUESTION_CV_CHARS)
    model = getattr(app_config, "GROQ_EVALUATOR_MODEL", "openai/gpt-oss-20b")
    plan = app_config.QUESTION_PLAN
    logger.info(
        "[QUESTION-GEN] plan total=%s beginner=%s intermediate=%s hard=%s adjusted=%s",
        plan.total,
        plan.beginner,
        plan.intermediate,
        plan.hard,
        plan.adjusted,
    )
    prompt = _build_question_prompt(jd_text, cv_text, plan)
    client = Groq(api_key=api_key)
    req_timeout = int(timeout_sec or 90)

    last_err = "invalid question payload"
    last_count = 0
    for attempt in range(1, 3):
        user_content = prompt
        if attempt > 1 and last_count:
            user_content = (
                f"{prompt}\n\nCORRECTION: Your previous JSON had {last_count} questions. "
                f"Return EXACTLY {plan.total} questions with ids 1-{plan.total}, "
                f"{plan.beginner} Low (jd), {plan.intermediate} Intermediate (jd), "
                f"{plan.hard} Hard (resume). No fewer."
            )
        try:
            resp = client.chat.completions.create(
                **groq_kwargs(
                    model,
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                "Return only strict valid JSON with key 'questions'. "
                                f"The questions array length must be exactly {plan.total}. "
                                "No markdown. No explanation."
                            ),
                        },
                        {"role": "user", "content": user_content},
                    ],
                    max_tokens=_QUESTION_GEN_MAX_TOKENS,
                    temperature=0.35,
                    json_mode=True,
                    timeout=req_timeout,
                )
            )
            raw = resp.choices[0].message.content or ""
            payload = _coerce_llm_json_object(raw)
            questions = _parse_questions(payload.get("questions")) or []
            last_count = len(questions)
            if _is_valid_generated_distribution(questions, plan):
                logger.info("[QUESTION-GEN] generated questions=%s", len(questions))
                return {"questions": questions}
            last_err = "shape/distribution mismatch"
            logger.warning(
                "[QUESTION-GEN] invalid payload attempt=%s count=%s",
                attempt,
                len(questions),
            )
        except Exception as ex:
            last_err = str(ex)
            logger.warning("[QUESTION-GEN] failed attempt=%s: %s", attempt, ex)
            err_l = last_err.lower()
            if "413" in last_err or "request too large" in err_l or "tokens per minute" in err_l:
                break

    raise ValueError(f"Question generation failed: {last_err}")
