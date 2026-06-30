"""
Batch pre-localization of interview bank questions (Hinglish).

Runs in a background thread after POST /api/join so per-turn Groq calls are avoided.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Dict, List

from config import GROQ_API_KEY, GROQ_MODEL, OLLAMA_MODEL
from interview_engine import BankQuestion

logger = logging.getLogger(__name__)

BATCH_HINGLISH_SYSTEM = (
    "You are a technical interviewer preparing spoken Hinglish interview questions. "
    "Rewrite each English question into natural spoken Hinglish (Roman script). "
    "Keep SQL, Excel, Power BI, and other technical terms in English. "
    "Do not reveal answers or hints. Max ~35 words per question. "
    'Return JSON only: {"questions": [{"id": "<id>", "spoken": "<hinglish text>"}, ...]}'
)


def localize_planned_questions(
    questions: List[BankQuestion],
    language_mode: str,
) -> Dict[str, str]:
    """
    Return map question_id -> spoken text.
    English mode: identity map (no API call).
    """
    if not questions:
        return {}

    if (language_mode or "english").lower() != "hinglish":
        return {q.id: q.question for q in questions}

    if not GROQ_API_KEY:
        logger.warning("[LOCALIZE] No GROQ_API_KEY — using English bank text for Hinglish")
        return {q.id: q.question for q in questions}

    items = [{"id": q.id, "question": q.question} for q in questions]
    user_content = json.dumps({"questions": items}, ensure_ascii=False)

    messages = [
        {"role": "system", "content": BATCH_HINGLISH_SYSTEM},
        {"role": "user", "content": user_content},
    ]

    raw = ""
    try:
        from groq import Groq

        client = Groq(api_key=GROQ_API_KEY)
        completion = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=messages,
            max_tokens=min(120 * len(questions), 4000),
            temperature=0.2,
            response_format={"type": "json_object"},
        )
        raw = (completion.choices[0].message.content or "").strip()
    except Exception as ex:
        logger.warning("[LOCALIZE] Groq batch failed: %s — trying Ollama", ex)

    if not raw:
        try:
            import ollama

            response = ollama.chat(
                model=OLLAMA_MODEL,
                messages=messages,
                stream=False,
            )
            raw = (response.get("message", {}).get("content") or "").strip()
        except Exception as ex:
            logger.warning("[LOCALIZE] Ollama batch failed: %s", ex)

    cache: Dict[str, str] = {q.id: q.question for q in questions}

    if raw:
        try:
            cleaned = re.sub(
                r"^```(?:json)?\s*|\s*```$", "", raw.strip(), flags=re.IGNORECASE
            )
            data = json.loads(cleaned)
            for entry in data.get("questions", []):
                qid = str(entry.get("id", "")).strip()
                spoken = str(entry.get("spoken", "") or "").strip()
                if qid and spoken and len(spoken) >= 5:
                    cache[qid] = spoken
            logger.info(
                "[LOCALIZE] Hinglish batch ready bot_questions=%d localized=%d",
                len(questions),
                sum(1 for q in questions if cache.get(q.id) != q.question),
            )
        except (json.JSONDecodeError, TypeError, ValueError) as ex:
            logger.warning("[LOCALIZE] JSON parse failed: %s raw=%r", ex, raw[:200])

    return cache
