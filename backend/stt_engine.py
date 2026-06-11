import sys
import queue
import re
import time
import torch
import numpy as np
import collections
from faster_whisper import WhisperModel

from config import MODEL_SIZE, DEVICE, COMPUTE_TYPE, SAMPLE_RATE, CHANNELS, SILENCE_DURATION
from state import AgentState


class STTEngine:
    def __init__(self, state: AgentState, sarvam_engine=None):
        """
        Args:
            state:         Shared AgentState
            sarvam_engine: Optional SarvamSTTEngine — primary transcription engine.
                           When provided, Sarvam Saaras V3 is tried first and Whisper
                           is the automatic fallback.
                           When None (main.py standalone mode), only Whisper is used.
        """
        self.state = state
        self.sarvam_engine = sarvam_engine   # None → Whisper-only (main.py)
        self.audio_buffer = []
        self.last_speech_time = 0.0
        self.is_recording = False
        self.actual_samplerate = SAMPLE_RATE
        self.actual_channels = CHANNELS

        # Adaptive endpointing
        self.base_silence_duration = SILENCE_DURATION
        self.adaptive_silence_duration = SILENCE_DURATION
        self.recent_utterance_lengths = []

        # SMART INTERRUPTION: Track how long candidate speaks while AI is speaking
        self.candidate_speaking_duration = 0.0
        self.interruption_threshold = 3.0  # seconds of continuous speech to interrupt AI

        print(f"Loading Whisper model '{MODEL_SIZE}' on {DEVICE}...")
        self.model = WhisperModel(MODEL_SIZE, device=DEVICE, compute_type=COMPUTE_TYPE)

        print(f"Loading Silero VAD on {DEVICE}...")
        self.vad_model, _ = torch.hub.load(
            repo_or_dir='snakers4/silero-vad',
            model='silero_vad',
            force_reload=False
        )
        self.vad_model.to(DEVICE)

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

    def process_audio(self):
        """Worker thread: VAD → accumulate → transcribe."""
        print("\n--- READY: START SPEAKING ---")

        vad_accumulator = np.empty(0, dtype=np.float32)
        pre_speech_buffer = collections.deque(maxlen=15)

        while self.state.is_running:
            try:
                chunk = self.state.audio_queue.get(timeout=1.0)
                chunk = chunk.flatten().astype(np.float32)

                # SMART INTERRUPTION: Allow candidate to interrupt if speaking long enough
                if self.state.is_ai_speaking.is_set():
                    if len(chunk) > 0:
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

                        if self.state.is_ai_speaking.is_set() and not self.state.interrupt_flag.is_set():
                            self.audio_buffer = []
                            self.is_recording = False
                            self.last_speech_time = 0.0
                            vad_accumulator = np.empty(0, dtype=np.float32)
                            pre_speech_buffer.clear()
                            continue
                    else:
                        self.candidate_speaking_duration = 0.0
                        self.audio_buffer = []
                        self.is_recording = False
                        continue
                else:
                    self.candidate_speaking_duration = 0.0

                if not self.state.is_started.is_set():
                    self.audio_buffer = []
                    self.is_recording = False
                    self.last_speech_time = 0.0
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
                            self.audio_buffer.extend(list(pre_speech_buffer))
                            pre_speech_buffer.clear()
                        self.audio_buffer.append(process_block)
                        self.last_speech_time = 0.0
                    else:
                        if self.is_recording:
                            self.last_speech_time += (512 / SAMPLE_RATE)
                            if self.last_speech_time >= self.adaptive_silence_duration:
                                self.transcribe_buffer()
                                self.is_recording = False
                                self.last_speech_time = 0.0
                            else:
                                self.audio_buffer.append(process_block)
                        else:
                            pre_speech_buffer.append(process_block)

            except queue.Empty:
                continue

    def transcribe_buffer(self):
        """
        Transcribe the accumulated audio buffer.

        Primary:  Sarvam AI Saaras V3  (api_server / Recall mode — sarvam_engine is set)
        Fallback: faster-whisper        (always available; sole engine in main.py mode)

        Deduplication: if Recall.ai already fired a final transcript for this
        utterance (state.last_recall_transcript_time was set within the last 4 s)
        we skip local transcription entirely — the LLM queue already has the text.
        """
        if not self.audio_buffer:
            return

        if not self.state.is_started.is_set():
            self.audio_buffer = []
            self.is_recording = False
            self.last_speech_time = 0.0
            return

        if self.state.is_ai_speaking.is_set():
            self.audio_buffer = []
            self.is_recording = False
            self.last_speech_time = 0.0
            return

        # ── Recall.ai deduplication guard ────────────────────────────────────
        # Recall's is_final transcript fires ~200-400 ms after candidate stops.
        # Our VAD silence timer fires 0.8-1.5 s later.  If Recall already sent
        # the transcript to the LLM queue we must NOT run Whisper/Sarvam again.
        # 4 s window is generous — covers the longest silence threshold (1.5 s)
        # plus Whisper processing time (~3 s for long answers).
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

        # Adaptive endpointing: tune silence threshold based on recent answer lengths
        utterance_duration = len(audio_data) / SAMPLE_RATE
        self.recent_utterance_lengths.append(utterance_duration)
        if len(self.recent_utterance_lengths) > 10:
            self.recent_utterance_lengths.pop(0)
        if len(self.recent_utterance_lengths) >= 3:
            avg_duration = sum(self.recent_utterance_lengths) / len(self.recent_utterance_lengths)
            if avg_duration < 2.0:
                self.adaptive_silence_duration = 0.8
            elif avg_duration > 5.0:
                self.adaptive_silence_duration = 1.5
            else:
                self.adaptive_silence_duration = 1.0

        self.audio_buffer = []
        self.vad_model.reset_states()

        # ── Primary: Sarvam Saaras V3 ─────────────────────────────────────────
        full_text = ""
        sarvam_ok = False

        if self.sarvam_engine is not None:
            try:
                result = self.sarvam_engine.transcribe_sync(
                    audio_data,
                    sample_rate=self.actual_samplerate or SAMPLE_RATE,
                )
                if result and result.strip():
                    full_text = result.strip()
                    sarvam_ok = True
                    print(f"\n[SARVAM STT] Transcript: {full_text}")
                else:
                    print("\n[SARVAM STT] No result — falling back to Whisper", file=sys.stderr)
            except Exception as e:
                print(f"\n[SARVAM STT Error]: {e} — falling back to Whisper", file=sys.stderr)

        # ── Fallback: faster-whisper ──────────────────────────────────────────
        if not sarvam_ok:
            try:
                segments, _ = self.model.transcribe(
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
                    print(f"\n[TRANSCRIPTION]: {full_text}")
            except Exception as e:
                try:
                    self.state.tts_queue.put("Sorry, I couldn't understand that. Please try again.")
                    self.state.tts_queue.put("<END_OF_TURN>")
                except Exception:
                    pass
                print(f"\n[STT Error]: {e}", file=sys.stderr)
                return

        # ── Post-processing: filler removal + backchannel filter ──────────────
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

        if len(full_text) > 2:
            self.state.llm_queue.put(full_text)
