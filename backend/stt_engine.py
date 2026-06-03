import sys
import queue
import re
import torch
import numpy as np
import collections
from faster_whisper import WhisperModel

from config import MODEL_SIZE, DEVICE, COMPUTE_TYPE, SAMPLE_RATE, CHANNELS, SILENCE_DURATION
from state import AgentState

class STTEngine:
    def __init__(self, state: AgentState):
        self.state = state
        self.audio_buffer = []
        self.last_speech_time = 0.0
        self.is_recording = False
        self.actual_samplerate = SAMPLE_RATE
        self.actual_channels = CHANNELS
        
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
        """
        Feed audio from external source (e.g., Recall.ai) instead of microphone.
        
        Args:
            audio_data: Audio as numpy array (float32, normalized to [-1, 1])
        """
        try:
            self.state.audio_queue.put(audio_data, block=False)
        except queue.Full:
            print("[STT] Warning: Audio queue full, dropping chunk", file=sys.stderr)

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
        """Concatenate buffer and transcribe using Whisper."""
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

        try:
            segments, info = self.model.transcribe(
                audio_data, 
                beam_size=3, 
                language="en",
                condition_on_previous_text=False,
                vad_filter=False 
            )
        except Exception as e:
            # Best-effort: tell the user something instead of silently stalling.
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
            
        full_text = full_text.strip()
        
        full_text = re.sub(r'\b(um|uh|hmm|ah|uhm)\b[\.\,]?', '', full_text, flags=re.IGNORECASE)
        full_text = re.sub(r'\s+', ' ', full_text).strip()
        
        if len(full_text) > 2:
            # Log transcription for monitoring
            print(f"\n[TRANSCRIPTION]: {full_text}")
            self.state.llm_queue.put(full_text)
