"""
Persist completed interview reports to disk so they survive session cleanup.
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


def _reports_dir() -> Path:
    root = Path(__file__).resolve().parent / "reports"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _report_path(bot_id: str) -> Path:
    safe_id = (bot_id or "").strip()
    if not safe_id:
        raise ValueError("bot_id is required")
    return _reports_dir() / f"{safe_id}.json"


def save_report(bot_id: str, report: Dict[str, Any]) -> Path:
    """Write a completed interview report (overwrites prior file for same bot_id)."""
    payload = {
        **report,
        "interview_completed": True,
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }
    path = _report_path(bot_id)
    with _lock:
        path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    logger.info("[REPORT STORE] saved bot=%s path=%s", bot_id[:8], path)
    return path


def load_report(bot_id: str) -> Optional[Dict[str, Any]]:
    """Load a persisted report, or None if not found."""
    path = _report_path(bot_id)
    if not path.is_file():
        return None
    try:
        with _lock:
            data = json.loads(path.read_text(encoding="utf-8"))
        if not data.get("interview_completed"):
            return None
        return data
    except (json.JSONDecodeError, OSError) as ex:
        logger.warning("[REPORT STORE] failed to read %s: %s", path, ex)
        return None


def report_exists(bot_id: str) -> bool:
    return load_report(bot_id) is not None


def list_reports() -> list[Dict[str, Any]]:
    """Return lightweight summaries of all persisted reports, newest first."""
    summaries: list[Dict[str, Any]] = []
    reports_dir = _reports_dir()
    paths = sorted(reports_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    for path in paths:
        try:
            with _lock:
                data = json.loads(path.read_text(encoding="utf-8"))
            if not data.get("interview_completed"):
                continue
            summaries.append(
                {
                    "bot_id": data.get("bot_id") or path.stem,
                    "candidate_name": data.get("candidate_name"),
                    "overall_average": data.get("overall_average"),
                    "questions_scored": data.get("questions_scored"),
                    "questions_planned": data.get("questions_planned"),
                    "stopped_reason": data.get("stopped_reason"),
                    "completed_at": data.get("completed_at"),
                }
            )
        except (json.JSONDecodeError, OSError) as ex:
            logger.warning("[REPORT STORE] skip %s: %s", path, ex)
    return summaries
