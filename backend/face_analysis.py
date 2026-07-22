"""
Reusable face analysis for interview integrity checks.

Uses MediaPipe Face Landmarker (landmarks + blendshapes + transform matrix):
- Multi-face detection
- Eye-first gaze: center | left | right | down | up | away
- Modes: production (default) | interview (soft screen look) | strict (QA)
- Interview expressions: neutral | smiling | focused | distracted | confused
- Speaking: speaking | not_speaking (visual lip/jaw motion; not audio VAD)

Designed so local OpenCV tests and future Recall frame pipelines share one API.
Labels stay honest; integrity warn policy is configured separately.
"""

from __future__ import annotations

import logging
import math
import urllib.request
from collections import defaultdict, deque
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Deque, Dict, List, Mapping, Optional, Sequence, Tuple

import numpy as np

logger = logging.getLogger(__name__)

_MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/"
    "face_landmarker/face_landmarker/float16/1/face_landmarker.task"
)
_DEFAULT_MODEL_PATH = Path(__file__).resolve().parent / "models" / "face_landmarker.task"

# Face-mesh landmark indices (MediaPipe Face Mesh topology)
_LEFT_EYE_OUTER = 33
_LEFT_EYE_INNER = 133
_LEFT_EYE_TOP = 159
_LEFT_EYE_BOTTOM = 145
_RIGHT_EYE_OUTER = 263
_RIGHT_EYE_INNER = 362
_RIGHT_EYE_TOP = 386
_RIGHT_EYE_BOTTOM = 374
_LEFT_IRIS = 468
_RIGHT_IRIS = 473


class GazeDirection(str, Enum):
    LOOKING_CENTER = "looking_center"
    LOOKING_LEFT = "looking_left"
    LOOKING_RIGHT = "looking_right"
    LOOKING_DOWN = "looking_down"
    LOOKING_UP = "looking_up"
    LOOKING_AWAY = "looking_away"


class GazeMode(str, Enum):
    """
    production — mild eye-down = center; hard head-down = looking_down (+warn)
    interview  — softer eyes / higher head-down threshold
    strict     — sensitive eyes for QA (eye-down can label without hard head)
    """

    PRODUCTION = "production"
    INTERVIEW = "interview"
    STRICT = "strict"


class InterviewExpression(str, Enum):
    NEUTRAL = "neutral"
    SMILING = "smiling"
    FOCUSED = "focused"
    DISTRACTED = "distracted"
    CONFUSED = "confused"


class SpeakingState(str, Enum):
    SPEAKING = "speaking"
    NOT_SPEAKING = "not_speaking"


@dataclass(frozen=True)
class BoundingBox:
    x: int
    y: int
    width: int
    height: int

    @property
    def as_xyxy(self) -> Tuple[int, int, int, int]:
        return self.x, self.y, self.x + self.width, self.y + self.height


@dataclass(frozen=True)
class GazeMetrics:
    """Fused eye signals (0..1) used for gaze classification + debug HUD."""

    look_left: float = 0.0
    look_right: float = 0.0
    look_down: float = 0.0
    look_up: float = 0.0
    iris_x: Optional[float] = None  # 0=image-left, 1=image-right
    iris_y: Optional[float] = None  # 0=up, 1=down
    fused_left: float = 0.0
    fused_right: float = 0.0
    fused_down: float = 0.0
    fused_up: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "look_left": round(self.look_left, 3),
            "look_right": round(self.look_right, 3),
            "look_down": round(self.look_down, 3),
            "look_up": round(self.look_up, 3),
            "iris_x": None if self.iris_x is None else round(self.iris_x, 3),
            "iris_y": None if self.iris_y is None else round(self.iris_y, 3),
            "fused_left": round(self.fused_left, 3),
            "fused_right": round(self.fused_right, 3),
            "fused_down": round(self.fused_down, 3),
            "fused_up": round(self.fused_up, 3),
        }


@dataclass(frozen=True)
class FaceAnalysisResult:
    face_id: int
    bbox: BoundingBox
    gaze: GazeDirection
    expression: InterviewExpression
    speaking: SpeakingState
    confidence: float
    head_yaw_deg: float
    head_pitch_deg: float
    mouth_activity: float = 0.0
    blendshape_scores: Dict[str, float] = field(default_factory=dict)
    gaze_metrics: Optional[GazeMetrics] = None
    # Pixel coords of left/right iris centers for debug overlays
    iris_points_px: Tuple[Tuple[int, int], ...] = ()

    def to_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "face_id": self.face_id,
            "bbox": {
                "x": self.bbox.x,
                "y": self.bbox.y,
                "width": self.bbox.width,
                "height": self.bbox.height,
            },
            "gaze": self.gaze.value,
            "expression": self.expression.value,
            "speaking": self.speaking.value,
            "mouth_activity": round(self.mouth_activity, 3),
            "confidence": round(self.confidence, 3),
            "head_yaw_deg": round(self.head_yaw_deg, 1),
            "head_pitch_deg": round(self.head_pitch_deg, 1),
        }
        if self.gaze_metrics is not None:
            payload["gaze_metrics"] = self.gaze_metrics.to_dict()
        return payload


@dataclass(frozen=True)
class FrameAnalysisResult:
    face_count: int
    faces: List[FaceAnalysisResult]
    timestamp_ms: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "face_count": self.face_count,
            "timestamp_ms": self.timestamp_ms,
            "faces": [f.to_dict() for f in self.faces],
        }


def ensure_face_landmarker_model(model_path: Optional[Path] = None) -> Path:
    """Download the official Face Landmarker bundle if missing."""
    path = Path(model_path) if model_path else _DEFAULT_MODEL_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file() and path.stat().st_size > 0:
        return path
    logger.info("Downloading Face Landmarker model -> %s", path)
    urllib.request.urlretrieve(_MODEL_URL, path)
    return path


def _blendshape_map(categories: Sequence[Any]) -> Dict[str, float]:
    out: Dict[str, float] = {}
    for cat in categories or []:
        name = getattr(cat, "category_name", None) or getattr(cat, "display_name", None)
        score = float(getattr(cat, "score", 0.0) or 0.0)
        if name:
            out[str(name)] = score
    return out


def _get_score(scores: Mapping[str, float], *names: str) -> float:
    for name in names:
        if name in scores:
            return float(scores[name])
    return 0.0


def _avg(scores: Mapping[str, float], *names: str) -> float:
    vals = [_get_score(scores, n) for n in names]
    vals = [v for v in vals if v > 0] or [0.0]
    return sum(vals) / len(vals)


def _matrix_to_yaw_pitch(matrix: Sequence[Sequence[float]]) -> Tuple[float, float]:
    """
    Extract approximate head yaw/pitch (degrees) from a 4x4 transform matrix.
    Positive yaw ≈ subject turning left (from camera view: face rotates).
    """
    try:
        m = np.asarray(matrix, dtype=np.float64)
        if m.shape == (16,):
            m = m.reshape(4, 4)
        if m.shape[0] < 3 or m.shape[1] < 3:
            return 0.0, 0.0
        # Row-major rotation R
        r00, r10, r20 = float(m[0, 0]), float(m[1, 0]), float(m[2, 0])
        r21, r22 = float(m[2, 1]), float(m[2, 2])
        yaw = math.degrees(math.atan2(-r20, math.sqrt(r00 * r00 + r10 * r10)))
        pitch = math.degrees(math.atan2(r21, r22))
        return yaw, pitch
    except Exception:
        return 0.0, 0.0


@dataclass(frozen=True)
class _GazeProfile:
    eye_threshold: float
    eye_margin: float
    yaw_away_deg: float
    pitch_away_deg: float
    # Blendshape weight vs iris geometry (sum need not be 1; normalized in fuse)
    blend_weight: float
    iris_weight: float
    # Treat eye-only look-down as on-screen (not desk/phone)
    screen_down_as_center: bool
    screen_down_max: float
    # Iris Y must exceed this before "down" strength grows (higher = looser screen band)
    iris_down_start: float
    # Hard chin-down head pitch (deg) required to label looking_down
    head_down_deg: float
    smoother_window: int
    prefer_center_on_tie: bool


_GAZE_PROFILES: Dict[GazeMode, _GazeProfile] = {
    GazeMode.PRODUCTION: _GazeProfile(
        # Mild eye/screen look ignored; looking_down only on hard head-down
        eye_threshold=0.24,
        eye_margin=0.04,
        yaw_away_deg=38.0,
        pitch_away_deg=34.0,
        blend_weight=0.50,
        iris_weight=0.50,
        screen_down_as_center=True,
        screen_down_max=0.85,
        iris_down_start=0.60,
        head_down_deg=16.0,
        smoother_window=4,
        prefer_center_on_tie=True,
    ),
    GazeMode.INTERVIEW: _GazeProfile(
        eye_threshold=0.28,
        eye_margin=0.06,
        yaw_away_deg=35.0,
        pitch_away_deg=32.0,
        blend_weight=0.55,
        iris_weight=0.45,
        screen_down_as_center=True,
        screen_down_max=0.90,
        iris_down_start=0.62,
        head_down_deg=18.0,
        smoother_window=6,
        prefer_center_on_tie=True,
    ),
    GazeMode.STRICT: _GazeProfile(
        eye_threshold=0.22,
        eye_margin=0.04,
        yaw_away_deg=40.0,
        pitch_away_deg=36.0,
        blend_weight=0.45,
        iris_weight=0.55,
        screen_down_as_center=False,
        screen_down_max=0.50,
        iris_down_start=0.55,
        head_down_deg=12.0,
        smoother_window=3,
        prefer_center_on_tie=False,
    ),
}


def parse_gaze_mode(value: Optional[str]) -> GazeMode:
    raw = (value or GazeMode.PRODUCTION.value).strip().lower()
    for mode in GazeMode:
        if mode.value == raw:
            return mode
    logger.warning("Unknown CAMERA_GAZE_MODE=%r — using production", value)
    return GazeMode.PRODUCTION


def _project_ratio(
    landmarks: Sequence[Any],
    a_idx: int,
    b_idx: int,
    p_idx: int,
) -> float:
    """Project point p onto segment a→b; return clamped 0..1."""
    ax, ay = float(landmarks[a_idx].x), float(landmarks[a_idx].y)
    bx, by = float(landmarks[b_idx].x), float(landmarks[b_idx].y)
    px, py = float(landmarks[p_idx].x), float(landmarks[p_idx].y)
    vx, vy = bx - ax, by - ay
    denom = vx * vx + vy * vy
    if denom < 1e-9:
        return 0.5
    t = ((px - ax) * vx + (py - ay) * vy) / denom
    return float(min(1.0, max(0.0, t)))


def _iris_xy_ratios(landmarks: Sequence[Any]) -> Tuple[Optional[float], Optional[float]]:
    """
    Iris position averaged across both eyes.
    iris_x: 0 ≈ looking image-left, 1 ≈ image-right
    iris_y: 0 ≈ looking up, 1 ≈ looking down
    """
    try:
        if len(landmarks) <= _RIGHT_IRIS:
            return None, None

        left_x = _project_ratio(landmarks, _LEFT_EYE_OUTER, _LEFT_EYE_INNER, _LEFT_IRIS)
        right_x = _project_ratio(landmarks, _RIGHT_EYE_OUTER, _RIGHT_EYE_INNER, _RIGHT_IRIS)
        # Right eye outer is image-right; invert so both share left=0 convention
        iris_x = (left_x + (1.0 - right_x)) / 2.0

        left_y = _project_ratio(landmarks, _LEFT_EYE_TOP, _LEFT_EYE_BOTTOM, _LEFT_IRIS)
        right_y = _project_ratio(landmarks, _RIGHT_EYE_TOP, _RIGHT_EYE_BOTTOM, _RIGHT_IRIS)
        iris_y = (left_y + right_y) / 2.0
        return iris_x, iris_y
    except Exception:
        return None, None


def _iris_points_px(
    landmarks: Sequence[Any],
    frame_w: int,
    frame_h: int,
) -> Tuple[Tuple[int, int], ...]:
    try:
        if len(landmarks) <= _RIGHT_IRIS:
            return ()
        pts = []
        for idx in (_LEFT_IRIS, _RIGHT_IRIS):
            lm = landmarks[idx]
            pts.append(
                (
                    int(max(0, min(frame_w - 1, float(lm.x) * frame_w))),
                    int(max(0, min(frame_h - 1, float(lm.y) * frame_h))),
                )
            )
        return tuple(pts)
    except Exception:
        return ()


def _iris_dir_strengths(
    iris_x: Optional[float],
    iris_y: Optional[float],
    *,
    iris_down_start: float = 0.55,
) -> Tuple[float, float, float, float]:
    """Map iris position to left/right/down/up strengths in 0..1."""
    left = right = down = up = 0.0
    if iris_x is not None:
        # Narrow center dead-zone; left side slightly more sensitive (glasses
        # + mirrored webcam often under-report look-left).
        if iris_x <= 0.48:
            left = (0.48 - iris_x) / 0.48
        if iris_x >= 0.52:
            right = (iris_x - 0.52) / 0.48
    if iris_y is not None:
        # Higher iris_down_start = more screen look ignored before "down" grows
        down_start = min(0.85, max(0.45, float(iris_down_start)))
        span = max(0.15, 1.0 - down_start)
        if iris_y >= down_start:
            down = (iris_y - down_start) / span
        if iris_y <= 0.45:
            up = (0.45 - iris_y) / 0.45
    return (
        float(min(1.0, max(0.0, left))),
        float(min(1.0, max(0.0, right))),
        float(min(1.0, max(0.0, down))),
        float(min(1.0, max(0.0, up))),
    )


def _fuse_dir(blend: float, iris: float, *, blend_w: float, iris_w: float) -> float:
    """
    Fuse blendshape + iris; take the stronger signal so one weak channel
    (common for look-left with glasses) does not kill the direction.
    """
    weighted = blend_w * blend + iris_w * iris
    peak = max(blend, iris)
    # Prefer peak when either channel is clearly active
    return float(min(1.0, max(weighted, 0.85 * peak + 0.15 * weighted)))


def compute_gaze_metrics(
    blendshapes: Mapping[str, float],
    landmarks: Sequence[Any],
    *,
    blend_weight: float = 0.55,
    iris_weight: float = 0.45,
    iris_down_start: float = 0.55,
) -> GazeMetrics:
    # Use max of paired blendshapes so one eye still drives the direction
    look_left = max(
        _get_score(blendshapes, "eyeLookOutLeft"),
        _get_score(blendshapes, "eyeLookInRight"),
        _avg(blendshapes, "eyeLookOutLeft", "eyeLookInRight"),
    )
    look_right = max(
        _get_score(blendshapes, "eyeLookOutRight"),
        _get_score(blendshapes, "eyeLookInLeft"),
        _avg(blendshapes, "eyeLookOutRight", "eyeLookInLeft"),
    )
    look_down = max(
        _get_score(blendshapes, "eyeLookDownLeft"),
        _get_score(blendshapes, "eyeLookDownRight"),
        _avg(blendshapes, "eyeLookDownLeft", "eyeLookDownRight"),
    )
    look_up = max(
        _get_score(blendshapes, "eyeLookUpLeft"),
        _get_score(blendshapes, "eyeLookUpRight"),
        _avg(blendshapes, "eyeLookUpLeft", "eyeLookUpRight"),
    )
    iris_x, iris_y = _iris_xy_ratios(landmarks)
    i_left, i_right, i_down, i_up = _iris_dir_strengths(
        iris_x,
        iris_y,
        iris_down_start=iris_down_start,
    )

    bw = max(0.0, float(blend_weight))
    iw = max(0.0, float(iris_weight))
    denom = bw + iw if (bw + iw) > 1e-6 else 1.0
    bw, iw = bw / denom, iw / denom

    fused_left = _fuse_dir(look_left, i_left, blend_w=bw, iris_w=iw)
    # Small left boost: mirrored preview + glasses often under-fire look-left
    fused_left = min(1.0, fused_left * 1.12)

    return GazeMetrics(
        look_left=look_left,
        look_right=look_right,
        look_down=look_down,
        look_up=look_up,
        iris_x=iris_x,
        iris_y=iris_y,
        fused_left=fused_left,
        fused_right=_fuse_dir(look_right, i_right, blend_w=bw, iris_w=iw),
        fused_down=_fuse_dir(look_down, i_down, blend_w=bw, iris_w=iw),
        fused_up=_fuse_dir(look_up, i_up, blend_w=bw, iris_w=iw),
    )


def classify_gaze(
    blendshapes: Mapping[str, float],
    *,
    head_yaw_deg: float,
    head_pitch_deg: float,
    iris_ratio: Optional[float] = None,
    landmarks: Optional[Sequence[Any]] = None,
    metrics: Optional[GazeMetrics] = None,
    mode: GazeMode = GazeMode.PRODUCTION,
) -> GazeDirection:
    """
    Eye-first gaze classification.

    Head pose only forces looking_away on strong turns. In production/interview,
    mild look-down (screen under webcam) maps to looking_center. Clear left/right
    and extreme down still surface. Warn policy is configured separately.
    """
    profile = _GAZE_PROFILES[mode]
    if metrics is None:
        if landmarks is not None:
            metrics = compute_gaze_metrics(
                blendshapes,
                landmarks,
                blend_weight=profile.blend_weight,
                iris_weight=profile.iris_weight,
                iris_down_start=profile.iris_down_start,
            )
        else:
            # Legacy path: blendshapes + optional horizontal iris only
            look_left = _avg(blendshapes, "eyeLookOutLeft", "eyeLookInRight")
            look_right = _avg(blendshapes, "eyeLookOutRight", "eyeLookInLeft")
            look_down = _avg(blendshapes, "eyeLookDownLeft", "eyeLookDownRight")
            look_up = _avg(blendshapes, "eyeLookUpLeft", "eyeLookUpRight")
            i_left, i_right, i_down, i_up = _iris_dir_strengths(
                iris_ratio,
                None,
                iris_down_start=profile.iris_down_start,
            )
            bw = profile.blend_weight
            iw = profile.iris_weight
            denom = bw + iw
            bw, iw = bw / denom, iw / denom
            metrics = GazeMetrics(
                look_left=look_left,
                look_right=look_right,
                look_down=look_down,
                look_up=look_up,
                iris_x=iris_ratio,
                iris_y=None,
                fused_left=bw * look_left + iw * i_left,
                fused_right=bw * look_right + iw * i_right,
                fused_down=bw * look_down + iw * i_down,
                fused_up=bw * look_up + iw * i_up,
            )

    yaw_abs = abs(head_yaw_deg)
    pitch_abs = abs(head_pitch_deg)

    # Strong lateral / extreme pitch → away
    if yaw_abs >= profile.yaw_away_deg or pitch_abs >= profile.pitch_away_deg:
        return GazeDirection.LOOKING_AWAY

    # Hard head nod down (chin toward chest) — integrity signal, not screen glance
    hard_head_down = (
        pitch_abs >= profile.head_down_deg
        and metrics.fused_down >= metrics.fused_up
        and metrics.fused_down >= 0.18
    )
    if hard_head_down:
        return GazeDirection.LOOKING_DOWN

    candidates: List[Tuple[GazeDirection, float]] = [
        (GazeDirection.LOOKING_LEFT, metrics.fused_left),
        (GazeDirection.LOOKING_RIGHT, metrics.fused_right),
        (GazeDirection.LOOKING_DOWN, metrics.fused_down),
        (GazeDirection.LOOKING_UP, metrics.fused_up),
    ]
    candidates.sort(key=lambda item: item[1], reverse=True)
    best_dir, best_score = candidates[0]
    second_score = candidates[1][1] if len(candidates) > 1 else 0.0

    if best_score < profile.eye_threshold or (best_score - second_score) < profile.eye_margin:
        return GazeDirection.LOOKING_CENTER

    # Eye-only look-down = watching the screen under the webcam → center
    if profile.screen_down_as_center and best_dir == GazeDirection.LOOKING_DOWN:
        for direction, score in candidates[1:]:
            if (
                direction
                in (GazeDirection.LOOKING_LEFT, GazeDirection.LOOKING_RIGHT)
                and score >= profile.eye_threshold
            ):
                return direction
        # Without hard head pitch, ignore mild/strong eye-down as screen engagement
        if pitch_abs < profile.head_down_deg:
            return GazeDirection.LOOKING_CENTER
        if best_score < profile.screen_down_max:
            return GazeDirection.LOOKING_CENTER

    return best_dir


class GazeSmoother:
    """Majority-vote gaze over a short window to ignore blinks / micro-moves."""

    def __init__(self, window: int = 5, *, prefer_center_on_tie: bool = False) -> None:
        self._window = max(1, int(window))
        self._prefer_center = prefer_center_on_tie
        self._histories: Dict[int, Deque[GazeDirection]] = defaultdict(
            lambda: deque(maxlen=self._window)
        )

    def update(self, face_id: int, gaze: GazeDirection) -> GazeDirection:
        hist = self._histories[face_id]
        hist.append(gaze)
        counts: Dict[GazeDirection, int] = {}
        for g in hist:
            counts[g] = counts.get(g, 0) + 1
        best = max(
            counts.items(),
            key=lambda item: (
                item[1],
                1
                if (self._prefer_center and item[0] == GazeDirection.LOOKING_CENTER)
                else 0,
            ),
        )[0]
        return best

    def reset(self) -> None:
        self._histories.clear()


def mouth_activity_score(blendshapes: Mapping[str, float]) -> float:
    """0..1 proxy for lip/jaw motion energy (visual speaking cue)."""
    jaw = _get_score(blendshapes, "jawOpen")
    funnel = _get_score(blendshapes, "mouthFunnel")
    pout = _get_score(blendshapes, "mouthPucker")
    stretch = _avg(blendshapes, "mouthStretchLeft", "mouthStretchRight")
    shrug = _avg(blendshapes, "mouthShrugLower", "mouthShrugUpper")
    close = _get_score(blendshapes, "mouthClose")
    # Open / articulating mouth increases score; tight closed mouth reduces it
    raw = (
        0.50 * jaw
        + 0.18 * funnel
        + 0.12 * stretch
        + 0.10 * pout
        + 0.10 * shrug
        - 0.15 * close
    )
    return float(min(1.0, max(0.0, raw)))


class SpeakingTracker:
    """
    Temporal speaking detector from mouth activity.

    Single-frame jaw open is not enough (yawns/smiles). We require
    recent variation across frames, with hysteresis to reduce flicker.
    """

    def __init__(
        self,
        *,
        window: int = 14,
        motion_threshold: float = 0.055,
        open_threshold: float = 0.10,
        speak_on_hits: int = 3,
        speak_off_misses: int = 5,
    ) -> None:
        self._window = max(4, int(window))
        self._motion_threshold = float(motion_threshold)
        self._open_threshold = float(open_threshold)
        self._speak_on_hits = max(1, int(speak_on_hits))
        self._speak_off_misses = max(1, int(speak_off_misses))
        self._histories: Dict[int, Deque[float]] = defaultdict(
            lambda: deque(maxlen=self._window)
        )
        self._state: Dict[int, SpeakingState] = {}
        self._hit_streak: Dict[int, int] = defaultdict(int)
        self._miss_streak: Dict[int, int] = defaultdict(int)

    def update(self, face_id: int, activity: float) -> SpeakingState:
        hist = self._histories[face_id]
        hist.append(float(activity))
        values = list(hist)
        if len(values) < 3:
            state = SpeakingState.NOT_SPEAKING
            self._state[face_id] = state
            return state

        span = max(values) - min(values)
        mean_act = sum(values) / len(values)
        # Approximate std without numpy dependency here
        var = sum((v - mean_act) ** 2 for v in values) / len(values)
        std = math.sqrt(var)

        active_now = (
            (span >= self._motion_threshold or std >= self._motion_threshold * 0.65)
            and mean_act >= self._open_threshold * 0.45
        ) or (activity >= self._open_threshold * 1.6 and span >= self._motion_threshold * 0.5)

        prev = self._state.get(face_id, SpeakingState.NOT_SPEAKING)
        if active_now:
            self._hit_streak[face_id] += 1
            self._miss_streak[face_id] = 0
        else:
            self._miss_streak[face_id] += 1
            self._hit_streak[face_id] = 0

        if prev == SpeakingState.NOT_SPEAKING:
            state = (
                SpeakingState.SPEAKING
                if self._hit_streak[face_id] >= self._speak_on_hits
                else SpeakingState.NOT_SPEAKING
            )
        else:
            state = (
                SpeakingState.NOT_SPEAKING
                if self._miss_streak[face_id] >= self._speak_off_misses
                else SpeakingState.SPEAKING
            )
        self._state[face_id] = state
        return state

    def reset(self) -> None:
        self._histories.clear()
        self._state.clear()
        self._hit_streak.clear()
        self._miss_streak.clear()


def classify_expression(
    blendshapes: Mapping[str, float],
    gaze: GazeDirection,
) -> InterviewExpression:
    """Interview-oriented expression labels from ARKit-style blendshapes."""
    smile = _avg(blendshapes, "mouthSmileLeft", "mouthSmileRight")
    brow_up = _get_score(blendshapes, "browInnerUp")
    brow_down = _avg(blendshapes, "browDownLeft", "browDownRight")
    jaw_open = _get_score(blendshapes, "jawOpen")
    mouth_funnel = _get_score(blendshapes, "mouthFunnel")

    if smile >= 0.35:
        return InterviewExpression.SMILING

    if brow_up >= 0.40 and (jaw_open >= 0.12 or mouth_funnel >= 0.15 or brow_down < 0.25):
        return InterviewExpression.CONFUSED

    # Strong off-screen / sustained side or up can read as distracted
    if gaze == GazeDirection.LOOKING_AWAY and smile < 0.25:
        return InterviewExpression.DISTRACTED
    if gaze in (
        GazeDirection.LOOKING_LEFT,
        GazeDirection.LOOKING_RIGHT,
        GazeDirection.LOOKING_UP,
    ) and smile < 0.2:
        return InterviewExpression.DISTRACTED

    # looking_down is often reading the interview UI — keep focused/neutral
    if gaze in (GazeDirection.LOOKING_CENTER, GazeDirection.LOOKING_DOWN):
        if smile < 0.25 and brow_up < 0.35:
            return InterviewExpression.FOCUSED

    return InterviewExpression.NEUTRAL


def _landmarks_bbox(
    landmarks: Sequence[Any],
    frame_w: int,
    frame_h: int,
) -> BoundingBox:
    xs = [float(lm.x) * frame_w for lm in landmarks]
    ys = [float(lm.y) * frame_h for lm in landmarks]
    x0, x1 = int(max(0, min(xs))), int(min(frame_w - 1, max(xs)))
    y0, y1 = int(max(0, min(ys))), int(min(frame_h - 1, max(ys)))
    # Pad slightly for readability
    pad_x = int(0.04 * (x1 - x0 + 1))
    pad_y = int(0.06 * (y1 - y0 + 1))
    x0 = max(0, x0 - pad_x)
    y0 = max(0, y0 - pad_y)
    x1 = min(frame_w - 1, x1 + pad_x)
    y1 = min(frame_h - 1, y1 + pad_y)
    return BoundingBox(x=x0, y=y0, width=max(1, x1 - x0), height=max(1, y1 - y0))


class FaceAnalyzer:
    """
    Thread-unsafe MediaPipe Face Landmarker wrapper.

    Create one instance per worker/process. Call close() when done.
    """

    def __init__(
        self,
        *,
        model_path: Optional[Path] = None,
        max_faces: int = 5,
        min_face_detection_confidence: float = 0.5,
        min_face_presence_confidence: float = 0.5,
        min_tracking_confidence: float = 0.5,
        gaze_mode: GazeMode | str = GazeMode.PRODUCTION,
    ) -> None:
        from mediapipe.tasks import python as mp_python
        from mediapipe.tasks.python import vision

        self._mp = __import__("mediapipe")
        self._vision = vision
        self._max_faces = max(1, int(max_faces))
        self._gaze_mode = (
            gaze_mode
            if isinstance(gaze_mode, GazeMode)
            else parse_gaze_mode(str(gaze_mode))
        )
        profile = _GAZE_PROFILES[self._gaze_mode]
        resolved = ensure_face_landmarker_model(model_path)

        options = vision.FaceLandmarkerOptions(
            base_options=mp_python.BaseOptions(model_asset_path=str(resolved)),
            running_mode=vision.RunningMode.VIDEO,
            num_faces=self._max_faces,
            min_face_detection_confidence=min_face_detection_confidence,
            min_face_presence_confidence=min_face_presence_confidence,
            min_tracking_confidence=min_tracking_confidence,
            output_face_blendshapes=True,
            output_facial_transformation_matrixes=True,
        )
        self._landmarker = vision.FaceLandmarker.create_from_options(options)
        self._last_timestamp_ms = -1
        self._speaking_tracker = SpeakingTracker()
        self._gaze_smoother = GazeSmoother(
            window=profile.smoother_window,
            prefer_center_on_tie=profile.prefer_center_on_tie,
        )
        logger.info(
            "FaceAnalyzer ready model=%s max_faces=%d gaze_mode=%s",
            resolved,
            self._max_faces,
            self._gaze_mode.value,
        )

    @property
    def gaze_mode(self) -> GazeMode:
        return self._gaze_mode

    def close(self) -> None:
        landmarker = getattr(self, "_landmarker", None)
        if landmarker is not None:
            landmarker.close()
            self._landmarker = None
        self._speaking_tracker.reset()
        self._gaze_smoother.reset()

    def __enter__(self) -> "FaceAnalyzer":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def analyze_bgr(
        self,
        frame_bgr: np.ndarray,
        *,
        timestamp_ms: Optional[int] = None,
    ) -> FrameAnalysisResult:
        """Analyze an OpenCV BGR frame (H×W×3 uint8)."""
        if frame_bgr is None or frame_bgr.size == 0:
            return FrameAnalysisResult(face_count=0, faces=[], timestamp_ms=0)
        rgb = frame_bgr[:, :, ::-1].copy()
        return self.analyze_rgb(rgb, timestamp_ms=timestamp_ms)

    def analyze_rgb(
        self,
        frame_rgb: np.ndarray,
        *,
        timestamp_ms: Optional[int] = None,
    ) -> FrameAnalysisResult:
        """Analyze an RGB frame (reusable for Recall PNG → RGB later)."""
        if self._landmarker is None:
            raise RuntimeError("FaceAnalyzer is closed")
        if frame_rgb is None or frame_rgb.size == 0:
            return FrameAnalysisResult(face_count=0, faces=[], timestamp_ms=0)
        if frame_rgb.dtype != np.uint8:
            frame_rgb = frame_rgb.astype(np.uint8)
        if not frame_rgb.flags["C_CONTIGUOUS"]:
            frame_rgb = np.ascontiguousarray(frame_rgb)

        ts = int(timestamp_ms) if timestamp_ms is not None else self._next_timestamp_ms()
        if ts <= self._last_timestamp_ms:
            ts = self._last_timestamp_ms + 1
        self._last_timestamp_ms = ts

        mp_image = self._mp.Image(
            image_format=self._mp.ImageFormat.SRGB,
            data=frame_rgb,
        )
        result = self._landmarker.detect_for_video(mp_image, ts)
        h, w = frame_rgb.shape[:2]
        faces = self._parse_result(result, frame_w=w, frame_h=h)
        return FrameAnalysisResult(face_count=len(faces), faces=faces, timestamp_ms=ts)

    def _next_timestamp_ms(self) -> int:
        if self._last_timestamp_ms < 0:
            return 0
        return self._last_timestamp_ms + 33  # ~30 FPS clock

    def _parse_result(
        self,
        result: Any,
        *,
        frame_w: int,
        frame_h: int,
    ) -> List[FaceAnalysisResult]:
        faces: List[FaceAnalysisResult] = []
        landmarks_list = getattr(result, "face_landmarks", None) or []
        blendshapes_list = getattr(result, "face_blendshapes", None) or []
        matrices = getattr(result, "facial_transformation_matrixes", None) or []

        for idx, landmarks in enumerate(landmarks_list):
            scores = _blendshape_map(
                blendshapes_list[idx] if idx < len(blendshapes_list) else []
            )
            matrix = matrices[idx] if idx < len(matrices) else None
            yaw, pitch = (0.0, 0.0)
            if matrix is not None:
                yaw, pitch = _matrix_to_yaw_pitch(matrix)

            profile = _GAZE_PROFILES[self._gaze_mode]
            metrics = compute_gaze_metrics(
                scores,
                landmarks,
                blend_weight=profile.blend_weight,
                iris_weight=profile.iris_weight,
                iris_down_start=profile.iris_down_start,
            )
            raw_gaze = classify_gaze(
                scores,
                head_yaw_deg=yaw,
                head_pitch_deg=pitch,
                metrics=metrics,
                mode=self._gaze_mode,
            )
            activity = mouth_activity_score(scores)
            bbox = _landmarks_bbox(landmarks, frame_w, frame_h)
            iris_pts = _iris_points_px(landmarks, frame_w, frame_h)

            # Presence confidence: favor larger, more frontal faces
            area_norm = min(
                1.0,
                (bbox.width * bbox.height) / max(1.0, frame_w * frame_h * 0.12),
            )
            confidence = min(
                1.0,
                0.45
                + 0.20 * float(bool(scores))
                + 0.20 * max(0.0, 1.0 - abs(yaw) / 55.0)
                + 0.15 * area_norm,
            )

            faces.append(
                FaceAnalysisResult(
                    face_id=idx + 1,
                    bbox=bbox,
                    gaze=raw_gaze,
                    expression=InterviewExpression.NEUTRAL,
                    speaking=SpeakingState.NOT_SPEAKING,
                    confidence=confidence,
                    head_yaw_deg=yaw,
                    head_pitch_deg=pitch,
                    mouth_activity=activity,
                    blendshape_scores=scores,
                    gaze_metrics=metrics,
                    iris_points_px=iris_pts,
                )
            )

        # Primary candidate = largest face (closest / most relevant)
        faces.sort(key=lambda f: f.bbox.width * f.bbox.height, reverse=True)
        finalized: List[FaceAnalysisResult] = []
        for i, face in enumerate(faces):
            face_id = i + 1
            gaze = self._gaze_smoother.update(face_id, face.gaze)
            expression = classify_expression(face.blendshape_scores, gaze)
            speaking = self._speaking_tracker.update(face_id, face.mouth_activity)
            finalized.append(
                FaceAnalysisResult(
                    face_id=face_id,
                    bbox=face.bbox,
                    gaze=gaze,
                    expression=expression,
                    speaking=speaking,
                    confidence=face.confidence,
                    head_yaw_deg=face.head_yaw_deg,
                    head_pitch_deg=face.head_pitch_deg,
                    mouth_activity=face.mouth_activity,
                    blendshape_scores=face.blendshape_scores,
                    gaze_metrics=face.gaze_metrics,
                    iris_points_px=face.iris_points_px,
                )
            )
        return finalized
