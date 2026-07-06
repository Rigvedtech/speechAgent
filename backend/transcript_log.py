"""
Session transcript logging — full [AI]: / [You]: lines to console, logger, and file.
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_session_files: dict[str, Path] = {}
_session_lines: dict[str, List[str]] = {}


def _transcripts_dir() -> Path:
    root = Path(__file__).resolve().parent / "transcripts"
    root.mkdir(parents=True, exist_ok=True)
    return root


def start_session(bot_id: str) -> None:
    """Open a per-session transcript file."""
    if not bot_id:
        return
    with _lock:
        if bot_id in _session_files:
            return
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = _transcripts_dir() / f"{bot_id[:12]}_{stamp}.txt"
        _session_files[bot_id] = path
        _session_lines[bot_id] = []
        header = f"# Transcript bot={bot_id} started={stamp}\n"
        path.write_text(header, encoding="utf-8")
        logger.info("[TRANSCRIPT] writing to %s", path)


def log_transcript(
    bot_id: Optional[str],
    role: str,
    text: str,
    *,
    persist: bool = True,
) -> None:
    """
    Log one turn. role: 'assistant' -> [AI], 'user' -> [You].
    """
    text = (text or "").strip()
    if not text:
        return

    label = "AI" if role == "assistant" else "You"
    line = f"[{label}]: {text}"
    ts = datetime.now().strftime("%H:%M:%S")
    stamped = f"{ts} {line}"

    print(f"\n{line}", flush=True)
    logger.info(line)

    if not persist or not bot_id:
        return

    with _lock:
        if bot_id not in _session_files:
            start_session(bot_id)
        path = _session_files.get(bot_id)
        lines = _session_lines.setdefault(bot_id, [])
        lines.append(stamped)
        if path:
            with path.open("a", encoding="utf-8") as fh:
                fh.write(stamped + "\n")


def get_session_transcript(bot_id: str) -> List[str]:
    with _lock:
        return list(_session_lines.get(bot_id, []))


def close_session(bot_id: str) -> None:
    with _lock:
        _session_files.pop(bot_id, None)
        _session_lines.pop(bot_id, None)
