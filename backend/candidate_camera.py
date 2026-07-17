"""
Candidate camera integrity for live interviews (Recall per-participant video).

Lock one participant webcam, run FaceAnalyzer, expose a snapshot for presence TTS.
Analysis is armed only after POST /api/start when CAMERA_INTEGRITY_ENABLED is true.

Lock order:
  1) display name matches scheduled candidate_name (can correct a wrong early lock)
  2) Recall transcript speaker id (when available)
  3) When candidate answers after the bot finishes: name match, else most-active webcam
  4) Sole human webcam — only after Start/arm (never on the first lobby frame)

Multi-face: if two significant faces persist > CAMERA_WARN_AFTER_MULTI_FACE_SEC, emit a warn.
"""

from __future__ import annotations

import logging
import re
import threading
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

import numpy as np

import config
from face_analysis import (
    FaceAnalyzer,
    FrameAnalysisResult,
    GazeDirection,
    SpeakingState,
    parse_gaze_mode,
)

logger = logging.getLogger(__name__)

_BOT_NAME_HINTS = ("prabhat", "interview", "bot", "notetaker", "recall")


def normalize_person_name(name: Optional[str]) -> str:
    raw = (name or "").strip().lower()
    raw = re.sub(r"[^\w\s]", " ", raw)
    return re.sub(r"\s+", " ", raw).strip()


def _first_tokens_close(a: str, b: str) -> bool:
    """Atharva ↔ Atharv / prefix nicknames (min 4 chars)."""
    if not a or not b:
        return False
    if a == b:
        return True
    shorter, longer = (a, b) if len(a) <= len(b) else (b, a)
    if len(shorter) >= 4 and longer.startswith(shorter):
        return True
    if len(a) >= 4 and len(b) >= 4 and abs(len(a) - len(b)) <= 2:
        # one-edit-ish: shared prefix of len-1
        n = min(len(a), len(b)) - 1
        if n >= 4 and a[:n] == b[:n]:
            return True
    return False


def names_match(candidate_name: Optional[str], participant_name: Optional[str]) -> bool:
    """Loose match: exact, containment, shared tokens, or close first names."""
    a = normalize_person_name(candidate_name)
    b = normalize_person_name(participant_name)
    if not a or not b:
        return False
    if a == b:
        return True
    if a in b or b in a:
        return True
    ta, tb = a.split(), b.split()
    if ta and tb:
        if _first_tokens_close(ta[0], tb[0]):
            if len(ta) == 1 or len(tb) == 1:
                return True
            if ta[-1] == tb[-1]:
                return True
            # Form first-only vs Teams "First Last"
            if len(ta) == 1 or len(tb) == 1:
                return True
        if ta[0] == tb[0]:
            if len(ta) == 1 or len(tb) == 1:
                return True
            if ta[-1] == tb[-1]:
                return True
    return False


def looks_like_bot_name(name: Optional[str], bot_name: Optional[str] = None) -> bool:
    n = normalize_person_name(name)
    if not n:
        return False
    if bot_name and names_match(bot_name, name):
        return True
    return any(h in n for h in _BOT_NAME_HINTS)


@dataclass
class FaceSnapshot:
    """Lightweight face state for presence / mute detection."""

    face_count: int = 0
    visually_speaking: bool = False
    gaze: str = ""
    locked_participant_id: Optional[str] = None
    locked_participant_name: Optional[str] = None
    updated_at: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "face_count": self.face_count,
            "visually_speaking": self.visually_speaking,
            "gaze": self.gaze,
            "locked_participant_id": self.locked_participant_id,
            "locked_participant_name": self.locked_participant_name,
            "updated_at": self.updated_at,
        }


@dataclass
class _SeenWebcam:
    participant_id: str
    name: Optional[str] = None
    frames: int = 0
    last_seen: float = 0.0


class CandidateCameraTracker:
    """
    Bind one Recall webcam participant and analyze frames after interview start.
    """

    def __init__(
        self,
        *,
        candidate_name: str,
        bot_name: str = "",
        gaze_mode: Optional[str] = None,
    ) -> None:
        self.candidate_name = (candidate_name or "").strip()
        self.bot_name = (bot_name or "").strip()
        self._gaze_mode = parse_gaze_mode(gaze_mode or config.CAMERA_GAZE_MODE)
        self._lock = threading.RLock()
        self._armed = False
        self._analyzer: Optional[FaceAnalyzer] = None
        self._locked_id: Optional[str] = None
        self._locked_name: Optional[str] = None
        self._awaiting_speaker_lock = False
        self._pending_answer_lock = False
        self._last_result: Optional[FrameAnalysisResult] = None
        self._snapshot = FaceSnapshot()
        self._last_analyze_at = 0.0
        self._min_analyze_interval = 0.45
        self._frame_idx = 0
        self._seen: Dict[str, _SeenWebcam] = {}
        self._video_frames_total = 0
        self._last_video_log_at = 0.0
        # Integrity warn state (multi_face / looking_away / looking_down / no_face)
        self._risk_pending_kind: Optional[str] = None
        self._risk_pending_hits = 0
        self._risk_kind: Optional[str] = None
        self._risk_started_at = 0.0
        self._risk_last_hit_at = 0.0
        self._last_warn_at = 0.0
        self._pending_warn_kind: Optional[str] = None

    @property
    def armed(self) -> bool:
        return self._armed

    @property
    def locked_participant_id(self) -> Optional[str]:
        return self._locked_id

    @property
    def snapshot(self) -> FaceSnapshot:
        with self._lock:
            return self._snapshot

    def set_candidate_name(self, name: str) -> None:
        with self._lock:
            self.candidate_name = (name or "").strip()
            self._try_correct_lock_by_name()

    def arm(self) -> None:
        with self._lock:
            if self._armed and self._analyzer is not None:
                self._try_correct_lock_by_name()
                return
            try:
                if self._analyzer is None:
                    self._analyzer = FaceAnalyzer(
                        max_faces=3,
                        gaze_mode=self._gaze_mode,
                    )
                self._armed = True
                self._awaiting_speaker_lock = self._locked_id is None
                self._try_correct_lock_by_name()
                if self._locked_id is None:
                    humans = self._human_webcams()
                    if len(humans) == 1 and humans[0].frames >= 1:
                        self._set_lock(
                            humans[0].participant_id,
                            humans[0].name,
                            "sole_webcam_on_arm",
                        )
                logger.info(
                    "[CAMERA] Armed integrity tracker candidate=%r locked=%s "
                    "seen_webcams=%d video_frames=%d",
                    self.candidate_name,
                    self._locked_id,
                    len(self._seen),
                    self._video_frames_total,
                )
            except Exception as ex:
                logger.exception("[CAMERA] Failed to arm FaceAnalyzer: %s", ex)
                self._armed = False
                self._analyzer = None

    def close(self) -> None:
        with self._lock:
            self._armed = False
            analyzer = self._analyzer
            self._analyzer = None
        if analyzer is not None:
            try:
                analyzer.close()
            except Exception:
                pass

    def _set_lock(self, participant_id: str, participant_name: Optional[str], reason: str) -> None:
        self._locked_id = str(participant_id)
        self._locked_name = (participant_name or "").strip() or None
        self._awaiting_speaker_lock = False
        self._pending_answer_lock = False
        self._snapshot.locked_participant_id = self._locked_id
        self._snapshot.locked_participant_name = self._locked_name
        logger.info(
            "[CAMERA] Locked candidate via %s id=%s name=%r (form_name=%r)",
            reason,
            self._locked_id,
            self._locked_name,
            self.candidate_name,
        )

    def _try_correct_lock_by_name(self) -> bool:
        """If form name matches a seen webcam, lock them (override wrong host lock)."""
        if not self.candidate_name:
            return False
        for seen in self._seen.values():
            if looks_like_bot_name(seen.name, self.bot_name):
                continue
            if names_match(self.candidate_name, seen.name):
                if self._locked_id != seen.participant_id:
                    self._set_lock(seen.participant_id, seen.name, "name_match")
                return True
        return False

    def note_speaker(
        self,
        *,
        participant_id: Optional[str],
        participant_name: Optional[str],
        is_bot: bool,
    ) -> None:
        """Lock candidate from first human Recall-transcript speaker."""
        if is_bot or not participant_id:
            return
        if looks_like_bot_name(participant_name, self.bot_name):
            return
        with self._lock:
            if self._locked_id is not None:
                # Correct if transcript speaker matches form name better
                if self.candidate_name and names_match(
                    self.candidate_name, participant_name
                ):
                    if str(participant_id) != str(self._locked_id):
                        self._set_lock(str(participant_id), participant_name, "speech_name")
                return
            self._set_lock(str(participant_id), participant_name, "speech")

    def lock_on_candidate_answer(self) -> bool:
        """
        Called when local STT/VAD hears the candidate after the bot asked a question.
        """
        with self._lock:
            if self._try_correct_lock_by_name():
                return True
            if self._locked_id is not None:
                # Wrong early lock (host) — prefer name, else keep until we can switch
                if self.candidate_name and not names_match(
                    self.candidate_name, self._locked_name
                ):
                    if self._lock_best_seen_webcam("answer_correct"):
                        return True
                return True
            if not self._armed:
                self._pending_answer_lock = True
                return False
            if self._lock_best_seen_webcam("answer"):
                return True
            self._pending_answer_lock = True
            logger.info(
                "[CAMERA] Pending answer-lock until webcam frames arrive "
                "(video_frames_total=%d)",
                self._video_frames_total,
            )
            return False

    def _human_webcams(self) -> list[_SeenWebcam]:
        out: list[_SeenWebcam] = []
        for seen in self._seen.values():
            if looks_like_bot_name(seen.name, self.bot_name):
                continue
            out.append(seen)
        return out

    def _lock_best_seen_webcam(self, reason: str) -> bool:
        humans = self._human_webcams()
        if not humans:
            logger.info(
                "[CAMERA] Answer/lock requested but no non-bot webcam frames seen yet "
                "(video_frames_total=%d seen=%d)",
                self._video_frames_total,
                len(self._seen),
            )
            return False
        # Prefer name match among humans
        if self.candidate_name:
            for h in humans:
                if names_match(self.candidate_name, h.name):
                    self._set_lock(h.participant_id, h.name, f"{reason}_name")
                    return True
        humans.sort(key=lambda s: (s.last_seen, s.frames), reverse=True)
        best = humans[0]
        if len(humans) > 1:
            logger.info(
                "[CAMERA] Multiple webcams seen (%d) — locking most active id=%s name=%r",
                len(humans),
                best.participant_id,
                best.name,
            )
        self._set_lock(best.participant_id, best.name, reason)
        return True

    def _remember_webcam(
        self,
        participant_id: str,
        participant_name: Optional[str],
        media_type: str,
    ) -> None:
        if media_type and media_type != "webcam":
            return
        if looks_like_bot_name(participant_name, self.bot_name):
            return
        pid = str(participant_id)
        now = time.monotonic()
        seen = self._seen.get(pid)
        if seen is None:
            self._seen[pid] = _SeenWebcam(
                participant_id=pid,
                name=(participant_name or "").strip() or None,
                frames=1,
                last_seen=now,
            )
            logger.info(
                "[CAMERA] Saw webcam participant id=%s name=%r (form_name=%r)",
                pid,
                participant_name,
                self.candidate_name,
            )
        else:
            seen.frames += 1
            seen.last_seen = now
            if participant_name and not seen.name:
                seen.name = participant_name.strip()
        # Opportunistic name lock / correction whenever a matching name appears
        if self.candidate_name and names_match(self.candidate_name, participant_name):
            if self._locked_id != pid:
                self._set_lock(pid, participant_name, "name_match")

    def _try_lock_from_video(
        self,
        participant_id: str,
        participant_name: Optional[str],
        media_type: str,
    ) -> bool:
        if media_type and media_type != "webcam":
            return False
        if looks_like_bot_name(participant_name, self.bot_name):
            return False
        if self.candidate_name and names_match(self.candidate_name, participant_name):
            self._set_lock(str(participant_id), participant_name, "name_match")
            return True
        # Never sole-lock before Start — host often appears first in the lobby
        if not self._armed:
            return False
        humans = self._human_webcams()
        if len(humans) == 1 and humans[0].frames >= 1:
            self._set_lock(humans[0].participant_id, humans[0].name, "sole_webcam")
            return True
        return False

    def _significant_extra_faces(self, result: FrameAnalysisResult) -> bool:
        if len(result.faces) < 2:
            return False
        if not config.CAMERA_WARN_ON_MULTI_FACE:
            return False
        primary = result.faces[0]
        p_area = max(1.0, float(primary.bbox.width * primary.bbox.height))
        ratio = float(config.CAMERA_WARN_MULTI_FACE_MIN_AREA_RATIO)
        for face in result.faces[1:]:
            area = float(face.bbox.width * face.bbox.height)
            if area / p_area >= ratio:
                return True
        return False

    @staticmethod
    def _is_off_screen_kind(kind: Optional[str]) -> bool:
        return kind in ("looking_away", "looking_down")

    def _classify_risk(self, result: FrameAnalysisResult) -> Optional[str]:
        """
        Priority: multi_face > no_face > off-screen (away/down[/side]).

        Thinking glances: looking_up never warns. Left/right only if
        CAMERA_WARN_INCLUDE_SIDE_LOOK. Strong looking_away / looking_down still warn
        after CAMERA_WARN_AFTER_AWAY_SEC (unless lips moving and ignore flag is on).
        """
        if self._significant_extra_faces(result):
            return "multi_face"
        if result.face_count <= 0:
            return "no_face" if config.CAMERA_WARN_ON_NO_FACE else None
        if not result.faces:
            return None
        primary = result.faces[0]
        gaze = primary.gaze
        speaking = primary.speaking == SpeakingState.SPEAKING
        ignore_while_lips = bool(config.CAMERA_WARN_IGNORE_AWAY_WHILE_SPEAKING)

        # Eye-up while thinking — never treat as integrity risk
        if gaze == GazeDirection.LOOKING_UP:
            return None

        if config.CAMERA_WARN_ON_LOOKING_DOWN and gaze == GazeDirection.LOOKING_DOWN:
            if not (ignore_while_lips and speaking):
                return "looking_down"

        if config.CAMERA_WARN_ON_LOOKING_AWAY and gaze == GazeDirection.LOOKING_AWAY:
            if not (ignore_while_lips and speaking):
                return "looking_away"

        # Optional: mild left/right iris (off by default for live interviews)
        if config.CAMERA_WARN_INCLUDE_SIDE_LOOK and gaze in (
            GazeDirection.LOOKING_LEFT,
            GazeDirection.LOOKING_RIGHT,
        ):
            if not (ignore_while_lips and speaking):
                return "looking_away"

        return None

    def _threshold_for(self, kind: str) -> float:
        if kind == "multi_face":
            return float(config.CAMERA_WARN_AFTER_MULTI_FACE_SEC)
        if kind in ("looking_away", "looking_down"):
            return float(config.CAMERA_WARN_AFTER_AWAY_SEC)
        return float(config.CAMERA_WARN_AFTER_SEC)

    def _same_risk_family(self, a: Optional[str], b: Optional[str]) -> bool:
        if a is None or b is None:
            return False
        if a == b:
            return True
        # left/right/away/down share one sticky off-screen timer
        if self._is_off_screen_kind(a) and self._is_off_screen_kind(b):
            return True
        return False

    def _clear_risk(self) -> None:
        self._risk_pending_kind = None
        self._risk_pending_hits = 0
        self._risk_kind = None
        self._risk_started_at = 0.0
        self._risk_last_hit_at = 0.0

    def _maybe_emit_warn(self, kind: str, now: float, held: float) -> None:
        cooldown = float(config.CAMERA_WARN_COOLDOWN_SEC)
        threshold = self._threshold_for(kind)
        if held < threshold:
            return
        if (now - self._last_warn_at) < cooldown:
            return
        if self._pending_warn_kind == kind:
            return
        self._pending_warn_kind = kind
        self._last_warn_at = now
        logger.info(
            "[CAMERA] Warn ready kind=%s held=%.1fs threshold=%.1fs id=%s",
            kind,
            held,
            threshold,
            self._locked_id,
        )

    def _update_integrity_risk(self, result: FrameAnalysisResult, now: float) -> None:
        """Accumulate sustained risk with sticky off-screen + brief grace gaps."""
        if not config.CAMERA_WARN_TTS_ENABLED:
            self._clear_risk()
            return

        raw = self._classify_risk(result)
        hold = max(1, int(config.CAMERA_WARN_HOLD_FRAMES_LIVE))
        grace = float(config.CAMERA_WARN_RISK_GRACE_SEC)

        if raw is None:
            # Grace: keep multi_face / no_face / off-screen timer through short blips
            if (
                self._risk_kind is not None
                and self._risk_last_hit_at > 0
                and (now - self._risk_last_hit_at) <= grace
            ):
                held = now - self._risk_started_at if self._risk_started_at > 0 else 0.0
                self._maybe_emit_warn(self._risk_kind, now, held)
            else:
                self._clear_risk()
            return

        if self._same_risk_family(raw, self._risk_pending_kind):
            self._risk_pending_hits += 1
        else:
            self._risk_pending_kind = raw
            self._risk_pending_hits = 1

        if self._risk_pending_hits < hold:
            return

        self._risk_last_hit_at = now
        if not self._same_risk_family(raw, self._risk_kind) or self._risk_started_at <= 0:
            self._risk_kind = raw
            self._risk_started_at = now
            logger.info(
                "[CAMERA] Risk started kind=%s id=%s faces=%d gaze=%s",
                raw,
                self._locked_id,
                result.face_count,
                result.faces[0].gaze.value if result.faces else "-",
            )
        else:
            # Sticky family: keep timer, refresh label (e.g. away → down)
            self._risk_kind = raw

        held = now - self._risk_started_at
        self._maybe_emit_warn(raw, now, held)

    def consume_warn(self) -> Optional[str]:
        """Return and clear a pending integrity warn kind."""
        with self._lock:
            kind = self._pending_warn_kind
            self._pending_warn_kind = None
            return kind

    def process_png_frame(
        self,
        *,
        png_bytes: bytes,
        participant_id: Optional[str],
        participant_name: Optional[str],
        media_type: str = "webcam",
        timestamp_ms: Optional[int] = None,
    ) -> Optional[FaceSnapshot]:
        if not png_bytes or not participant_id:
            return None

        with self._lock:
            self._video_frames_total += 1
            now = time.monotonic()
            if now - self._last_video_log_at >= 5.0:
                self._last_video_log_at = now
                logger.info(
                    "[CAMERA] video frames total=%d media=%s id=%s name=%r locked=%s armed=%s",
                    self._video_frames_total,
                    media_type,
                    participant_id,
                    participant_name,
                    self._locked_id,
                    self._armed,
                )

            self._remember_webcam(str(participant_id), participant_name, media_type or "webcam")

            # Registry-only before Start interview (analyzer not armed yet)
            if not self._armed or self._analyzer is None:
                if self._locked_id is None:
                    self._try_lock_from_video(
                        str(participant_id), participant_name, media_type or "webcam"
                    )
                return None

            if media_type and media_type != "webcam":
                return None

            if self._locked_id is None:
                if self._pending_answer_lock and not looks_like_bot_name(
                    participant_name, self.bot_name
                ):
                    # Prefer name if this frame matches; else lock this human webcam
                    if self.candidate_name and names_match(
                        self.candidate_name, participant_name
                    ):
                        self._set_lock(
                            str(participant_id), participant_name, "answer_pending_name"
                        )
                    else:
                        # With multiple humans, wait for name or use most-active on answer()
                        humans = self._human_webcams()
                        if len(humans) == 1:
                            self._set_lock(
                                str(participant_id), participant_name, "answer_pending"
                            )
                        elif self.candidate_name:
                            self._try_correct_lock_by_name()
                        else:
                            self._lock_best_seen_webcam("answer_pending")
                else:
                    self._try_lock_from_video(
                        str(participant_id), participant_name, media_type or "webcam"
                    )

            if self._locked_id is None:
                return None
            if str(participant_id) != str(self._locked_id):
                return None

            if now - self._last_analyze_at < self._min_analyze_interval:
                return self._snapshot
            self._last_analyze_at = now

            try:
                import cv2

                arr = np.frombuffer(png_bytes, dtype=np.uint8)
                frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                if frame is None or frame.size == 0:
                    logger.warning("[CAMERA] PNG decode failed id=%s", participant_id)
                    return None
                ts = timestamp_ms
                if ts is None:
                    self._frame_idx += 1
                    ts = self._frame_idx * 500
                result = self._analyzer.analyze_bgr(frame, timestamp_ms=int(ts))
                self._last_result = result
                speaking = False
                gaze = ""
                if result.faces:
                    primary = result.faces[0]
                    speaking = primary.speaking == SpeakingState.SPEAKING
                    gaze = primary.gaze.value
                self._snapshot = FaceSnapshot(
                    face_count=result.face_count,
                    visually_speaking=speaking,
                    gaze=gaze,
                    locked_participant_id=self._locked_id,
                    locked_participant_name=self._locked_name,
                    updated_at=now,
                )
                self._update_integrity_risk(result, now)
                if (
                    self._frame_idx % 10 == 0
                    or result.face_count != 1
                    or (gaze and gaze != "looking_center")
                ):
                    logger.info(
                        "[CAMERA] analyze faces=%d gaze=%s speaking=%s id=%s name=%r",
                        result.face_count,
                        gaze or "-",
                        speaking,
                        self._locked_id,
                        self._locked_name,
                    )
                return self._snapshot
            except Exception as ex:
                logger.warning("[CAMERA] Frame analyze failed: %s", ex)
                return None

    def presence_reason(self, *, stale_after_sec: float = 8.0) -> Optional[str]:
        """
        Camera hint for the silence presence ladder (not a live mid-answer warn).

        - cannot_see: locked candidate, no face recently
        - muted_mic: face present and lips moving (silence already confirmed by caller)
        """
        with self._lock:
            if not self._armed or self._locked_id is None:
                return None
            snap = self._snapshot
            age = time.monotonic() - snap.updated_at if snap.updated_at else 1e9
            if age > stale_after_sec:
                return "cannot_see"
            if snap.face_count <= 0:
                return "cannot_see"
            if snap.visually_speaking:
                return "muted_mic"
            return None
