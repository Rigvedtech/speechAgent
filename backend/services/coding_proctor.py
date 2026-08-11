"""Coding-round browser proctoring: frame analysis + integrity summary.

Face analysis reuses FaceAnalyzer (MediaPipe). Browser focus/input/display
signals are accepted from the client and persisted; this module owns
server-authoritative face classification and summary aggregation.
"""

from __future__ import annotations

import base64
import logging
import threading
from datetime import datetime, timezone
from typing import Any, Optional

import numpy as np

from camera_integrity_policy import classify_integrity_risk, significant_extra_faces
from face_analysis import FaceAnalyzer, FrameAnalysisResult, GazeMode

logger = logging.getLogger("services.coding_proctor")

_analyzer_lock = threading.Lock()
_analyzer: Optional[FaceAnalyzer] = None

# Allowed client/server event types (audit trail).
ALLOWED_EVENT_TYPES = frozenset(
    {
        "camera_permission_granted",
        "camera_permission_denied",
        "camera_started",
        "camera_lost",
        "camera_restored",
        "face_ok",
        "no_face",
        "multi_face",
        "gaze_away",
        "tab_hidden",
        "tab_visible",
        "window_blur",
        "window_focus",
        "fullscreen_entered",
        "fullscreen_exited",
        "paste_blocked",
        "copy_attempt",
        "context_menu_blocked",
        "devtools_suspected",
        "second_display_suspected",
        "proctor_gate_passed",
        "proctor_resume",
        "heartbeat",
        "session_started",
        "session_submitted",
    }
)

SEVERITIES = frozenset({"info", "warn", "critical"})


def get_face_analyzer() -> FaceAnalyzer:
    """Process-wide FaceAnalyzer (VIDEO mode needs monotonic timestamps)."""
    global _analyzer
    with _analyzer_lock:
        if _analyzer is None:
            _analyzer = FaceAnalyzer(
                max_faces=5,
                gaze_mode=GazeMode.INTERVIEW,
            )
        return _analyzer


def decode_image_b64(image_b64: str) -> Optional[np.ndarray]:
    """Decode data-URL or raw base64 JPEG/PNG to BGR ndarray."""
    import cv2

    raw = (image_b64 or "").strip()
    if not raw:
        return None
    if "," in raw and raw.lower().startswith("data:"):
        raw = raw.split(",", 1)[1]
    try:
        data = base64.b64decode(raw, validate=False)
    except Exception:
        return None
    if not data:
        return None
    arr = np.frombuffer(data, dtype=np.uint8)
    frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    return frame


def analyze_frame_bgr(frame_bgr: np.ndarray) -> dict[str, Any]:
    """Run face analysis and map to coding-proctor signals."""
    analyzer = get_face_analyzer()
    result: FrameAnalysisResult = analyzer.analyze_bgr(frame_bgr)
    risk = classify_integrity_risk(result)
    multi = significant_extra_faces(result)
    primary_gaze = None
    if result.faces:
        primary_gaze = result.faces[0].gaze.value

    signal: Optional[str] = None
    severity = "info"
    if multi or (result.face_count or 0) >= 2:
        signal = "multi_face"
        severity = "critical"
    elif (result.face_count or 0) <= 0 or risk == "no_face":
        signal = "no_face"
        severity = "warn"
    elif risk in ("looking_side", "looking_away"):
        signal = "gaze_away"
        severity = "warn"
    elif risk == "looking_down":
        # Looking at editor/code is expected — info only.
        signal = "face_ok"
        severity = "info"
    else:
        signal = "face_ok"
        severity = "info"

    return {
        "face_count": int(result.face_count or 0),
        "multi_face": bool(multi or (result.face_count or 0) >= 2),
        "gaze": primary_gaze,
        "risk": risk,
        "signal": signal,
        "severity": severity,
        "gate_ok": int(result.face_count or 0) == 1 and not multi,
    }


def empty_summary() -> dict[str, Any]:
    return {
        "risk_level": "clean",  # clean | review | high
        "warn_count": 0,
        "critical_count": 0,
        "counts": {},
        "last_event_type": None,
        "last_severity": None,
        "updated_at": None,
    }


def apply_events_to_summary(
    summary: Optional[dict[str, Any]],
    events: list[dict[str, Any]],
) -> dict[str, Any]:
    """Merge new events into aggregate summary (idempotent-ish additive)."""
    out = dict(empty_summary())
    if isinstance(summary, dict):
        out["risk_level"] = summary.get("risk_level") or "clean"
        out["warn_count"] = int(summary.get("warn_count") or 0)
        out["critical_count"] = int(summary.get("critical_count") or 0)
        counts = summary.get("counts") or {}
        if isinstance(counts, dict):
            out["counts"] = {str(k): int(v) for k, v in counts.items()}

    for ev in events:
        et = str(ev.get("event_type") or "")
        sev = str(ev.get("severity") or "info")
        if et not in ALLOWED_EVENT_TYPES:
            continue
        if sev not in SEVERITIES:
            sev = "info"
        out["counts"][et] = int(out["counts"].get(et, 0)) + 1
        if sev == "warn":
            out["warn_count"] = int(out["warn_count"]) + 1
        elif sev == "critical":
            out["critical_count"] = int(out["critical_count"]) + 1
        out["last_event_type"] = et
        out["last_severity"] = sev

    critical = int(out["critical_count"])
    warns = int(out["warn_count"])
    high_signals = (
        int(out["counts"].get("multi_face", 0))
        + int(out["counts"].get("devtools_suspected", 0))
        + int(out["counts"].get("camera_lost", 0))
    )
    if critical >= 3 or high_signals >= 3:
        out["risk_level"] = "high"
    elif critical >= 1 or warns >= 3:
        out["risk_level"] = "review"
    else:
        out["risk_level"] = "clean"

    out["updated_at"] = datetime.now(timezone.utc).isoformat()
    return out
