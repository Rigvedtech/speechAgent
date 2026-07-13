import sys
import queue
import re
import time
import threading
import logging
import torch
import numpy as np
import collections
from typing import Optional, Tuple
from faster_whisper import WhisperModel

from config import (
    MODEL_SIZE,
    DEVICE,
    COMPUTE_TYPE,
    SAMPLE_RATE,
    CHANNELS,
    SILENCE_DURATION,
    STT_FALLBACK_ENABLED,
    USER_BARGE_IN_ENABLED,
    BOT_INTERRUPT_ENABLED,
    BOT_INTERRUPT_MIN_PARTIAL_SEC,
    ANSWER_DEPTH_CHECK_WINDOW_SEC,
    ANSWER_TOPIC_POLL_WINDOW_SEC,
    MID_ANSWER_BOT_COOLDOWN_SEC,
    SARVAM_LOCAL_SILENCE_SEC,
    WHISPER_LOCAL_SILENCE_SEC,
    SARVAM_QUALITY_MIN_UTTERANCE_SEC,
    SARVAM_QUALITY_MIN_CHARS,
    TURN_MERGE_ENABLED,
    TURN_MERGE_WINDOW_SEC,
    TURN_MERGE_MIN_AUDIO_SEC,
    TURN_MERGE_MIN_CHARS,
    TURN_MERGE_MIN_HOLD_SEC,
    TURN_MERGE_MAX_SHORT_HOLD_SEC,
    MIN_ANSWER_WORDS,
    NAME_NORMALIZE_ENABLED,
    INTRO_MIN_CHARS,
    INTRO_MIN_SPEECH_SEC,
    INTRO_MERGE_WINDOW_SEC,
    CORE_ANSWER_SOFT_SILENCE_SEC,
    CORE_ANSWER_MERGE_WINDOW_SEC,
    CORE_LONG_ANSWER_SPEECH_SEC,
    CORE_LONG_ANSWER_SILENCE_SEC,
    CORE_ANSWER_MAX_HOLD_SEC,
    CLARIFIER_REPLY_SILENCE_SEC,
    TURN_FLUSH_GUARD_MIN_CHARS,
    TURN_FLUSH_DEFER_SEC,
    STREAM_STT_ENABLED,
    STREAM_STT_FINALIZE_SEC,
    STREAM_STT_MIN_CHARS,
    INCOMPLETE_MERGE_WINDOW_SEC,
    SHORT_UTTERANCE_MAX_SEC,
    SHORT_UTTERANCE_SILENCE_SEC,
    sarvam_collect_deadline_sec,
    sarvam_transcribe_timeout_sec,
)
from state import AgentState
from interview_engine import (
    detect_incomplete_answer,
    should_commit_short_turn_immediately,
)
from transcript_utils import normalize_candidate_name

logger = logging.getLogger(__name__)


class STTEngine:
    def __init__(self, state: AgentState, sarvam_engine=None):
        """
        Args:
            state:         Shared AgentState
            sarvam_engine: Optional SarvamSTTEngine — primary transcription engine.
                           When provided, Sarvam Saaras V3 is tried first and Whisper
                           is loaded lazily only if Sarvam fails.
                           When None (main.py standalone mode), Whisper loads at init.
        """
        self.state = state
        self.sarvam_engine = sarvam_engine
        self.audio_buffer = []
        self.last_speech_time = 0.0
        self.is_recording = False
        self.actual_samplerate = SAMPLE_RATE
        self.actual_channels = CHANNELS

        # Adaptive endpointing (split by engine profile)
        self._active_endpoint_silence = (
            SARVAM_LOCAL_SILENCE_SEC if self.sarvam_engine is not None else WHISPER_LOCAL_SILENCE_SEC
        )
        self.base_silence_duration = self._active_endpoint_silence
        self.adaptive_silence_duration = self._active_endpoint_silence
        self.recent_utterance_lengths = []

        # User barge-in while bot speaks (disabled by default for interview mode)
        self.candidate_speaking_duration = 0.0
        self.interruption_threshold = 3.0

        # Bot interrupt while user speaks
        self._recording_started_at = 0.0
        self._last_bot_interrupt_check = 0.0
        self._bot_interrupt_cooldown_until = 0.0
        self._check_num: int = 0
        self._prev_check_partial: str = ""

        # Lazy Whisper — only loaded when Sarvam fails (or no Sarvam configured)
        self._whisper_model = None
        self._whisper_lock = threading.Lock()
        self._stt_lock = threading.Lock()

        # Turn commit / merge guard (hold suspicious partials, merge within window)
        self._pending_audio: Optional[np.ndarray] = None
        self._pending_text: str = ""
        self._pending_until: float = 0.0
        self._pending_sarvam_failed: bool = False
        self._pending_core_deadline: float = 0.0
        self._turn_q_index: int = -1
        # Dedicated flush timer — must not depend on next mic chunk (fixes 40s+ silence deadlock)
        self._flush_timer: Optional[threading.Timer] = None
        self._flush_lock = threading.Lock()
        self._pending_commit_lock = threading.Lock()
        # Live Sarvam streaming (transcript builds while speaking)
        self._live_stream_on = False
        self._live_stream_pcm_buf = np.empty(0, dtype=np.float32)
        self._live_stream_chunk_samples = int(SAMPLE_RATE * 0.1)  # 100ms

        print(f"Loading Silero VAD on {DEVICE}...")
        self.vad_model, _ = torch.hub.load(
            repo_or_dir='snakers4/silero-vad',
            model='silero_vad',
            force_reload=False
        )
        self.vad_model.to(DEVICE)

        if self.sarvam_engine is not None:
            print("[STT] Primary: Sarvam Saaras V3 (batch per utterance)")
            if STT_FALLBACK_ENABLED:
                print(f"[STT] Fallback: Faster Whisper '{MODEL_SIZE}' (loads on demand)")
            else:
                print("[STT] Whisper fallback disabled (STT_FALLBACK_ENABLED=false)")
        else:
            self._ensure_whisper()

        if not USER_BARGE_IN_ENABLED:
            print("[STT] User barge-in disabled — mic ignored while bot speaks")

    def _ensure_whisper(self):
        """Load Whisper model once — deferred until fallback is needed."""
        if self._whisper_model is not None:
            return self._whisper_model
        with self._whisper_lock:
            if self._whisper_model is not None:
                return self._whisper_model
            print(f"Loading Whisper model '{MODEL_SIZE}' on {DEVICE}...")
            self._whisper_model = WhisperModel(
                MODEL_SIZE, device=DEVICE, compute_type=COMPUTE_TYPE
            )
            print(f"[STT] Whisper fallback ready on {DEVICE}")
            return self._whisper_model

    def _reset_recording_state(self):
        self._abort_live_stream()
        self.audio_buffer = []
        self.is_recording = False
        self.state.candidate_recording = False
        self.last_speech_time = 0.0
        self._recording_started_at = 0.0
        self._last_bot_interrupt_check = 0.0
        self._check_num = 0
        self._prev_check_partial = ""

    def preserve_answer_in_progress(self) -> None:
        """Save in-progress answer audio before mid-answer bot speech (clarifier/rephrase)."""
        if not self.is_recording or not self.audio_buffer:
            return
        self._preserved_snapshot = {
            "audio": np.concatenate(self.audio_buffer).copy(),
            "started_at": self._recording_started_at,
            "check_num": self._check_num,
            "prev_partial": self._prev_check_partial,
            "last_speech_time": self.last_speech_time,
            "live_text": self._get_live_partial_text(),
        }
        # Pause live stream while bot speaks (will restart on restore)
        self._abort_live_stream()

    def restore_answer_in_progress(self) -> None:
        """Restore answer buffer after mid-answer bot speech so the candidate can continue."""
        snap = getattr(self, "_preserved_snapshot", None)
        if not snap:
            return
        self.audio_buffer = [snap["audio"]]
        self.is_recording = True
        self._recording_started_at = snap["started_at"]
        self._check_num = snap["check_num"]
        self._prev_check_partial = snap["prev_partial"]
        self.last_speech_time = snap.get("last_speech_time", 0.0)
        saved_live = (snap.get("live_text") or "").strip()
        self._preserved_snapshot = None
        # Resume live STT for continued answer after mid-answer bot speech
        if self._stream_stt_enabled() and not self._live_stream_on:
            self._start_live_stream()
            # Seed prior live text so topic/final merge keeps earlier speech
            if saved_live and self.sarvam_engine is not None:
                try:
                    with self.sarvam_engine._live_lock:
                        if self.sarvam_engine._live_active and not self.sarvam_engine._live_parts:
                            self.sarvam_engine._live_parts = [saved_live]
                except Exception:
                    pass
            if saved_live:
                self._prev_check_partial = saved_live

    def _orch_awaiting_clarifier(self) -> bool:
        orch = getattr(self.state, "interview_orchestrator", None)
        return bool(orch and getattr(orch, "awaiting_clarifier_reply", False))

    def _in_core_phase(self) -> bool:
        orch = getattr(self.state, "interview_orchestrator", None)
        if orch is None:
            return False
        from interview_engine import InterviewPhase
        return orch.phase == InterviewPhase.CORE

    def _in_await_intro_phase(self) -> bool:
        orch = getattr(self.state, "interview_orchestrator", None)
        if orch is None:
            return False
        from interview_engine import InterviewPhase
        return orch.phase == InterviewPhase.AWAIT_INTRO

    _INTRO_GREETING_WORDS = frozenset({
        "hello", "hi", "hey", "namaste", "namaskar", "good", "morning",
        "evening", "afternoon", "prabhat", "prabhupada", "sir", "maam",
        "ma'am", "thanks", "thank", "you",
    })

    def _is_greeting_only_intro(self, text: str) -> bool:
        """Short hello/namaste-only utterances are not a complete introduction."""
        stripped = re.sub(r"[^\w\s']", " ", (text or "").strip().lower())
        words = [w for w in stripped.split() if w]
        if not words or len(words) > 6:
            return False
        return all(w in self._INTRO_GREETING_WORDS for w in words)

    def _should_hold_intro_turn(
        self, text: str, utterance_duration: float
    ) -> Tuple[bool, str]:
        stripped = (text or "").strip()
        if len(stripped) >= INTRO_MIN_CHARS:
            return False, ""
        if (
            utterance_duration >= INTRO_MIN_SPEECH_SEC
            and len(stripped) >= max(40, INTRO_MIN_CHARS // 2)
        ):
            return False, ""
        if self._is_greeting_only_intro(stripped):
            return True, "greeting_only"
        if len(stripped) < INTRO_MIN_CHARS:
            return True, "intro_too_short"
        return False, ""

    def _should_flush_held_intro_turn(self, text: str, audio_sec: float) -> bool:
        stripped = (text or "").strip()
        if not stripped:
            return False
        if len(stripped) >= INTRO_MIN_CHARS:
            return True
        if audio_sec >= INTRO_MIN_SPEECH_SEC and len(stripped) >= 40:
            return True
        return False

    def _merge_window_sec(self, hold_reason: str = "", text: str = "") -> float:
        if hold_reason == "core_answer_in_progress":
            # Incomplete mid-thought needs a longer listen-back than normal soft merge
            if text and detect_incomplete_answer(text):
                return float(INCOMPLETE_MERGE_WINDOW_SEC)
            return CORE_ANSWER_MERGE_WINDOW_SEC
        if self._in_await_intro_phase():
            return INTRO_MERGE_WINDOW_SEC
        return TURN_MERGE_WINDOW_SEC

    _ANSWER_DONE_SUFFIX = re.compile(
        r"(?:"
        r"that'?s\s+it|that'?s\s+all|i'?m\s+done|that\s+is\s+it"
        r"|bas|ठीक\s+है|बस|हो\s+गया"
        r")\s*[\.\!\?]*(?:\s+|$)",
        re.IGNORECASE,
    )

    def _contains_answer_done_marker(self, text: str) -> bool:
        """Detect completion cues anywhere in the answer, especially at the end."""
        t = (text or "").strip()
        if not t:
            return False
        if self._ANSWER_DONE_SUFFIX.search(t):
            return True
        # Short utterance that is only a done phrase
        if len(t) <= 40 and re.match(
            r"^(?:that'?s\s+it|that'?s\s+all|done|bas|ठीक\s+है|बस)\s*[\.\!\?]*$",
            t,
            re.IGNORECASE,
        ):
            return True
        return False

    def _is_answer_done_phrase(self, text: str) -> bool:
        return self._contains_answer_done_marker(text)

    def _core_answer_in_progress(self) -> bool:
        """True when mid-answer progress checks indicate an in-flight CORE answer."""
        orch = getattr(self.state, "interview_orchestrator", None)
        if orch is None or not self._in_core_phase():
            return False
        if orch.awaiting_clarifier_reply:
            return False
        if orch.progress_checks:
            return True
        if orch.answer_continuation_count > 0:
            return True
        return False

    def _active_endpoint_silence_for_recording(self) -> float:
        """Soft silence endpoint — ~2s pause ends utterance capture (merge may still apply)."""
        if self._orch_awaiting_clarifier():
            return CLARIFIER_REPLY_SILENCE_SEC
        endpoint = self.adaptive_silence_duration
        if not self.is_recording or not self._recording_started_at:
            return endpoint
        if not self._in_core_phase():
            return endpoint
        # Short utterances (repeat/rephrase): faster endpoint so total stays ~4s
        speech_so_far = time.monotonic() - self._recording_started_at
        if speech_so_far <= float(SHORT_UTTERANCE_MAX_SEC):
            return min(float(SHORT_UTTERANCE_SILENCE_SEC), float(CORE_ANSWER_SOFT_SILENCE_SEC))
        # Production: soft silence for CORE answers (merge window handles continuation)
        try:
            return max(endpoint, float(CORE_ANSWER_SOFT_SILENCE_SEC))
        except Exception:
            return max(endpoint, CORE_LONG_ANSWER_SILENCE_SEC)

    def _sync_turn_question_index(self) -> None:
        """Drop held turns when the orchestrator advances to a new question."""
        orch = getattr(self.state, "interview_orchestrator", None)
        if orch is None:
            return
        idx = orch.current_index
        if idx == self._turn_q_index:
            return
        if self._pending_audio is not None:
            logger.info(
                "[TURN DISCARD] Q%d→Q%d — dropping held turn %r",
                max(self._turn_q_index, 0) + 1,
                idx + 1,
                (self._pending_text or "")[:60],
            )
            self._clear_pending_turn()
        self._turn_q_index = idx

    def _current_q_label(self) -> str:
        orch = getattr(self.state, "interview_orchestrator", None)
        if orch is None:
            return "?"
        return str(orch.current_index + 1)

    def _substantive_answer_in_progress(self) -> bool:
        """True when a long CORE answer is actively being captured or checked."""
        if self._core_answer_in_progress():
            return True
        if self.is_recording and self._in_core_phase():
            if self._recording_started_at:
                speech_sec = time.monotonic() - self._recording_started_at
                if speech_sec >= 8.0:
                    return True
        orch = getattr(self.state, "interview_orchestrator", None)
        if orch is not None and orch.has_active_answer_progress():
            return True
        return False

    def _cancel_flush_timer(self) -> None:
        with self._flush_lock:
            t = self._flush_timer
            self._flush_timer = None
        if t is not None:
            try:
                t.cancel()
            except Exception:
                pass

    def _schedule_flush_timer(self, delay_sec: float) -> None:
        """Wake flush when merge window expires — even if candidate stays silent."""
        self._cancel_flush_timer()
        wait = max(0.05, float(delay_sec))

        def _on_fire() -> None:
            try:
                with self._flush_lock:
                    self._flush_timer = None
                if self._pending_audio is None:
                    return
                if time.monotonic() < self._pending_until:
                    # Extended (e.g. defer) — reschedule remainder
                    remain = self._pending_until - time.monotonic()
                    if remain > 0.05:
                        self._schedule_flush_timer(remain)
                        return
                logger.info(
                    "[TURN FLUSH TIMER] Q%s firing after silence — committing held turn",
                    self._current_q_label(),
                )
                self._discard_expired_pending(force=True)
            except Exception as ex:
                logger.warning("[TURN FLUSH TIMER] failed: %s", ex)

        timer = threading.Timer(wait, _on_fire)
        timer.daemon = True
        with self._flush_lock:
            self._flush_timer = timer
        timer.start()

    def _defer_pending_flush(self, pending_text: str, pending_sec: float, reason: str) -> None:
        logger.warning(
            "[TURN DEFER] Q%s %s — active answer in progress (audio=%.1fs chars=%d text=%r)",
            self._current_q_label(),
            reason,
            pending_sec,
            len(pending_text),
            pending_text[:60],
        )
        self._pending_until = time.monotonic() + TURN_FLUSH_DEFER_SEC
        self._schedule_flush_timer(TURN_FLUSH_DEFER_SEC)

    def _clear_pending_turn(self) -> None:
        self._cancel_flush_timer()
        self._pending_audio = None
        self._pending_text = ""
        self._pending_until = 0.0
        self._pending_sarvam_failed = False
        self._pending_core_deadline = 0.0

    def _should_flush_held_core_turn(self, text: str, audio_sec: float) -> bool:
        stripped = (text or "").strip()
        if not stripped:
            return False
        if self._contains_answer_done_marker(stripped):
            return True
        if len(stripped) >= TURN_MERGE_MIN_CHARS:
            return True
        if audio_sec >= CORE_LONG_ANSWER_SPEECH_SEC and len(stripped) >= 40:
            return True
        return False

    def _should_flush_held_turn(self, text: str, audio_sec: float) -> bool:
        """Commit held text on expiry instead of silently dropping substantive answers."""
        stripped = (text or "").strip()
        if not stripped:
            return False
        if should_commit_short_turn_immediately(stripped):
            return True
        if len(stripped) >= TURN_MERGE_MIN_CHARS:
            return True
        if audio_sec >= TURN_MERGE_MIN_AUDIO_SEC and len(stripped) >= 3:
            return True
        return False

    def _discard_expired_pending(self, force: bool = False) -> None:
        with self._pending_commit_lock:
            self._discard_expired_pending_locked(force=force)

    def _discard_expired_pending_locked(self, force: bool = False) -> None:
        if self._pending_audio is None:
            return
        if not force and time.monotonic() < self._pending_until:
            return
        pending_text = (self._pending_text or "").strip()
        pending_sec = len(self._pending_audio) / SAMPLE_RATE
        if self._in_await_intro_phase():
            should_flush = self._should_flush_held_intro_turn(pending_text, pending_sec)
        elif self._pending_core_deadline > 0:
            should_flush = self._should_flush_held_core_turn(pending_text, pending_sec)
        else:
            should_flush = self._should_flush_held_turn(pending_text, pending_sec)

        # Production hard-end: after merge window, always commit substantive CORE holds
        if (
            force
            and self._in_core_phase()
            and pending_text
            and len(pending_text) >= 12
        ):
            should_flush = True

        if should_flush and self._substantive_answer_in_progress():
            if len(pending_text) < TURN_FLUSH_GUARD_MIN_CHARS:
                self._defer_pending_flush(
                    pending_text, pending_sec, "tiny held turn during long answer"
                )
                return

        if should_flush:
            logger.info(
                "[TURN FLUSH] Q%s merge window expired — committing held turn "
                "(audio=%.1fs chars=%d): %r",
                self._current_q_label(),
                pending_sec,
                len(pending_text),
                pending_text[:80],
            )
            self._commit_turn(pending_text)
        else:
            logger.warning(
                "[TURN DISCARD] Q%s merge window expired — dropping held turn "
                "(audio=%.1fs chars=%d text=%r)",
                self._current_q_label(),
                pending_sec,
                len(pending_text),
                pending_text[:80] if pending_text else "",
            )
        self._clear_pending_turn()

    def _should_hold_turn(
        self,
        text: str,
        utterance_duration: float,
        sarvam_failed: bool,
    ) -> Tuple[bool, str]:
        if not TURN_MERGE_ENABLED:
            return False, ""
        if self._in_await_intro_phase():
            return self._should_hold_intro_turn(text, utterance_duration)
        if not self._in_core_phase():
            return False, ""
        if self._orch_awaiting_clarifier():
            return False, ""

        stripped = (text or "").strip()
        if should_commit_short_turn_immediately(stripped):
            return False, ""

        # Done phrase → hard end immediately (no merge hold)
        if self._contains_answer_done_marker(stripped):
            return False, ""

        if self._in_core_phase() and self._core_answer_in_progress():
            if (
                self._pending_core_deadline > 0
                and time.monotonic() >= self._pending_core_deadline
            ):
                logger.info(
                    "[TURN FLUSH] core answer max hold reached — committing chars=%d",
                    len(stripped),
                )
                return False, ""
            # Incomplete / mid-thought → always hold (do not advance to next Q)
            if detect_incomplete_answer(stripped):
                return True, "core_answer_in_progress"
            # Live path: complete answers commit after soft silence (keep ~2.5s latency)
            if self._stream_stt_enabled():
                words = len(stripped.split())
                if words >= max(MIN_ANSWER_WORDS * 2, 16) or self._contains_answer_done_marker(stripped):
                    return False, ""
            # Soft end → brief hold so a short pause can resume into same answer
            return True, "core_answer_in_progress"

        # First soft-ended CORE utterance
        if self._in_core_phase() and stripped:
            # Incomplete mid-thought → merge hold (prevents Q2 cut → Q3 jump)
            if detect_incomplete_answer(stripped):
                return True, "core_answer_in_progress"
            words = len(stripped.split())
            if len(stripped) >= TURN_MERGE_MIN_CHARS or words >= MIN_ANSWER_WORDS:
                # Live STT: only skip merge when answer looks finished enough
                if self._stream_stt_enabled():
                    if words >= max(MIN_ANSWER_WORDS * 2, 16) or self._contains_answer_done_marker(stripped):
                        return False, ""
                    return True, "core_answer_in_progress"
                return True, "core_answer_in_progress"

        if stripped and len(stripped) >= TURN_MERGE_MIN_CHARS and not sarvam_failed:
            return False, ""

        if not stripped:
            if utterance_duration < TURN_MERGE_MIN_HOLD_SEC:
                return False, ""
            return True, "empty_transcript"
        if (
            utterance_duration >= TURN_MERGE_MIN_AUDIO_SEC
            and len(stripped) < TURN_MERGE_MIN_CHARS
            and utterance_duration >= TURN_MERGE_MAX_SHORT_HOLD_SEC
        ):
            return True, "short_text_long_audio"
        if sarvam_failed and len(stripped) < SARVAM_QUALITY_MIN_CHARS:
            if utterance_duration >= TURN_MERGE_MAX_SHORT_HOLD_SEC:
                return True, "sarvam_fail_whisper_short"
        return False, ""

    def _normalize_candidate_name(self, text: str) -> str:
        if not NAME_NORMALIZE_ENABLED or not text:
            return text
        orch = getattr(self.state, "interview_orchestrator", None)
        canonical = getattr(orch, "candidate_name", "") if orch else ""
        if not canonical:
            return text
        return normalize_candidate_name(text, canonical)

    def _commit_turn(self, text: str) -> bool:
        """Normalize and emit a single turn to the LLM queue. Returns True if queued."""
        self._sync_turn_question_index()
        stripped = (text or "").strip()
        if not stripped or len(stripped) <= 2:
            logger.debug("[TURN SKIP] reason=too_short len=%d", len(stripped))
            return False
        if getattr(self.state, "interview_ended", None) and self.state.interview_ended.is_set():
            logger.debug("[TURN SKIP] reason=interview_ended")
            return False
        orch = getattr(self.state, "interview_orchestrator", None)
        if orch is not None and orch.is_stale_previous_question_tail(stripped):
            logger.info(
                "[TURN SKIP] stale tail from previous question Q%d text=%r",
                orch.current_index + 1,
                stripped[:80],
            )
            return False
        normalized = self._normalize_candidate_name(stripped)
        hook = getattr(self.state, "on_candidate_speech", None)
        if callable(hook):
            try:
                hook()
            except Exception:
                self.state.last_candidate_speech_at = time.monotonic()
                self.state.pending_presence_check = False
        else:
            self.state.last_candidate_speech_at = time.monotonic()
            self.state.pending_presence_check = False
        if orch is not None:
            if not orch.awaiting_clarifier_reply:
                orch.mark_answer_turn_committed()
        self.state.llm_queue.put(normalized)
        logger.info(
            "[TURN COMMIT] queued %d chars for LLM/scoring",
            len(normalized),
        )
        return True

    def _clean_transcript_text(self, text: str) -> str:
        cleaned = re.sub(r'\b(um|uh|hmm|ah|uhm)\b[\.\,]?', '', text, flags=re.IGNORECASE)
        return re.sub(r'\s+', ' ', cleaned).strip()

    def _is_backchannel(self, text: str) -> bool:
        lowered = (text or "").strip().lower()
        backchannel_patterns = [
            r'^(yeah|yes|yep|yup|mhm|mmhmm|uh-huh|mm-hmm|right|got it)$',
            r'^(yeah|yes|yep|yup|mhm|mmhmm|uh-huh|mm-hmm|right|got it)[\.!\?]*$',
            r'^(yeah yeah|yes yes)$',
        ]
        return any(re.match(p, lowered) for p in backchannel_patterns)

    def _finalize_transcript_commit(
        self,
        full_text: str,
        utterance_duration: float,
    ) -> None:
        """Filter backchannels and commit a transcribed turn with explicit logging."""
        if not full_text:
            logger.info(
                "[TURN SKIP] reason=empty_transcript duration=%.1fs",
                utterance_duration,
            )
            return

        cleaned = self._clean_transcript_text(full_text)
        if not cleaned:
            logger.info(
                "[TURN SKIP] reason=empty_after_cleanup duration=%.1fs",
                utterance_duration,
            )
            return

        if self._is_backchannel(cleaned):
            logger.info("[TURN SKIP] reason=backchannel text=%r", cleaned)
            print(f"\n[BACKCHANNEL FILTERED]: '{cleaned}' (ignored - not a real turn)")
            return

        self._commit_turn(cleaned)

    def _transcribe_with_fallback(
        self, audio_data: np.ndarray, utterance_duration: float = 0.0
    ) -> Tuple[str, bool]:
        """
        Primary: Sarvam STT. Fallback: Faster Whisper.
        Returns (transcript, sarvam_failed).
        """
        audio_data = audio_data.flatten().astype(np.float32)
        if len(audio_data) < int(SAMPLE_RATE * 0.3):
            return "", False

        full_text = ""
        sarvam_ok = False
        sarvam_attempted = self.sarvam_engine is not None
        stt_timeout = sarvam_transcribe_timeout_sec(utterance_duration)
        collect_deadline = sarvam_collect_deadline_sec(utterance_duration)

        with self._stt_lock:
            if self.sarvam_engine is not None:
                try:
                    logger.debug(
                        "[STT] Sarvam batch audio=%.1fs timeout=%.1fs collect=%.1fs",
                        utterance_duration,
                        stt_timeout,
                        collect_deadline,
                    )
                    result = self.sarvam_engine.transcribe_sync(
                        audio_data,
                        sample_rate=self.actual_samplerate or SAMPLE_RATE,
                        timeout=stt_timeout,
                        collect_deadline=collect_deadline,
                    )
                    if result and result.strip():
                        candidate = result.strip()
                        if (
                            utterance_duration >= SARVAM_QUALITY_MIN_UTTERANCE_SEC
                            and len(candidate) < SARVAM_QUALITY_MIN_CHARS
                        ):
                            print(
                                f"\n[SARVAM STT] Low-confidence short final for {utterance_duration:.1f}s "
                                f"audio ('{candidate}') — trying Whisper fallback",
                                file=sys.stderr,
                            )
                        else:
                            full_text = candidate
                            sarvam_ok = True
                            print(f"\n[SARVAM STT] Transcript: {full_text}")
                    else:
                        print("\n[SARVAM STT] No result — falling back to Whisper", file=sys.stderr)
                except Exception as e:
                    print(f"\n[SARVAM STT Error]: {e} — falling back to Whisper", file=sys.stderr)

            if not sarvam_ok and self._allow_whisper_fallback():
                try:
                    model = self._ensure_whisper()
                    mode = getattr(self.state, "interview_language", "english") or "english"
                    whisper_lang = None if mode == "hinglish" else "en"
                    segments, _ = model.transcribe(
                        audio_data,
                        beam_size=3,
                        language=whisper_lang,
                        condition_on_previous_text=False,
                        vad_filter=False,
                    )
                    for segment in segments:
                        full_text += segment.text.strip() + " "
                    full_text = full_text.strip()
                    if full_text:
                        print(f"\n[WHISPER FALLBACK]: {full_text}")
                except Exception as e:
                    print(f"\n[STT Error]: {e}", file=sys.stderr)
                    return "", sarvam_attempted
            elif not sarvam_ok:
                mode = getattr(self.state, "interview_language", "english") or "english"
                if mode != "english":
                    print(
                        f"\n[STT] Sarvam failed in {mode} mode — Whisper fallback disabled",
                        file=sys.stderr,
                    )
                else:
                    print("\n[STT] Sarvam failed and Whisper fallback is disabled", file=sys.stderr)
                return "", sarvam_attempted

        sarvam_failed = sarvam_attempted and not sarvam_ok
        return full_text.strip(), sarvam_failed

    def _allow_whisper_fallback(self) -> bool:
        if not STT_FALLBACK_ENABLED:
            return False
        mode = getattr(self.state, "interview_language", "english") or "english"
        if mode == "english":
            return True
        from language_profiles import get_profile
        return get_profile(mode).speech.whisper_fallback

    def audio_callback(self, indata, frames, time_info, status):
        """Callback for sounddevice to capture audio streams."""
        if status:
            print(f"Status: {status}", file=sys.stderr)
        data = indata.copy()
        if data.ndim == 2 and data.shape[1] > 1:
            data = data.mean(axis=1, keepdims=True)
        self.state.audio_queue.put(data)

    def feed_external_audio(self, audio_data: np.ndarray):
        """Feed audio from external source (e.g., Recall.ai) instead of microphone."""
        try:
            self.state.audio_queue.put(audio_data, block=False)
        except queue.Full:
            print("[STT] Warning: Audio queue full, dropping chunk", file=sys.stderr)


    def _stream_stt_enabled(self) -> bool:
        return bool(STREAM_STT_ENABLED) and self.sarvam_engine is not None

    def _start_live_stream(self) -> None:
        if not self._stream_stt_enabled():
            self._live_stream_on = False
            return
        try:
            ok = self.sarvam_engine.start_live_utterance_sync()
            self._live_stream_on = bool(ok)
            self._live_stream_pcm_buf = np.empty(0, dtype=np.float32)
            if ok:
                logger.info("[STREAM STT] live utterance started Q%s", self._current_q_label())
            else:
                logger.warning("[STREAM STT] failed to start — will use batch fallback")
        except Exception as ex:
            self._live_stream_on = False
            logger.warning("[STREAM STT] start error: %s", ex)

    def _abort_live_stream(self) -> None:
        if not self._live_stream_on and not (
            self.sarvam_engine is not None and getattr(self.sarvam_engine, "is_live_active", lambda: False)()
        ):
            self._live_stream_pcm_buf = np.empty(0, dtype=np.float32)
            self._live_stream_on = False
            return
        self._live_stream_on = False
        self._live_stream_pcm_buf = np.empty(0, dtype=np.float32)
        try:
            if self.sarvam_engine is not None:
                self.sarvam_engine.abort_live_utterance_sync()
        except Exception:
            pass

    def _feed_live_stream(self, process_block: np.ndarray) -> None:
        if not self._live_stream_on or self.sarvam_engine is None:
            return
        block = process_block.flatten().astype(np.float32)
        self._live_stream_pcm_buf = np.concatenate([self._live_stream_pcm_buf, block])
        while len(self._live_stream_pcm_buf) >= self._live_stream_chunk_samples:
            chunk = self._live_stream_pcm_buf[: self._live_stream_chunk_samples]
            self._live_stream_pcm_buf = self._live_stream_pcm_buf[self._live_stream_chunk_samples :]
            try:
                self.sarvam_engine.stream_audio_sync(chunk, sample_rate=SAMPLE_RATE)
            except Exception:
                break

    def _get_live_partial_text(self) -> str:
        if self.sarvam_engine is None:
            return ""
        try:
            return (self.sarvam_engine.get_live_transcript() or "").strip()
        except Exception:
            return ""

    def _finalize_live_or_batch(
        self, audio_data: np.ndarray, utterance_duration: float
    ) -> tuple:
        """Prefer live transcript; fall back to full batch only if needed."""
        t0 = time.monotonic()
        live_text = ""
        used_live = False
        if self._live_stream_on and self.sarvam_engine is not None:
            # Flush any remaining PCM
            if len(self._live_stream_pcm_buf) > 0:
                try:
                    self.sarvam_engine.stream_audio_sync(
                        self._live_stream_pcm_buf, sample_rate=SAMPLE_RATE
                    )
                except Exception:
                    pass
                self._live_stream_pcm_buf = np.empty(0, dtype=np.float32)
            try:
                live_text = (
                    self.sarvam_engine.finalize_live_utterance_sync(
                        collect_deadline=float(STREAM_STT_FINALIZE_SEC)
                    )
                    or ""
                ).strip()
            except Exception as ex:
                logger.warning("[STREAM STT] finalize error: %s", ex)
                live_text = self._get_live_partial_text()
            self._live_stream_on = False
            used_live = len(live_text) >= int(STREAM_STT_MIN_CHARS)
            logger.info(
                "[STREAM STT] finalize Q%s live_chars=%d used_live=%s finalize_ms=%.0f audio=%.1fs",
                self._current_q_label(),
                len(live_text),
                used_live,
                (time.monotonic() - t0) * 1000,
                utterance_duration,
            )
            if used_live:
                print(f"\n[SARVAM STT LIVE] Transcript: {live_text}")
                return live_text, False

        # Batch fallback (short answers / live failed / stream disabled)
        self._abort_live_stream()
        full_text, sarvam_failed = self._transcribe_with_fallback(
            audio_data, utterance_duration=utterance_duration
        )
        logger.info(
            "[STREAM STT] batch fallback Q%s chars=%d failed=%s total_ms=%.0f audio=%.1fs",
            self._current_q_label(),
            len((full_text or "").strip()),
            sarvam_failed,
            (time.monotonic() - t0) * 1000,
            utterance_duration,
        )
        return full_text, sarvam_failed

    def _transcribe_whisper_only(self, audio_data: np.ndarray) -> str:
        """
        Whisper-only transcription for bot-interrupt partial checks.

        Deliberately does NOT touch the Sarvam WebSocket so the persistent
        connection stays clean for the real final-answer transcription.
        Falls back gracefully if Whisper is unavailable.
        """
        audio_data = audio_data.flatten().astype(np.float32)
        if len(audio_data) < int(SAMPLE_RATE * 0.5):
            return ""
        if not STT_FALLBACK_ENABLED:
            return ""
        try:
            model = self._ensure_whisper()
            mode = getattr(self.state, "interview_language", "english") or "english"
            whisper_lang = None if mode == "hinglish" else "en"
            segments, _ = model.transcribe(
                audio_data,
                beam_size=3,
                language=whisper_lang,
                condition_on_previous_text=False,
                vad_filter=False,
            )
            text = " ".join(s.text.strip() for s in segments).strip()
            return text
        except Exception as e:
            print(f"\n[STT] Whisper partial check error: {e}", file=sys.stderr)
            return ""

    def _maybe_force_answer_time_cap(self) -> bool:
        """Hard-stop recording when answer exceeds ANSWER_MAX_TOTAL_SEC (7 min cap)."""
        if not self.is_recording:
            return False
        orch = getattr(self.state, "interview_orchestrator", None)
        if orch is None:
            return False
        from interview_engine import InterviewPhase
        if orch.phase != InterviewPhase.CORE:
            return False
        speech_sec = orch.get_answer_speech_sec()
        if speech_sec <= 0 and self._recording_started_at > 0:
            speech_sec = time.monotonic() - self._recording_started_at
        if not orch.answer_time_cap_reached(speech_sec):
            return False
        logger.info(
            "[ANSWER CAP] Q%s %.0fs hard cap reached — finalizing utterance",
            self._current_q_label(),
            speech_sec,
        )
        self.transcribe_buffer()
        self.is_recording = False
        self.last_speech_time = 0.0
        self._recording_started_at = 0.0
        return True

    def _maybe_check_bot_interrupt(self):
        """
        Mid-answer progress: scheduled interrupt slots beat background topic polls.
        Uses Whisper exclusively so the Sarvam WebSocket is never disturbed.
        """
        if self._maybe_force_answer_time_cap():
            return
        if not BOT_INTERRUPT_ENABLED:
            return

        orch = getattr(self.state, "interview_orchestrator", None)
        if orch is not None:
            from interview_engine import InterviewPhase
            if orch.phase != InterviewPhase.CORE:
                return

        if not self.is_recording or not self.audio_buffer:
            return
        if self.state.is_ai_speaking.is_set():
            return
        if orch is not None:
            ok, _reason = orch.can_run_progress_gate(is_ai_speaking=False)
            if not ok:
                return
        if self._orch_awaiting_clarifier():
            return
        if time.monotonic() < self._bot_interrupt_cooldown_until:
            return

        speech_sec = orch.get_answer_speech_sec() if orch else 0.0
        if speech_sec <= 0 and self._recording_started_at > 0:
            speech_sec = time.monotonic() - self._recording_started_at

        schedule = orch.resolve_progress_check(speech_sec) if orch else None
        if schedule is None:
            return

        audio_data = np.concatenate(self.audio_buffer).flatten().astype(np.float32)
        partial_sec = len(audio_data) / SAMPLE_RATE
        if partial_sec < BOT_INTERRUPT_MIN_PARTIAL_SEC:
            return

        self._last_bot_interrupt_check = time.monotonic()

        # Prefer live Sarvam transcript (keeps topic tracking without Whisper rebatch)
        live_partial = self._get_live_partial_text()
        if len(live_partial) >= 12:
            full_partial = live_partial
            window_text = live_partial[-400:].strip()
            recent_segment = full_partial[len(self._prev_check_partial):].strip()
            if not recent_segment:
                recent_segment = window_text
            self._prev_check_partial = full_partial
        else:
            full_partial = self._transcribe_whisper_only(audio_data)
            if len(full_partial) < 12:
                return
            if schedule.kind == "poll":
                window_sec = float(ANSWER_TOPIC_POLL_WINDOW_SEC)
            else:
                window_sec = float(ANSWER_DEPTH_CHECK_WINDOW_SEC)
            window_samples = max(int(window_sec * SAMPLE_RATE), 512)
            if len(audio_data) > window_samples:
                window_audio = audio_data[-window_samples:]
            else:
                window_audio = audio_data
            window_text = self._transcribe_whisper_only(window_audio).strip()
            if not window_text:
                window_text = full_partial[-400:].strip()
            recent_segment = full_partial[len(self._prev_check_partial):].strip()
            if not recent_segment:
                recent_segment = window_text
            self._prev_check_partial = full_partial
        self._check_num += 1

        if schedule.kind == "slot":
            orch.mark_timed_check_done(schedule.slot, speech_sec)
        else:
            orch.mark_topic_poll_done(schedule.poll_index)

        from interview_engine import ProgressCheckPayload
        payload = ProgressCheckPayload(
            full_partial=full_partial,
            recent_segment=recent_segment,
            speech_sec=speech_sec,
            check_num=self._check_num,
            check_kind=schedule.kind,
            check_slot=schedule.slot if schedule.kind == "slot" else 0,
            poll_index=schedule.poll_index if schedule.kind == "poll" else 0,
            window_text=window_text,
        )

        print(
            f"\n[PROGRESS CHECK #{self._check_num}] kind={schedule.kind} "
            f"slot={schedule.slot} poll={schedule.poll_index} {speech_sec:.0f}s | "
            f"recent={recent_segment[:60]!r}"
        )
        try:
            self.state.bot_interrupt_queue.put_nowait(payload)
            self._bot_interrupt_cooldown_until = (
                time.monotonic() + MID_ANSWER_BOT_COOLDOWN_SEC
            )
        except queue.Full:
            pass

    def process_audio(self):
        """Worker thread: VAD → accumulate → transcribe."""
        print("\n--- READY: START SPEAKING ---")

        vad_accumulator = np.empty(0, dtype=np.float32)
        pre_speech_buffer = collections.deque(maxlen=15)

        while self.state.is_running:
            try:
                if self.state.clear_stt_buffer.is_set():
                    self._reset_recording_state()
                    vad_accumulator = np.empty(0, dtype=np.float32)
                    pre_speech_buffer.clear()
                    self.state.clear_stt_buffer.clear()
                    self.vad_model.reset_states()

                chunk = self.state.audio_queue.get(timeout=1.0)
                chunk = chunk.flatten().astype(np.float32)

                if self.state.is_ai_speaking.is_set():
                    # Bot is speaking — discard mic audio (no user barge-in by default)
                    if USER_BARGE_IN_ENABLED and len(chunk) > 0:
                        vad_chunk = chunk
                        if self.actual_samplerate != SAMPLE_RATE:
                            import scipy.signal
                            num_samples = int(len(chunk) * SAMPLE_RATE / self.actual_samplerate)
                            vad_chunk = scipy.signal.resample(chunk, num_samples)

                        if len(vad_chunk) >= 512:
                            tensor_chunk = torch.from_numpy(vad_chunk[:512]).to(DEVICE)
                            tensor_chunk = tensor_chunk.unsqueeze(0)
                            with torch.no_grad():
                                speech_prob = self.vad_model(tensor_chunk, SAMPLE_RATE).item()

                            if speech_prob > 0.7:
                                self.state.interrupt_flag.set()
                            elif speech_prob >= 0.5:
                                self.candidate_speaking_duration += (len(chunk) / self.actual_samplerate)
                                if self.candidate_speaking_duration >= self.interruption_threshold:
                                    print(f"\n[INTERRUPTION DETECTED] Candidate spoke for "
                                          f"{self.candidate_speaking_duration:.1f}s - Stopping AI")
                                    self.state.interrupt_flag.set()
                                    self.state.is_ai_speaking.clear()
                                    self.candidate_speaking_duration = 0.0
                                    continue
                            else:
                                self.candidate_speaking_duration = max(
                                    0, self.candidate_speaking_duration - 0.1
                                )

                    self.candidate_speaking_duration = 0.0
                    self._reset_recording_state()
                    vad_accumulator = np.empty(0, dtype=np.float32)
                    pre_speech_buffer.clear()
                    continue

                self.candidate_speaking_duration = 0.0

                if not self.state.is_started.is_set():
                    self._reset_recording_state()
                    vad_accumulator = np.empty(0, dtype=np.float32)
                    pre_speech_buffer.clear()
                    continue

                if self.actual_samplerate != SAMPLE_RATE:
                    import scipy.signal
                    num_samples = int(len(chunk) * SAMPLE_RATE / self.actual_samplerate)
                    vad_chunk = scipy.signal.resample(chunk, num_samples)
                else:
                    vad_chunk = chunk

                vad_accumulator = np.concatenate((vad_accumulator, vad_chunk))

                while len(vad_accumulator) >= 512:
                    process_block = vad_accumulator[:512]
                    vad_accumulator = vad_accumulator[512:]

                    tensor_chunk = torch.from_numpy(process_block).to(DEVICE)
                    tensor_chunk = tensor_chunk.unsqueeze(0)
                    with torch.no_grad():
                        speech_prob = self.vad_model(tensor_chunk, SAMPLE_RATE).item()

                    if speech_prob >= 0.5:
                        if not self.is_recording:
                            print("\rListening...        ", end="", flush=True)
                            self.is_recording = True
                            self.state.candidate_recording = True
                            self._recording_started_at = time.monotonic()
                            self._last_bot_interrupt_check = time.monotonic()
                            # Reset cooldown so each new answer gets a clean interrupt window
                            self._bot_interrupt_cooldown_until = 0.0
                            started_hook = getattr(
                                self.state, "on_candidate_speech_started", None
                            )
                            if callable(started_hook):
                                try:
                                    started_hook()
                                except Exception:
                                    pass
                            self._start_live_stream()
                            for pre_block in pre_speech_buffer:
                                self.audio_buffer.append(pre_block)
                                self._feed_live_stream(pre_block)
                            pre_speech_buffer.clear()
                        self.audio_buffer.append(process_block)
                        self._feed_live_stream(process_block)
                        self.last_speech_time = 0.0
                        self._maybe_check_bot_interrupt()
                    else:
                        if self.is_recording:
                            self.last_speech_time += (512 / SAMPLE_RATE)
                            endpoint = self._active_endpoint_silence_for_recording()
                            if self.last_speech_time >= endpoint:
                                self.transcribe_buffer()
                                self.is_recording = False
                                self.last_speech_time = 0.0
                                self._recording_started_at = 0.0
                            else:
                                self.audio_buffer.append(process_block)
                                self._feed_live_stream(process_block)
                                self._maybe_check_bot_interrupt()
                        else:
                            pre_speech_buffer.append(process_block)

            except queue.Empty:
                # Idle mic: still flush held turns when merge window expires
                if self._pending_audio is not None and time.monotonic() >= self._pending_until:
                    self._discard_expired_pending(force=True)
                continue

    def transcribe_buffer(self):
        """
        Transcribe the accumulated audio buffer.

        Primary:  Sarvam AI Saaras V3 (batch per utterance)
        Fallback: faster-whisper (lazy-loaded)
        """
        if not self.audio_buffer:
            return

        self._sync_turn_question_index()

        if not self.state.is_started.is_set():
            self._reset_recording_state()
            return

        if self.state.is_ai_speaking.is_set():
            self._reset_recording_state()
            return

        recall_age = time.monotonic() - self.state.last_recall_transcript_time
        if recall_age < 4.0:
            print(
                f"\r[STT] Recall.ai handled this utterance "
                f"({recall_age:.2f}s ago) — skipping local transcription",
                end="", flush=True,
            )
            self._abort_live_stream()
            self.audio_buffer = []
            self.vad_model.reset_states()
            return

        audio_data = np.concatenate(self.audio_buffer).flatten().astype(np.float32)
        segment_duration = len(audio_data) / SAMPLE_RATE

        # Merge with held partial — prefer text merge (never rebatch full combined audio)
        merged_pending_text = ""
        self._discard_expired_pending()
        with self._pending_commit_lock:
            if self._pending_audio is not None and time.monotonic() < self._pending_until:
                pending_sec = len(self._pending_audio) / SAMPLE_RATE
                merged_pending_text = (self._pending_text or "").strip()
                print(
                    f"\n[TURN MERGE] combining held text ({len(merged_pending_text)} chars, "
                    f"{pending_sec:.1f}s) + new segment {segment_duration:.1f}s",
                    file=sys.stderr,
                )
                # Keep audio concat only for duration stats / whisper fallback
                audio_data = np.concatenate([self._pending_audio, audio_data]).astype(np.float32)
                self._clear_pending_turn()

        utterance_duration = len(audio_data) / SAMPLE_RATE
        self.recent_utterance_lengths.append(utterance_duration)
        if len(self.recent_utterance_lengths) > 10:
            self.recent_utterance_lengths.pop(0)
        if len(self.recent_utterance_lengths) >= 3:
            avg_duration = sum(self.recent_utterance_lengths) / len(self.recent_utterance_lengths)
            if self.sarvam_engine is not None:
                if avg_duration < 2.0:
                    self.adaptive_silence_duration = max(
                        self._active_endpoint_silence - 0.2, 0.8
                    )
                else:
                    # Do not stretch silence for long answers — keeps turn-end latency stable.
                    self.adaptive_silence_duration = self._active_endpoint_silence
            else:
                # Preserve Whisper behavior for fallback-only mode.
                if avg_duration < 2.0:
                    self.adaptive_silence_duration = 0.8
                elif avg_duration > 5.0:
                    self.adaptive_silence_duration = 1.5
                else:
                    self.adaptive_silence_duration = self._active_endpoint_silence

        self.audio_buffer = []
        self.vad_model.reset_states()

        # Finalize only the NEW live segment (not the full merged audio)
        new_text, sarvam_failed = self._finalize_live_or_batch(
            audio_data[-int(segment_duration * SAMPLE_RATE):]
            if merged_pending_text and utterance_duration > segment_duration
            else audio_data,
            utterance_duration=segment_duration,
        )
        if merged_pending_text:
            full_text = f"{merged_pending_text} {(new_text or '').strip()}".strip()
            logger.info(
                "[TURN MERGE TEXT] Q%s pending_chars=%d new_chars=%d total=%d",
                self._current_q_label(),
                len(merged_pending_text),
                len((new_text or "").strip()),
                len(full_text),
            )
        else:
            full_text = new_text

        if self.state.is_ai_speaking.is_set():
            logger.info(
                "[TURN DISCARD] Q%s bot speaking during transcription — dropping utterance",
                self._current_q_label(),
            )
            self._abort_live_stream()
            return

        should_hold, hold_reason = self._should_hold_turn(
            full_text, utterance_duration, sarvam_failed
        )
        if should_hold:
            logger.info(
                "[TURN HOLD] reason=%s duration=%.1fs chars=%d text=%r",
                hold_reason,
                utterance_duration,
                len((full_text or "").strip()),
                (full_text or "")[:80],
            )
            self._pending_audio = audio_data.copy()
            new_text = (full_text or "").strip()
            if self._pending_text and new_text:
                self._pending_text = f"{self._pending_text} {new_text}".strip()
            elif new_text:
                self._pending_text = new_text
            merge_sec = self._merge_window_sec(hold_reason, text=new_text)
            self._pending_until = time.monotonic() + merge_sec
            self._pending_sarvam_failed = sarvam_failed
            if hold_reason == "core_answer_in_progress" and self._pending_core_deadline <= 0:
                self._pending_core_deadline = (
                    time.monotonic() + CORE_ANSWER_MAX_HOLD_SEC
                )
            # Critical: flush on timer even if candidate stays silent (no new audio)
            self._schedule_flush_timer(merge_sec)
            return

        self._finalize_transcript_commit(full_text, utterance_duration)
