"""Persistent server logs under backend/logs/."""

from __future__ import annotations

import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

_configured = False
_run_log_path: Optional[Path] = None


def logs_dir() -> Path:
    root = Path(__file__).resolve().parent / "logs"
    root.mkdir(parents=True, exist_ok=True)
    return root


def get_run_log_path() -> Optional[Path]:
    return _run_log_path


def setup_file_logging(*, level: int = logging.INFO, prefix: str = "api_server") -> Path:
    global _configured, _run_log_path
    if _configured and _run_log_path is not None:
        return _run_log_path
    enabled = os.getenv("FILE_LOGGING_ENABLED", "true").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = logs_dir() / f"{prefix}_{stamp}.log"
    if not enabled:
        _configured = True
        _run_log_path = path
        return path
    fmt = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    handler = logging.FileHandler(path, encoding="utf-8")
    handler.setLevel(level)
    handler.setFormatter(fmt)
    root = logging.getLogger()
    root.addHandler(handler)
    if root.level > level or root.level == logging.NOTSET:
        root.setLevel(level)
    _configured = True
    _run_log_path = path
    logging.getLogger(__name__).info("[LOG FILE] Full server log -> %s", path)
    return path