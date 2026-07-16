"""
Local camera test for interview face / gaze / expression analysis.

Warns with Edge-TTS when risk lasts longer than CAMERA_WARN_AFTER_SEC (env).

Usage (from backend/):
  .\\venv\\Scripts\\python.exe camera_detection_test.py
  .\\venv\\Scripts\\python.exe camera_detection_test.py --gaze-mode production
  .\\venv\\Scripts\\python.exe camera_detection_test.py --gaze-mode strict --no-tts

Controls:
  q / ESC — quit
  s       — print current frame JSON to terminal
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# Allow `python backend/camera_detection_test.py` from repo root
_BACKEND_DIR = Path(__file__).resolve().parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "hide")

import cv2
import edge_tts
import numpy as np

import config as app_config
from face_analysis import (
    FaceAnalysisResult,
    FaceAnalyzer,
    FrameAnalysisResult,
    GazeDirection,
    GazeMode,
    InterviewExpression,
    SpeakingState,
    parse_gaze_mode,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("camera_detection_test")

_WINDOW = "Interview Camera Detection (q=quit, s=snapshot log)"

_GAZE_COLOR = {
    GazeDirection.LOOKING_CENTER: (60, 180, 75),
    GazeDirection.LOOKING_LEFT: (255, 180, 0),
    GazeDirection.LOOKING_RIGHT: (255, 180, 0),
    GazeDirection.LOOKING_DOWN: (255, 200, 80),
    GazeDirection.LOOKING_UP: (255, 200, 80),
    GazeDirection.LOOKING_AWAY: (0, 80, 255),
}

_EXPR_COLOR = {
    InterviewExpression.FOCUSED: (60, 180, 75),
    InterviewExpression.SMILING: (0, 220, 255),
    InterviewExpression.NEUTRAL: (220, 220, 220),
    InterviewExpression.DISTRACTED: (0, 140, 255),
    InterviewExpression.CONFUSED: (180, 100, 255),
}

_WARN_MESSAGES = {
    "no_face": "Please stay in front of the camera so I can see your face.",
    "looking_away": "Please face the camera and keep looking at the screen.",
    "looking_down": "Please lift your head and look at the interview screen.",
    "multi_face": "Please make sure only you are visible on camera.",
}


class EdgeTtsSpeaker:
    """Non-blocking Edge-TTS playback for local camera warnings."""

    def __init__(self, *, voice: str, rate: str) -> None:
        self._voice = voice
        self._rate = rate
        self._lock = threading.Lock()
        self._busy = False
        import pygame

        pygame.mixer.init()
        self._pygame = pygame

    @property
    def busy(self) -> bool:
        return self._busy

    def speak(self, text: str) -> None:
        text = (text or "").strip()
        if not text:
            return
        with self._lock:
            if self._busy:
                logger.debug("TTS busy — skip warning: %s", text[:60])
                return
            self._busy = True

        def _worker() -> None:
            path: Optional[str] = None
            try:
                tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
                path = tmp.name
                tmp.close()
                communicate = edge_tts.Communicate(text, self._voice, rate=self._rate)
                asyncio.run(communicate.save(path))
                self._pygame.mixer.music.load(path)
                self._pygame.mixer.music.play()
                while self._pygame.mixer.music.get_busy():
                    time.sleep(0.05)
                logger.info("TTS warn spoken: %s", text)
            except Exception as ex:
                logger.warning("Edge-TTS warn failed: %s", ex)
            finally:
                if path:
                    try:
                        os.unlink(path)
                    except OSError:
                        pass
                with self._lock:
                    self._busy = False

        threading.Thread(target=_worker, name="camera-warn-tts", daemon=True).start()

    def close(self) -> None:
        try:
            self._pygame.mixer.music.stop()
            self._pygame.mixer.quit()
        except Exception:
            pass


@dataclass
class RiskState:
    kind: Optional[str] = None
    started_at: float = 0.0
    last_warn_at: float = 0.0
    active_seconds: float = 0.0


class IntegrityWarnMonitor:
    """Accumulate sustained risk, then speak Edge-TTS after CAMERA_WARN_AFTER_SEC."""

    def __init__(self, speaker: Optional[EdgeTtsSpeaker]) -> None:
        self._speaker = speaker
        self._warn_after = float(app_config.CAMERA_WARN_AFTER_SEC)
        self._warn_after_away = float(
            getattr(app_config, "CAMERA_WARN_AFTER_AWAY_SEC", self._warn_after * 1.75)
        )
        self._cooldown = float(app_config.CAMERA_WARN_COOLDOWN_SEC)
        self._include_side = bool(app_config.CAMERA_WARN_INCLUDE_SIDE_LOOK)
        self._on_no_face = bool(app_config.CAMERA_WARN_ON_NO_FACE)
        self._on_multi = bool(app_config.CAMERA_WARN_ON_MULTI_FACE)
        self._on_away = bool(app_config.CAMERA_WARN_ON_LOOKING_AWAY)
        self._on_down = bool(getattr(app_config, "CAMERA_WARN_ON_LOOKING_DOWN", False))
        self._ignore_away_while_speaking = bool(
            getattr(app_config, "CAMERA_WARN_IGNORE_AWAY_WHILE_SPEAKING", True)
        )
        self._multi_min_area_ratio = float(
            getattr(app_config, "CAMERA_WARN_MULTI_FACE_MIN_AREA_RATIO", 0.18)
        )
        self._hold_frames = max(1, int(getattr(app_config, "CAMERA_WARN_HOLD_FRAMES", 8)))
        self._enabled = bool(app_config.CAMERA_WARN_TTS_ENABLED) and speaker is not None
        self._risk = RiskState()
        self._pending_kind: Optional[str] = None
        self._pending_hits = 0
        logger.info(
            "Warn monitor: enabled=%s after=%.1fs away_after=%.1fs cooldown=%.1fs "
            "side_look=%s hold_frames=%d",
            self._enabled,
            self._warn_after,
            self._warn_after_away,
            self._cooldown,
            self._include_side,
            self._hold_frames,
        )

    def _significant_extra_faces(self, result: FrameAnalysisResult) -> bool:
        """True only if a second face is large enough vs the primary (not a tiny poster)."""
        if len(result.faces) < 2:
            return False
        primary = result.faces[0]
        p_area = max(1.0, float(primary.bbox.width * primary.bbox.height))
        for face in result.faces[1:]:
            area = float(face.bbox.width * face.bbox.height)
            if area / p_area >= self._multi_min_area_ratio:
                return True
        return False

    def _classify(self, result: FrameAnalysisResult) -> Optional[str]:
        if result.face_count <= 0:
            return "no_face" if self._on_no_face else None
        if self._on_multi and self._significant_extra_faces(result):
            return "multi_face"
        if not self._on_away:
            return None
        primary = result.faces[0]
        # Answering aloud often looks at the screen / gestures — don't flag away
        if (
            self._ignore_away_while_speaking
            and primary.speaking == SpeakingState.SPEAKING
        ):
            return None
        gaze = primary.gaze
        if gaze == GazeDirection.LOOKING_AWAY:
            return "looking_away"
        if self._on_down and gaze == GazeDirection.LOOKING_DOWN:
            return "looking_down"
        if self._include_side and gaze in (
            GazeDirection.LOOKING_LEFT,
            GazeDirection.LOOKING_RIGHT,
            GazeDirection.LOOKING_UP,
        ):
            return "looking_away"
        return None

    def _threshold_for(self, kind: str) -> float:
        if kind in ("looking_away", "looking_down"):
            return self._warn_after_away
        return self._warn_after

    def update(self, result: FrameAnalysisResult, now: float) -> RiskState:
        raw = self._classify(result)
        if raw is None:
            self._pending_kind = None
            self._pending_hits = 0
            self._risk = RiskState(last_warn_at=self._risk.last_warn_at)
            return self._risk

        if raw == self._pending_kind:
            self._pending_hits += 1
        else:
            self._pending_kind = raw
            self._pending_hits = 1

        # Debounce: require N consecutive risk frames before the timer starts
        if self._pending_hits < self._hold_frames:
            self._risk = RiskState(last_warn_at=self._risk.last_warn_at)
            return self._risk

        kind = raw
        if self._risk.kind != kind or self._risk.started_at <= 0:
            self._risk.kind = kind
            self._risk.started_at = now

        self._risk.active_seconds = max(0.0, now - self._risk.started_at)
        threshold = self._threshold_for(kind)

        if (
            self._enabled
            and self._risk.active_seconds >= threshold
            and (now - self._risk.last_warn_at) >= self._cooldown
            and self._speaker is not None
            and not self._speaker.busy
        ):
            message = _WARN_MESSAGES.get(kind, _WARN_MESSAGES["looking_away"])
            logger.info(
                "Risk warn kind=%s held=%.1fs threshold=%.1fs",
                kind,
                self._risk.active_seconds,
                threshold,
            )
            self._speaker.speak(message)
            self._risk.last_warn_at = now

        return self._risk


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Local OpenCV + MediaPipe interview face analysis test",
    )
    parser.add_argument("--camera", type=int, default=0, help="Camera device index")
    parser.add_argument("--max-faces", type=int, default=5, help="Max faces per frame")
    parser.add_argument("--width", type=int, default=1280, help="Capture width")
    parser.add_argument("--height", type=int, default=720, help="Capture height")
    parser.add_argument("--model", type=Path, default=None, help="face_landmarker.task path")
    parser.add_argument(
        "--warn-after",
        type=float,
        default=None,
        help="Override CAMERA_WARN_AFTER_SEC for this run",
    )
    parser.add_argument(
        "--no-tts",
        action="store_true",
        help="Disable Edge-TTS warnings for this run",
    )
    parser.add_argument(
        "--gaze-mode",
        choices=[m.value for m in GazeMode],
        default=None,
        help="Override CAMERA_GAZE_MODE (production|interview|strict)",
    )
    parser.add_argument(
        "--no-gaze-debug",
        action="store_true",
        help="Hide iris dots and fused eye score HUD",
    )
    return parser.parse_args(argv)


def _draw_face(
    frame: np.ndarray,
    face: FaceAnalysisResult,
    *,
    debug: bool = True,
) -> None:
    x1, y1, x2, y2 = face.bbox.as_xyxy
    color = _GAZE_COLOR.get(face.gaze, (200, 200, 200))
    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)

    if debug:
        for px, py in face.iris_points_px:
            cv2.circle(frame, (px, py), 3, (0, 255, 255), -1, cv2.LINE_AA)
            cv2.circle(frame, (px, py), 6, color, 1, cv2.LINE_AA)

    speaking_label = (
        "SPEAKING" if face.speaking == SpeakingState.SPEAKING else "not speaking"
    )
    speak_color = (0, 220, 100) if face.speaking == SpeakingState.SPEAKING else (160, 160, 160)

    label_1 = f"Face {face.face_id}: {face.gaze.value}"
    label_2 = f"{face.expression.value}  conf={face.confidence:.2f}"
    label_3 = f"{speaking_label}  mouth={face.mouth_activity:.2f}"
    expr_color = _EXPR_COLOR.get(face.expression, (220, 220, 220))

    font = cv2.FONT_HERSHEY_SIMPLEX
    scale = 0.55
    thickness = 2
    y_text = max(48, y1 - 8)
    cv2.putText(frame, label_1, (x1, y_text - 36), font, scale, color, thickness, cv2.LINE_AA)
    cv2.putText(frame, label_2, (x1, y_text - 18), font, scale, expr_color, thickness, cv2.LINE_AA)
    cv2.putText(frame, label_3, (x1, y_text), font, scale, speak_color, thickness, cv2.LINE_AA)

    if debug and face.gaze_metrics is not None:
        m = face.gaze_metrics
        eye_line = (
            f"eye L={m.fused_left:.2f} R={m.fused_right:.2f} "
            f"D={m.fused_down:.2f} U={m.fused_up:.2f}"
        )
        cv2.putText(
            frame,
            eye_line,
            (x1, min(frame.shape[0] - 8, y2 + 18)),
            font,
            0.45,
            (220, 220, 80),
            1,
            cv2.LINE_AA,
        )


def _draw_hud(
    frame: np.ndarray,
    result: FrameAnalysisResult,
    fps: float,
    risk: RiskState,
    warn_after: float,
    *,
    gaze_mode: GazeMode,
) -> None:
    h, w = frame.shape[:2]
    overlay = frame.copy()
    cv2.rectangle(overlay, (0, 0), (w, 78), (20, 20, 20), -1)
    cv2.addWeighted(overlay, 0.45, frame, 0.55, 0, frame)

    summary = (
        f"Faces: {result.face_count}   FPS: {fps:.1f}   "
        f"mode={gaze_mode.value}   warn_after={warn_after:.0f}s"
    )
    cv2.putText(
        frame,
        summary,
        (12, 24),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.55,
        (240, 240, 240),
        2,
        cv2.LINE_AA,
    )
    cv2.putText(
        frame,
        "q/ESC quit | s log JSON snapshot",
        (12, 48),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.5,
        (180, 180, 180),
        1,
        cv2.LINE_AA,
    )

    if risk.kind and risk.active_seconds > 0:
        remain = max(0.0, warn_after - risk.active_seconds)
        if remain > 0:
            risk_line = f"RISK {risk.kind}: {risk.active_seconds:.1f}s  (warn in {remain:.1f}s)"
            color = (0, 180, 255)
        else:
            risk_line = f"RISK {risk.kind}: {risk.active_seconds:.1f}s  (WARN)"
            color = (0, 80, 255)
        cv2.putText(
            frame,
            risk_line,
            (12, 70),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            color,
            1,
            cv2.LINE_AA,
        )


def _open_camera(index: int, width: int, height: int) -> cv2.VideoCapture:
    cap = cv2.VideoCapture(index, cv2.CAP_DSHOW)
    if not cap.isOpened():
        cap.release()
        cap = cv2.VideoCapture(index)
    if not cap.isOpened():
        raise RuntimeError(
            f"Could not open camera index {index}. "
            "Check that no other app is using the webcam."
        )
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    return cap


def run_camera_loop(
    *,
    camera_index: int = 0,
    max_faces: int = 5,
    width: int = 1280,
    height: int = 720,
    model_path: Path | None = None,
    warn_after_override: float | None = None,
    tts_enabled: bool = True,
    gaze_mode_override: str | None = None,
    gaze_debug: bool | None = None,
) -> int:
    if warn_after_override is not None:
        app_config.CAMERA_WARN_AFTER_SEC = float(warn_after_override)
    if not tts_enabled:
        app_config.CAMERA_WARN_TTS_ENABLED = False
    if gaze_mode_override:
        app_config.CAMERA_GAZE_MODE = gaze_mode_override
    if gaze_debug is not None:
        app_config.CAMERA_GAZE_DEBUG = bool(gaze_debug)

    gaze_mode = parse_gaze_mode(app_config.CAMERA_GAZE_MODE)
    debug = bool(app_config.CAMERA_GAZE_DEBUG)

    analyzer = FaceAnalyzer(
        model_path=model_path,
        max_faces=max_faces,
        gaze_mode=gaze_mode,
    )
    speaker: Optional[EdgeTtsSpeaker] = None
    if app_config.CAMERA_WARN_TTS_ENABLED:
        speaker = EdgeTtsSpeaker(
            voice=app_config.TTS_VOICE,
            rate=app_config.TTS_RATE,
        )
    monitor = IntegrityWarnMonitor(speaker)
    cap = _open_camera(camera_index, width, height)
    warn_after = float(app_config.CAMERA_WARN_AFTER_SEC)

    logger.info(
        "Camera opened index=%s size~=%sx%s gaze_mode=%s debug=%s — press q to quit",
        camera_index,
        int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
        int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
        gaze_mode.value,
        debug,
    )

    fps_smooth = 0.0
    last_t = time.perf_counter()
    frame_idx = 0

    try:
        while True:
            ok, frame = cap.read()
            if not ok or frame is None:
                logger.warning("Failed to read frame from camera")
                break

            frame = cv2.flip(frame, 1)

            now = time.perf_counter()
            dt = max(1e-6, now - last_t)
            last_t = now
            inst_fps = 1.0 / dt
            fps_smooth = inst_fps if fps_smooth <= 0 else (0.9 * fps_smooth + 0.1 * inst_fps)

            timestamp_ms = int(frame_idx * (1000.0 / max(fps_smooth, 1.0)))
            frame_idx += 1

            result = analyzer.analyze_bgr(frame, timestamp_ms=timestamp_ms)
            risk = monitor.update(result, now)

            for face in result.faces:
                _draw_face(frame, face, debug=debug)
            _draw_hud(
                frame,
                result,
                fps_smooth,
                risk,
                warn_after,
                gaze_mode=gaze_mode,
            )

            cv2.imshow(_WINDOW, frame)
            key = cv2.waitKey(1) & 0xFF
            if key in (ord("q"), 27):
                break
            if key == ord("s"):
                payload = result.to_dict()
                payload["risk"] = {
                    "kind": risk.kind,
                    "active_seconds": round(risk.active_seconds, 2),
                    "warn_after_sec": warn_after,
                }
                logger.info("SNAPSHOT %s", json.dumps(payload, ensure_ascii=True))
                print(json.dumps(payload, indent=2))
    finally:
        cap.release()
        cv2.destroyAllWindows()
        analyzer.close()
        if speaker is not None:
            speaker.close()
        logger.info("Camera detection test stopped")

    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        return run_camera_loop(
            camera_index=args.camera,
            max_faces=args.max_faces,
            width=args.width,
            height=args.height,
            model_path=args.model,
            warn_after_override=args.warn_after,
            tts_enabled=not args.no_tts,
            gaze_mode_override=args.gaze_mode,
            gaze_debug=False if args.no_gaze_debug else None,
        )
    except KeyboardInterrupt:
        logger.info("Interrupted")
        return 130
    except Exception as ex:
        logger.exception("Camera detection test failed: %s", ex)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
