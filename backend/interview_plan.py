"""
Structured interview: JD → 5 themes × 3 questions (15), phase-gate on first N answers, scorecard.

Used by LLMBrain (standalone + ai_bridge). Plan generation is a single non-streaming LLM call.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Callable, List, Optional, Tuple

# --- JSON helpers ---


def _strip_code_fence(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z0-9]*\s*", "", t)
        t = re.sub(r"\s*```\s*$", "", t)
    return t.strip()


def extract_json_obj(text: str) -> Optional[dict[str, Any]]:
    try:
        return json.loads(_strip_code_fence(text))
    except json.JSONDecodeError:
        pass
    m = re.search(r"\{[\s\S]*\}", text)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            return None
    return None


@dataclass
class QuestionPlan:
    """Flattened sequence of 15 questions with 5 theme labels (one per block of 3)."""

    themes: List[str]
    questions: List[str]


@dataclass
class StructuredInterviewRuntime:
    plan: Optional[QuestionPlan] = None
    plan_failed: bool = False
    num_questions_asked: int = 0
    strikes: int = 0
    gate_first_n: int = 5
    strikes_to_end: int = 3
    done: bool = False  # scorecard emitted or early exit finalized


SYSTEM_PLAN_PROMPT = """You design a structured technical phone screen strictly from the job description (JD).
Output ONLY valid JSON (no markdown) with this exact shape:
{
  "themes": [
    {"name": "short theme title", "questions": ["one spoken question?", "...", "..."]},
    ...
  ]
}
Requirements:
- Exactly 5 themes that together cover ALL major JD responsibilities/skills areas.
- Each theme has exactly 3 questions → 15 questions total.
- Questions are stack-agnostic unless the JD names a specific technology; then stay JD-faithful only.
- One clear sentence each, plain English, suitable for live voice/TTS (no bullets, code, numbering).
"""


def flatten_plan_from_json(data: dict[str, Any]) -> Optional[QuestionPlan]:
    themes_raw = data.get("themes")
    if not isinstance(themes_raw, list) or len(themes_raw) != 5:
        return None
    theme_names: List[str] = []
    questions: List[str] = []
    for block in themes_raw:
        if not isinstance(block, dict):
            return None
        name = str(block.get("name", "")).strip()
        qs = block.get("questions")
        if not name or not isinstance(qs, list) or len(qs) != 3:
            return None
        theme_names.append(name)
        for q in qs:
            q = str(q).strip()
            if not q:
                return None
            questions.append(q)
    if len(questions) != 15:
        return None
    return QuestionPlan(themes=theme_names, questions=questions)


def generate_plan_from_jd(
    jd: str,
    *,
    groq_complete: Optional[Callable[..., Any]] = None,
    ollama_chat: Optional[Callable[..., Any]] = None,
    groq_model: str = "llama-3.1-8b-instant",
    ollama_model: str = "llama3.2:3b",
) -> Optional[QuestionPlan]:
    """
    One-shot plan from JD. groq_complete(messages) -> response with .choices[0].message.content
    or ollama_chat(model, messages, stream=False) -> dict with message content.
    """
    jd = (jd or "").strip()
    if not jd:
        return None

    messages = [
        {"role": "system", "content": SYSTEM_PLAN_PROMPT},
        {
            "role": "user",
            "content": "Job description:\n\n" + jd[:12000],
        },
    ]

    raw = ""
    if groq_complete is not None:
        try:
            resp = groq_complete(messages=messages, model=groq_model, max_tokens=2500, temperature=0.2)
            raw = (resp.choices[0].message.content or "").strip()
        except Exception:
            raw = ""

    if not raw and ollama_chat is not None:
        try:
            resp = ollama_chat(model=ollama_model, messages=messages, stream=False)
            raw = (resp.get("message") or {}).get("content") or ""
            raw = str(raw).strip()
        except Exception:
            raw = ""

    data = extract_json_obj(raw) if raw else None
    if not data:
        return None
    return flatten_plan_from_json(data)


GATE_PROMPT = """You are a strict but fair hiring screener.
Given the interview question the candidate was asked and their spoken answer (ASR transcript), decide if this counts as a STRIKE.

Return ONLY valid JSON: {"strike": true|false, "note": "one short reason"}

Set strike=true ONLY if the answer is clearly:
- unrelated to the question or refuses the topic while changing subject,
- evasive or nonsense meant to derail,
- contradicts the resume snapshot in bad faith (claims impossible overlap).

Do NOT strike for: brief but on-topic answers, nervous tone, "I don't know" once, or minor ASR noise.
"""


def assess_phase_gate(
    question: str,
    answer: str,
    resume_excerpt: str,
    *,
    groq_complete: Optional[Callable[..., Any]] = None,
    ollama_chat: Optional[Callable[..., Any]] = None,
    groq_model: str = "llama-3.1-8b-instant",
    ollama_model: str = "llama3.2:3b",
) -> Tuple[bool, str]:
    """Return (strike, note) — strike True if this answer increments the phase-gate counter."""
    messages = [
        {"role": "system", "content": GATE_PROMPT},
        {
            "role": "user",
            "content": (
                f"Question:\n{question}\n\n"
                f"Candidate answer (transcript):\n{answer}\n\n"
                f"Resume excerpt (for contradiction checks):\n{(resume_excerpt or '')[:2000]}"
            ),
        },
    ]
    raw = ""
    if groq_complete is not None:
        try:
            resp = groq_complete(messages=messages, model=groq_model, max_tokens=120, temperature=0)
            raw = (resp.choices[0].message.content or "").strip()
        except Exception:
            raw = ""

    if not raw and ollama_chat is not None:
        try:
            resp = ollama_chat(model=ollama_model, messages=messages, stream=False)
            raw = (resp.get("message") or {}).get("content") or ""
            raw = str(raw).strip()
        except Exception:
            raw = ""

    data = extract_json_obj(raw) if raw else None
    if not data:
        return False, ""
    note = str(data.get("note") or "").strip()
    return bool(data.get("strike")), note


RELEVANCE_SCORE_PROMPT = """You score a candidate's spoken interview answer against ONE interview question (ASR transcript may have typos).

Return ONLY valid JSON: {"score": <integer 1-10>, "reason": "<one short sentence>"}

Rubric:
- 1-3: off-topic, empty, or nonsense relative to the question
- 4-5: minimal relevance, very vague
- 6-7: partially addresses the question with some correct points
- 8-9: solid, relevant, reasonable detail
- 10: excellent depth, specifics, and correctness for a phone screen

Be fair to short but correct answers. Penalize clear derailing or unrelated content.
"""


def score_interview_answer(
    question: str,
    answer: str,
    *,
    theme: str = "",
    groq_complete: Optional[Callable[..., Any]] = None,
    ollama_chat: Optional[Callable[..., Any]] = None,
    groq_model: str = "llama-3.1-8b-instant",
    ollama_model: str = "llama3.2:3b",
) -> Tuple[int, str]:
    """Return (score 1-10, one-line reason) for developer terminal; (-1, '') if unavailable."""
    q = (question or "").strip()
    a = (answer or "").strip()
    if not q or not a:
        return -1, ""

    theme_line = f"JD theme bucket: {theme}\n" if (theme or "").strip() else ""

    messages = [
        {"role": "system", "content": RELEVANCE_SCORE_PROMPT},
        {
            "role": "user",
            "content": theme_line + f"Question:\n{q}\n\nCandidate answer:\n{a[:8000]}",
        },
    ]
    raw = ""
    if groq_complete is not None:
        try:
            resp = groq_complete(messages=messages, model=groq_model, max_tokens=150, temperature=0)
            raw = (resp.choices[0].message.content or "").strip()
        except Exception:
            raw = ""

    if not raw and ollama_chat is not None:
        try:
            resp = ollama_chat(model=ollama_model, messages=messages, stream=False)
            raw = (resp.get("message") or {}).get("content") or ""
            raw = str(raw).strip()
        except Exception:
            raw = ""

    data = extract_json_obj(raw) if raw else None
    if not data:
        return -1, ""
    try:
        sc = int(data.get("score", -1))
    except (TypeError, ValueError):
        return -1, ""
    sc = max(1, min(10, sc))
    reason = str(data.get("reason") or "").strip()
    return sc, reason


SCORECARD_PROMPT = """You summarize a completed technical interview for the hiring manager.
Output plain spoken English only: 4 to 7 short sentences, no markdown.
Cover: overall fit vs the JD themes, 1–2 strengths, 1–2 gaps, and a clear recommendation (proceed / borderline / do not proceed).
Be specific to what the candidate actually said; if the interview ended early, say so calmly.
"""


def generate_scorecard(
    jd: str,
    resume: str,
    themes: List[str],
    conversation_history: List[dict[str, str]],
    *,
    early_exit: bool,
    groq_complete: Optional[Callable[..., Any]] = None,
    ollama_chat: Optional[Callable[..., Any]] = None,
    groq_model: str = "llama-3.1-8b-instant",
    ollama_model: str = "llama3.2:3b",
) -> str:
    """Produce spoken scorecard text."""
    # Compact transcript
    lines: List[str] = []
    for m in conversation_history[-24:]:
        role = m.get("role", "")
        content = (m.get("content") or "").strip()
        if content:
            lines.append(f"{role.upper()}: {content}")
    transcript = "\n".join(lines)

    themes_s = "; ".join(themes) if themes else ""

    messages = [
        {"role": "system", "content": SCORECARD_PROMPT},
        {
            "role": "user",
            "content": (
                f"JD:\n{jd[:6000]}\n\nResume:\n{resume[:4000]}\n\n"
                f"Themes covered: {themes_s}\n"
                f"Early exit / short round: {'yes' if early_exit else 'no'}\n\n"
                f"Conversation:\n{transcript[:12000]}"
            ),
        },
    ]

    raw = ""
    if groq_complete is not None:
        try:
            resp = groq_complete(messages=messages, model=groq_model, max_tokens=500, temperature=0.3)
            raw = (resp.choices[0].message.content or "").strip()
        except Exception:
            raw = ""

    if not raw and ollama_chat is not None:
        try:
            resp = ollama_chat(model=ollama_model, messages=messages, stream=False)
            raw = (resp.get("message") or {}).get("content") or ""
            raw = str(raw).strip()
        except Exception:
            raw = ""

    return raw or (
        "Interview complete. Based on this session’s notes, thank the candidate—HR will follow "
        "up with structured feedback shortly."
    )
