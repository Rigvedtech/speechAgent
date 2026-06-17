import sys
import queue
import re
import time
import threading
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
    BOT_INTERRUPT_MIN_SPEECH_SEC,
    BOT_INTERRUPT_CHECK_INTERVAL_SEC,
    BOT_INTERRUPT_MIN_PARTIAL_SEC,
    SARVAM_LOCAL_SILENCE_SEC,
    WHISPER_LOCAL_SILENCE_SEC,
    SARVAM_QUALITY_MIN_UTTERANCE_SEC,
    SARVAM_QUALITY_MIN_CHARS,
    TURN_MERGE_ENABLED,
    TURN_MERGE_WINDOW_SEC,
    TURN_MERGE_MIN_AUDIO_SEC,
    TURN_MERGE_MIN_CHARS,
    NAME_NORMALIZE_ENABLED,
)
from state import AgentState
from transcript_utils import normalize_candidate_name


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

        # Lazy Whisper — only loaded when Sarvam fails (or no Sarvam configured)
        self._whisper_model = None
        self._whisper_lock = threading.Lock()
        self._stt_lock = threading.Lock()

        # Turn commit / merge guard (hold suspicious partials, merge within window)
        self._pending_audio: Optional[np.ndarray] = None
        self._pending_text: str = ""
        self._pending_until: float = 0.0
        self._pending_sarvam_failed: bool = False

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
        self.audio_buffer = []
        self.is_recording = False
        self.last_speech_time = 0.0
        self._recording_started_at = 0.0
        self._last_bot_interrupt_check = 0.0

    def _orch_awaiting_clarifier(self) -> bool:
        orch = getattr(self.state, "interview_orchestrator", None)
        return bool(orch and getattr(orch, "awaiting_clarifier_reply", False))

    def _in_core_phase(self) -> bool:
        orch = getattr(self.state, "interview_orchestrator", None)
        if orch is None:
            return False
        from interview_engine import InterviewPhase
        return orch.phase == InterviewPhase.CORE

    def _clear_pending_turn(self) -> None:
        self._pending_audio = None
        self._pending_text = ""
        self._pending_until = 0.0
        self._pending_sarvam_failed = False

    def _discard_expired_pending(self) -> None:
        if self._pending_audio is not None and time.monotonic() >= self._pending_until:
            print(
                f"\n[TURN DISCARD] merge window expired "
                f"(had {len(self._pending_audio) / SAMPLE_RATE:.1f}s audio, "
                f"text={self._pending_text!r})",
                file=sys.stderr,
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
        if not self._in_core_phase():
            return False, ""
        if self._orch_awaiting_clarifier():
            return False, ""

        stripped = (text or "").strip()
        if not stripped:
            return True, "empty_transcript"
        if (
            utterance_duration >= TURN_MERGE_MIN_AUDIO_SEC
            and len(stripped) < TURN_MERGE_MIN_CHARS
        ):
            return True, "short_text_long_audio"
        if sarvam_failed and len(stripped) < SARVAM_QUALITY_MIN_CHARS:
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

    def _commit_turn(self, text: str) -> None:
        """Normalize and emit a single turn to the LLM queue."""
        if not text or len(text) <= 2:
            return
        if getattr(self.state, "interview_ended", None) and self.state.interview_ended.is_set():
            return
        normalized = self._normalize_candidate_name(text)
        self.state.llm_queue.put(normalized)

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

        with self._stt_lock:
            if self.sarvam_engine is not None:
                try:
                    result = self.sarvam_engine.transcribe_sync(
                        audio_data,
                        sample_rate=self.actual_samplerate or SAMPLE_RATE,
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

            if not sarvam_ok and STT_FALLBACK_ENABLED:
                try:
                    model = self._ensure_whisper()
                    segments, _ = model.transcribe(
                        audio_data,
                        beam_size=3,
                        language="en",
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
                print("\n[STT] Sarvam failed and Whisper fallback is disabled", file=sys.stderr)
                return "", sarvam_attempted

        sarvam_failed = sarvam_attempted and not sarvam_ok
        return full_text.strip(), sarvam_failed

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
            segments, _ = model.transcribe(
                audio_data,
                beam_size=3,
                language="en",
                condition_on_previous_text=False,
                vad_filter=False,
            )
            text = " ".join(s.text.strip() for s in segments).strip()
            return text
        except Exception as e:
            print(f"\n[STT] Whisper partial check error: {e}", file=sys.stderr)
            return ""

    def _maybe_check_bot_interrupt(self):
        """
        While user is still speaking, peek at partial audio via Whisper only
        and push to bot_interrupt_queue for LLM clarifier check.

        Rules:
        - Only fires during CORE interview phase (never during intro/greeting).
        - Uses Whisper exclusively so the Sarvam WebSocket is never disturbed —
          this guarantees Sarvam gets clean, uninterrupted audio for the real
          final-answer transcription.
        """
        # Only fire during CORE Q&A phase — never during intro, greeting, closing
        orch = getattr(self.state, "interview_orchestrator", None)
        if orch is not None:
            from interview_engine import InterviewPhase
            if orch.phase != InterviewPhase.CORE:
                return

        if not self.is_recording or not self.audio_buffer:
            return
        if self.state.is_ai_speaking.is_set():
            return
        if time.monotonic() < self._bot_interrupt_cooldown_until:
            return
        if self._orch_awaiting_clarifier():
            return

        speech_sec = time.monotonic() - self._recording_started_at
        if speech_sec < BOT_INTERRUPT_MIN_SPEECH_SEC:
            return
        if time.monotonic() - self._last_bot_interrupt_check < BOT_INTERRUPT_CHECK_INTERVAL_SEC:
            return

        audio_data = np.concatenate(self.audio_buffer).flatten().astype(np.float32)
        partial_sec = len(audio_data) / SAMPLE_RATE
        if partial_sec < BOT_INTERRUPT_MIN_PARTIAL_SEC:
            return

        self._last_bot_interrupt_check = time.monotonic()

        # Use Whisper for partial peek — keeps Sarvam connection untouched
        partial_text = self._transcribe_whisper_only(audio_data)
        if len(partial_text) < 12:
            return

        print(f"\n[STT] Bot-interrupt check (Whisper partial, {partial_sec:.1f}s): {partial_text[:80]}")
        try:
            self.state.bot_interrupt_queue.put_nowait(partial_text)
            self._bot_interrupt_cooldown_until = time.monotonic() + 15.0
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
                            self._recording_started_at = time.monotonic()
                            self._last_bot_interrupt_check = time.monotonic()
                            # Reset cooldown so each new answer gets a clean interrupt window
                            self._bot_interrupt_cooldown_until = 0.0
                            for pre_block in pre_speech_buffer:
                                self.audio_buffer.append(pre_block)
                            pre_speech_buffer.clear()
                        self.audio_buffer.append(process_block)
                        self.last_speech_time = 0.0
                        self._maybe_check_bot_interrupt()
                    else:
                        if self.is_recording:
                            self.last_speech_time += (512 / SAMPLE_RATE)
                            if self.last_speech_time >= self.adaptive_silence_duration:
                                self.transcribe_buffer()
                                self.is_recording = False
                                self.last_speech_time = 0.0
                                self._recording_started_at = 0.0
                            else:
                                self.audio_buffer.append(process_block)
                                self._maybe_check_bot_interrupt()
                        else:
                            pre_speech_buffer.append(process_block)

            except queue.Empty:
                continue

    def transcribe_buffer(self):
        """
        Transcribe the accumulated audio buffer.

        Primary:  Sarvam AI Saaras V3 (batch per utterance)
        Fallback: faster-whisper (lazy-loaded)
        """
        if not self.audio_buffer:
            return

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
            self.audio_buffer = []
            self.vad_model.reset_states()
            return

        audio_data = np.concatenate(self.audio_buffer).flatten().astype(np.float32)

        # Merge with held partial audio if still within the merge window
        self._discard_expired_pending()
        if self._pending_audio is not None and time.monotonic() < self._pending_until:
            pending_sec = len(self._pending_audio) / SAMPLE_RATE
            print(
                f"\n[TURN MERGE] combining {pending_sec:.1f}s held audio + "
                f"{len(audio_data) / SAMPLE_RATE:.1f}s new audio",
                file=sys.stderr,
            )
            audio_data = np.concatenate([self._pending_audio, audio_data]).astype(np.float32)
            self._clear_pending_turn()

        utterance_duration = len(audio_data) / SAMPLE_RATE
        self.recent_utterance_lengths.append(utterance_duration)
        if len(self.recent_utterance_lengths) > 10:
            self.recent_utterance_lengths.pop(0)
        if len(self.recent_utterance_lengths) >= 3:
            avg_duration = sum(self.recent_utterance_lengths) / len(self.recent_utterance_lengths)
            if self.sarvam_engine is not None:
                # Sarvam path favors fuller sentence capture over ultra-fast cutoff.
                if avg_duration < 2.0:
                    self.adaptive_silence_duration = max(self._active_endpoint_silence - 0.2, 1.0)
                elif avg_duration > 5.0:
                    self.adaptive_silence_duration = max(self._active_endpoint_silence + 0.2, 1.4)
                else:
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

        full_text, sarvam_failed = self._transcribe_with_fallback(
            audio_data, utterance_duration=utterance_duration
        )

        # Hold path: store audio for merge even when transcript is empty
        should_hold, hold_reason = self._should_hold_turn(
            full_text, utterance_duration, sarvam_failed
        )
        if should_hold:
            print(
                f"\n[TURN HOLD] reason={hold_reason} duration={utterance_duration:.1f}s "
                f"text={full_text!r}",
                file=sys.stderr,
            )
            self._pending_audio = audio_data.copy()
            self._pending_text = (full_text or "").strip() or self._pending_text
            self._pending_until = time.monotonic() + TURN_MERGE_WINDOW_SEC
            self._pending_sarvam_failed = sarvam_failed
            return

        if not full_text:
            return

        full_text = re.sub(r'\b(um|uh|hmm|ah|uhm)\b[\.\,]?', '', full_text, flags=re.IGNORECASE)
        full_text = re.sub(r'\s+', ' ', full_text).strip()

        if full_text:
            lowered = full_text.lower()
            backchannel_patterns = [
                r'^(yeah|yes|yep|yup|okay|ok|mhm|mmhmm|uh-huh|mm-hmm|right|sure|got it)$',
                r'^(yeah|yes|yep|yup|okay|ok|mhm|mmhmm|uh-huh|mm-hmm|right|sure|got it)[\.!\?]*$',
                r'^(yeah yeah|ok ok|yes yes)$',
            ]
            if any(re.match(p, lowered) for p in backchannel_patterns):
                print(f"\n[BACKCHANNEL FILTERED]: '{full_text}' (ignored - not a real turn)")
                return

        self._commit_turn(full_text)
