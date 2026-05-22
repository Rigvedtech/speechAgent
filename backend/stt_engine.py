import sys
import queue
import re
import threading
import torch
import numpy as np
import collections

from config import (
    MODEL_SIZE,
    DEVICE,
    COMPUTE_TYPE,
    SAMPLE_RATE,
    CHANNELS,
    SILENCE_DURATION,
    STT_PROVIDER,
    ASSEMBLYAI_API_KEY,
)
from state import AgentState

if STT_PROVIDER == "whisper":
    from faster_whisper import WhisperModel


class STTEngine:
    def __init__(self, state: AgentState):
        self.state = state
        self.audio_buffer = []
        self.last_speech_time = 0.0
        self.is_recording = False
        self.actual_samplerate = SAMPLE_RATE
        self.actual_channels = CHANNELS
        self.model = None
        self._use_assemblyai = STT_PROVIDER == "assemblyai"

        if self._use_assemblyai:
            if not ASSEMBLYAI_API_KEY:
                raise ValueError(
                    "STT_PROVIDER=assemblyai but no API key. Set ASSEMBLYAI_API_KEY or "
                    "AssemblyAI_API_KEY in .env, or set STT_PROVIDER=whisper."
                )
            print("AssemblyAI STT: local Whisper model will not be loaded.")
        else:
            print(f"Loading Whisper model '{MODEL_SIZE}' on {DEVICE}...")
            self.model = WhisperModel(MODEL_SIZE, device=DEVICE, compute_type=COMPUTE_TYPE)

        print(f"Loading Silero VAD on {DEVICE}...")
        self.vad_model, _ = torch.hub.load(
            repo_or_dir="snakers4/silero-vad",
            model="silero_vad",
            force_reload=False,
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

    def process_audio(self):
        """Worker thread to process audio chunks using VAD and transcribe."""
        print("\n--- READY: START SPEAKING ---")

        vad_accumulator = np.empty(0, dtype=np.float32)
        pre_speech_buffer = collections.deque(maxlen=15)

        while self.state.is_running:
            try:
                chunk = self.state.audio_queue.get(timeout=1.0)
                chunk = chunk.flatten().astype(np.float32)

                # Barge-in disabled: drop user audio completely while AI is speaking.
                if self.state.is_ai_speaking:
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

                            if self.last_speech_time >= SILENCE_DURATION:
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
        """Concatenate buffer and transcribe (Whisper or AssemblyAI)."""
        if not self.audio_buffer:
            return
        if self.state.is_ai_speaking:
            self.audio_buffer = []
            self.is_recording = False
            self.last_speech_time = 0.0
            return

        audio_data = np.concatenate(self.audio_buffer).flatten().astype(np.float32)
        self.audio_buffer = []
        self.vad_model.reset_states()

        if self._use_assemblyai:
            self._transcribe_assemblyai(audio_data)
            return

        assert self.model is not None
        try:
            segments, _info = self.model.transcribe(
                audio_data,
                beam_size=3,
                language="en",
                condition_on_previous_text=False,
                vad_filter=False,
            )
        except Exception as e:
            try:
                self.state.tts_queue.put("Sorry, I couldn’t understand that. Please try again.")
                self.state.tts_queue.put("<END_OF_TURN>")
            except Exception:
                pass
            print(f"\n[STT Error]: {e}", file=sys.stderr)
            return

        full_text = ""
        for segment in segments:
            full_text += segment.text.strip() + " "

        self._postprocess_and_enqueue(full_text)

    def _transcribe_assemblyai(self, audio_data: np.ndarray) -> None:
        """Run AssemblyAI in a worker thread so the VAD loop is not blocked by HTTP."""

        def run():
            try:
                from stt_assemblyai import transcribe_float32_mono

                text = transcribe_float32_mono(audio_data, SAMPLE_RATE)
            except Exception as e:
                try:
                    self.state.tts_queue.put(
                        "Sorry, speech recognition failed. Please check your network and API key."
                    )
                    self.state.tts_queue.put("<END_OF_TURN>")
                except Exception:
                    pass
                print(f"\n[STT AssemblyAI Error]: {e}", file=sys.stderr)
                return
            self._postprocess_and_enqueue(text)

        threading.Thread(target=run, daemon=True).start()

    def _postprocess_and_enqueue(self, full_text: str) -> None:
        full_text = (full_text or "").strip()
        full_text = re.sub(r"\b(um|uh|hmm|ah|uhm)\b[\.\,]?", "", full_text, flags=re.IGNORECASE)
        full_text = re.sub(r"\s+", " ", full_text).strip()

        if len(full_text) > 2:
            self.state.llm_queue.put(full_text)
