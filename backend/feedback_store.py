"""
Persist candidate interview feedback to disk (one file per bot_id).
"""

from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

_lock = threading.Lock()

TECH_ISSUES = frozenset({"none", "minor", "major"})
WOULD_REPEAT = frozenset({"yes", "maybe", "no"})


def _feedback_dir() -> Path:
    root = Path(__file__).resolve().parent / "feedback"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _feedback_path(bot_id: str) -> Path:
    safe_id = (bot_id or "").strip()
    if not safe_id:
        raise ValueError("bot_id is required")
    return _feedback_dir() / f"{safe_id}.json"


def feedback_exists(bot_id: str) -> bool:
    return _feedback_path(bot_id).is_file()


def save_feedback(bot_id: str, payload: Dict[str, Any]) -> Path:
    overall = payload.get("overall_rating")
    clarity = payload.get("clarity_rating")
    tech = payload.get("tech_issues")
    improve = (payload.get("improve_text") or "").strip()

    if not isinstance(overall, int) or not 1 <= overall <= 5:
        raise ValueError("overall_rating must be 1–5")
    if not isinstance(clarity, int) or not 1 <= clarity <= 5:
        raise ValueError("clarity_rating must be 1–5")
    if tech not in TECH_ISSUES:
        raise ValueError("tech_issues must be none, minor, or major")
    if not improve:
        raise ValueError("improve_text is required")
    if len(improve) > 500:
        raise ValueError("improve_text must be at most 500 characters")

    would_repeat = payload.get("would_repeat")
    if would_repeat is not None and would_repeat not in WOULD_REPEAT:
        raise ValueError("would_repeat must be yes, maybe, or no")

    record = {
        "bot_id": bot_id,
        "overall_rating": overall,
        "clarity_rating": clarity,
        "tech_issues": tech,
        "improve_text": improve,
        "would_repeat": would_repeat,
        "candidate_name": payload.get("candidate_name"),
        "submitted_at": datetime.now(timezone.utc).isoformat(),
    }

    path = _feedback_path(bot_id)
    with _lock:
        if path.is_file():
            raise ValueError("Feedback already submitted for this interview")
        path.write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("[FEEDBACK STORE] saved bot=%s path=%s", bot_id[:8], path)
    return path


def load_feedback(bot_id: str) -> Optional[Dict[str, Any]]:
    path = _feedback_path(bot_id)
    if not path.is_file():
        return None
    try:
        with _lock:
            return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as ex:
        logger.warning("[FEEDBACK STORE] failed to read %s: %s", path, ex)
        return None
