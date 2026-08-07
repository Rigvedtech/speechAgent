"""
Local camera test for interview face / gaze / expression analysis.

Matches live meeting warn policy (same camera_integrity_policy + .env timers).
Simulate turns:
  c — candidate answer turn (warns ON)  [default]
  a — AI asking turn (warns OFF)

Usage (from backend/):
  .\\venv\\Scripts\\python.exe camera_detection_test.py
  .\\venv\\Scripts\\python.exe camera_detection_test.py --gaze-mode interview --no-tts

Controls:
  q / ESC — quit
  s       — print current frame JSON to terminal
  a       — AI turn (looking away OK, no warn)
  c       — candidate turn (interview dwell timers from .env)
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
from camera_integrity_policy import classify_integrity_risk, significant_extra_faces
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
    "looking_side": "Please face the camera and keep looking at the screen.",
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
    """Accumulate sustained risk, then speak Edge-TTS after configured dwell times."""

    def __init__(self, speaker: Optional[EdgeTtsSpeaker]) -> None:
        self._speaker = speaker
        self._warn_after = float(app_config.CAMERA_WARN_AFTER_SEC)
        self._warn_after_down = float(
            getattr(app_config, "CAMERA_WARN_AFTER_DOWN_SEC", 3.0)
        )
        self._warn_after_side = float(
            getattr(app_config, "CAMERA_WARN_AFTER_SIDE_SEC", 5.0)
        )
        self._warn_after_away = float(
            getattr(app_config, "CAMERA_WARN_AFTER_AWAY_SEC", self._warn_after_side)
        )
        self._cooldown = float(app_config.CAMERA_WARN_COOLDOWN_SEC)
        self._cooldown_multi = float(
            getattr(app_config, "CAMERA_WARN_COOLDOWN_MULTI_FACE_SEC", 5.0)
        )
        self._hold_frames = max(1, int(getattr(app_config, "CAMERA_WARN_HOLD_FRAMES", 8)))
        self._enabled = bool(app_config.CAMERA_WARN_TTS_ENABLED) and speaker is not None
        # Match live meeting: warns only on candidate answer turn (not AI asking)
        self._candidate_turn = True
        self._risk = RiskState()
        self._pending_kind: Optional[str] = None
        self._pending_hits = 0
        self._last_gaze_warn_at = 0.0
        self._last_multi_warn_at = 0.0
        side_min_yaw = float(
            getattr(app_config, "CAMERA_WARN_SIDE_MIN_YAW_DEG", 0.0) or 0.0
        )
        down_min_pitch = float(
            getattr(app_config, "CAMERA_WARN_DOWN_MIN_PITCH_DEG", 0.0) or 0.0
        )
        ignore_speaking = bool(
            getattr(app_config, "CAMERA_WARN_IGNORE_AWAY_WHILE_SPEAKING", False)
        )
        logger.info(
            "Warn monitor: enabled=%s down_after=%.1fs side_after=%.1fs "
            "away_after=%.1fs gaze_cd=%.1fs multi_cd=%.1fs side_look=%s "
            "side_min_yaw=%.0f down_min_pitch=%.0f ignore_while_speaking=%s "
            "hold_frames=%d turn=candidate (press a=AI / c=candidate) [shared policy]",
            self._enabled,
            self._warn_after_down,
            self._warn_after_side,
            self._warn_after_away,
            self._cooldown,
            self._cooldown_multi,
            bool(app_config.CAMERA_WARN_INCLUDE_SIDE_LOOK),
            side_min_yaw,
            down_min_pitch,
            ignore_speaking,
            self._hold_frames,
        )

    @property
    def candidate_turn(self) -> bool:
        return self._candidate_turn

    def set_candidate_turn(self, active: bool) -> None:
        active = bool(active)
        if self._candidate_turn == active:
            return
        self._candidate_turn = active
        self._pending_kind = None
        self._pending_hits = 0
        self._risk = RiskState(last_warn_at=self._risk.last_warn_at)
        logger.info(
            "Turn=%s — integrity warns %s",
            "candidate" if active else "ai",
            "ON" if active else "OFF",
        )

    def _significant_extra_faces(self, result: FrameAnalysisResult) -> bool:
        return significant_extra_faces(result)

    def _classify(self, result: FrameAnalysisResult) -> Optional[str]:
        """Same policy as live CandidateCameraTracker (shared module)."""
        return classify_integrity_risk(result)

    def _threshold_for(self, kind: str) -> float:
        if kind == "looking_down":
            return self._warn_after_down
        if kind == "looking_side":
            return self._warn_after_side
        if kind == "looking_away":
            return self._warn_after_away
        if kind == "multi_face":
            return float(
                getattr(app_config, "CAMERA_WARN_AFTER_MULTI_FACE_SEC", 5.0)
            )
        return self._warn_after

    def _cooldown_ok(self, kind: str, now: float) -> bool:
        if kind == "multi_face":
            return (now - self._last_multi_warn_at) >= self._cooldown_multi
        return (now - self._last_gaze_warn_at) >= self._cooldown

    def update(self, result: FrameAnalysisResult, now: float) -> RiskState:
        # Same as live meeting: no warn accumulation while "AI asking"
        if not self._candidate_turn:
            self._pending_kind = None
            self._pending_hits = 0
            self._risk = RiskState(last_warn_at=self._risk.last_warn_at)
            return self._risk

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
            and self._cooldown_ok(kind, now)
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
            if kind == "multi_face":
                self._last_multi_warn_at = now
            else:
                self._last_gaze_warn_at = now

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
    label_2 = (
        f"{face.expression.value}  conf={face.confidence:.2f}  "
        f"pitch={face.head_pitch_deg:+.0f}"
    )
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
    down_after: float = 3.0,
    side_after: float = 5.0,
    candidate_turn: bool = True,
) -> None:
    h, w = frame.shape[:2]
    overlay = frame.copy()
    cv2.rectangle(overlay, (0, 0), (w, 96), (20, 20, 20), -1)
    cv2.addWeighted(overlay, 0.45, frame, 0.55, 0, frame)

    turn_label = "candidate WARN ON" if candidate_turn else "AI asking WARN OFF"
    summary = (
        f"Faces: {result.face_count}  FPS: {fps:.1f}  "
        f"mode={gaze_mode.value}  down={down_after:.0f}s side={side_after:.0f}s"
    )
    cv2.putText(
        frame,
        summary,
        (12, 22),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.5,
        (240, 240, 240),
        2,
        cv2.LINE_AA,
    )
    cv2.putText(
        frame,
        f"turn={turn_label}  |  a=AI  c=candidate  q=quit  s=snapshot",
        (12, 46),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.48,
        (0, 220, 120) if candidate_turn else (0, 180, 255),
        1,
        cv2.LINE_AA,
    )

    if not candidate_turn:
        cv2.putText(
            frame,
            "AI turn — looking away OK (no warn)",
            (12, 70),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (180, 180, 180),
            1,
            cv2.LINE_AA,
        )
    elif risk.kind and risk.active_seconds > 0:
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
    else:
        down_s = float(getattr(app_config, "CAMERA_WARN_AFTER_DOWN_SEC", 6.0))
        side_s = float(getattr(app_config, "CAMERA_WARN_AFTER_SIDE_SEC", 8.0))
        cool_s = float(app_config.CAMERA_WARN_COOLDOWN_SEC)
        cv2.putText(
            frame,
            f"head/face integrity | chin≥16° or side yaw≥20° → warn "
            f"({down_s:.0f}/{side_s:.0f}s, cd {cool_s:.0f}s)",
            (12, 70),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            (180, 180, 180),
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
    down_after = float(getattr(app_config, "CAMERA_WARN_AFTER_DOWN_SEC", 3.0))
    side_after = float(getattr(app_config, "CAMERA_WARN_AFTER_SIDE_SEC", 5.0))

    logger.info(
        "Camera opened index=%s size~=%sx%s gaze_mode=%s debug=%s "
        "down_after=%.0fs side_after=%.0fs — press q to quit",
        camera_index,
        int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
        int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
        gaze_mode.value,
        debug,
        down_after,
        side_after,
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
            warn_after = monitor._threshold_for(risk.kind) if risk.kind else down_after

            for face in result.faces:
                _draw_face(frame, face, debug=debug)
            _draw_hud(
                frame,
                result,
                fps_smooth,
                risk,
                warn_after,
                gaze_mode=gaze_mode,
                down_after=down_after,
                side_after=side_after,
                candidate_turn=monitor.candidate_turn,
            )

            cv2.imshow(_WINDOW, frame)
            key = cv2.waitKey(1) & 0xFF
            if key in (ord("q"), 27):
                break
            if key == ord("a"):
                monitor.set_candidate_turn(False)
            if key == ord("c"):
                monitor.set_candidate_turn(True)
            if key == ord("s"):
                payload = result.to_dict()
                payload["risk"] = {
                    "kind": risk.kind,
                    "active_seconds": round(risk.active_seconds, 2),
                    "warn_after_sec": warn_after,
                    "candidate_turn": monitor.candidate_turn,
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
