"""Shared JD/interview camera integrity risk classification.

Used by live CandidateCameraTracker and local camera_detection_test.py so
warn policy cannot drift between environments.
"""

from __future__ import annotations

from typing import Optional

import config
from face_analysis import FrameAnalysisResult, GazeDirection, SpeakingState


def significant_extra_faces(
    result: FrameAnalysisResult,
    *,
    min_area_ratio: Optional[float] = None,
) -> bool:
    """True if a second face is large enough vs the primary (not a tiny poster)."""
    if len(result.faces) < 2:
        return False
    if not config.CAMERA_WARN_ON_MULTI_FACE:
        return False
    primary = result.faces[0]
    p_area = max(1.0, float(primary.bbox.width * primary.bbox.height))
    ratio = float(
        min_area_ratio
        if min_area_ratio is not None
        else config.CAMERA_WARN_MULTI_FACE_MIN_AREA_RATIO
    )
    for face in result.faces[1:]:
        area = float(face.bbox.width * face.bbox.height)
        if area / p_area >= ratio:
            return True
    return False


def classify_integrity_risk(result: FrameAnalysisResult) -> Optional[str]:
    """
    Priority: multi_face > no_face > looking_down > looking_side / looking_away.

    looking_up never warns (thinking / remembering).
    Interview-friendly: skip gaze warns while speaking; side needs head yaw;
    looking_down needs chin pitch (eyes/iris alone are not enough).
    """
    if significant_extra_faces(result):
        return "multi_face"
    if result.face_count <= 0:
        return "no_face" if config.CAMERA_WARN_ON_NO_FACE else None
    if not result.faces:
        return None

    primary = result.faces[0]
    gaze = primary.gaze
    speaking = primary.speaking == SpeakingState.SPEAKING
    ignore_while_speaking = bool(
        getattr(config, "CAMERA_WARN_IGNORE_AWAY_WHILE_SPEAKING", False)
    )

    if gaze == GazeDirection.LOOKING_UP:
        return None

    if config.CAMERA_WARN_ON_LOOKING_DOWN and gaze == GazeDirection.LOOKING_DOWN:
        if ignore_while_speaking and speaking:
            return None
        # Desk/notes: require real chin-down, not eye glance at the UI
        min_pitch = float(getattr(config, "CAMERA_WARN_DOWN_MIN_PITCH_DEG", 0.0) or 0.0)
        if min_pitch > 0 and abs(float(primary.head_pitch_deg)) < min_pitch:
            return None
        return "looking_down"

    if config.CAMERA_WARN_ON_LOOKING_AWAY and gaze == GazeDirection.LOOKING_AWAY:
        if ignore_while_speaking and speaking:
            return None
        return "looking_away"

    if config.CAMERA_WARN_INCLUDE_SIDE_LOOK and gaze in (
        GazeDirection.LOOKING_LEFT,
        GazeDirection.LOOKING_RIGHT,
    ):
        if ignore_while_speaking and speaking:
            return None
        min_yaw = float(getattr(config, "CAMERA_WARN_SIDE_MIN_YAW_DEG", 0.0) or 0.0)
        if min_yaw > 0 and abs(float(primary.head_yaw_deg)) < min_yaw:
            return None
        return "looking_side"

    return None
