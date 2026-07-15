"""
Shared logic for resolving interview reports (live session, DB, or disk).
"""

from __future__ import annotations

import logging
from typing import Any, Dict, TYPE_CHECKING

from fastapi import HTTPException

from report_store import load_report, save_report

if TYPE_CHECKING:
    from session_manager import SessionManager

logger = logging.getLogger(__name__)

INTERVIEW_NOT_STARTED = "Interview not started — call POST /api/start first"
INTERVIEW_NOT_COMPLETED = (
    "Interview not completed — wait until the AI delivers the closing message"
)


def resolve_interview_report(
    bot_id: str,
    session_manager: "SessionManager",
) -> Dict[str, Any]:
    """
    Return a completed report for bot_id.

    Order:
    1. Postgres interview_reports (preferred)
    2. Disk file under backend/reports/ (legacy / fallback)
    3. Live in-memory session when interview_ended is set
    """
    try:
        from interview_persist import load_report_by_bot_id

        db_report = load_report_by_bot_id(bot_id)
        if db_report:
            return db_report
    except Exception as ex:
        logger.warning("[REPORT] DB load failed bot=%s: %s", bot_id[:8], ex)

    stored = load_report(bot_id)
    if stored:
        return stored

    session = session_manager.get_session(bot_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Bot {bot_id} not found")

    orch = session.state.interview_orchestrator
    if not orch:
        raise HTTPException(status_code=400, detail=INTERVIEW_NOT_STARTED)

    if not session.state.interview_ended.is_set():
        raise HTTPException(
            status_code=409,
            detail=INTERVIEW_NOT_COMPLETED,
        )

    report = orch.build_report()
    try:
        save_report(bot_id, report)
    except Exception as ex:
        logger.warning("[REPORT] persist failed bot=%s: %s", bot_id[:8], ex)

    if getattr(orch, "db_interview_id", None):
        try:
            from interview_persist import save_interview_report

            save_interview_report(orch.db_interview_id, report)
        except Exception as ex:
            logger.warning(
                "[REPORT] DB persist failed bot=%s: %s", bot_id[:8], ex
            )

    return report
