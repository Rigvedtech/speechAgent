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
        
        # Adaptive endpointing
        self.base_silence_duration = SILENCE_DURATION
        self.adaptive_silence_duration = SILENCE_DURATION
        self.recent_utterance_lengths = []
        
        # SMART INTERRUPTION: Track how long candidate speaks while AI is speaking
        self.candidate_speaking_duration = 0.0  # Seconds of continuous speech
        self.interruption_threshold = 3.0  # If candidate speaks > 3s, interrupt AI
        
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

                # SMART INTERRUPTION: Allow candidate to interrupt if speaking too long
                if self.state.is_ai_speaking.is_set():
                    # Check if candidate is speaking
                    if len(chunk) > 0:
                        vad_chunk = chunk
                        if self.actual_samplerate != SAMPLE_RATE:
                            import scipy.signal
                            num_samples = int(len(chunk) * SAMPLE_RATE / self.actual_samplerate)
                            vad_chunk = scipy.signal.resample(chunk, num_samples)
                        
                        # Quick VAD check on this chunk
                        if len(vad_chunk) >= 512:
                            tensor_chunk = torch.from_numpy(vad_chunk[:512]).to(DEVICE)
                            tensor_chunk = tensor_chunk.unsqueeze(0)
                            with torch.no_grad():
                                speech_prob = self.vad_model(tensor_chunk, SAMPLE_RATE).item()
                            
                            # High confidence speech - trigger interrupt
                            if speech_prob > 0.7:
                                self.state.interrupt_flag.set()
                                # Continue processing this audio (don't drop it)
                                # Fall through to process as normal speech
                            elif speech_prob >= 0.5:
                                # Medium confidence - accumulate duration
                                self.candidate_speaking_duration += (len(chunk) / self.actual_samplerate)
                                
                                # If candidate speaks > 3 seconds continuously, interrupt AI
                                if self.candidate_speaking_duration >= self.interruption_threshold:
                                    print(f"\n[INTERRUPTION DETECTED] Candidate spoke for {self.candidate_speaking_duration:.1f}s - Stopping AI")
                                    self.state.interrupt_flag.set()
                                    self.state.is_ai_speaking.clear()
                                    self.candidate_speaking_duration = 0.0
                                    # Don't clear buffer - let this speech be processed
                                    continue
                            else:
                                # Silence - reset counter
                                self.candidate_speaking_duration = max(0, self.candidate_speaking_duration - 0.1)
                        
                        # Drop audio if AI still speaking and no strong interrupt detected
                        if self.state.is_ai_speaking.is_set() and not self.state.interrupt_flag.is_set():
                            self.audio_buffer = []
                            self.is_recording = False
                            self.last_speech_time = 0.0
                            vad_accumulator = np.empty(0, dtype=np.float32)
                            pre_speech_buffer.clear()
                            continue
                    else:
                        # Reset interruption counter on silence
                        self.candidate_speaking_duration = 0.0
                        self.audio_buffer = []
                        self.is_recording = False
                        continue
                else:
                    # AI not speaking - reset interruption counter
                    self.candidate_speaking_duration = 0.0
                
                # MANUAL START: Don't process audio until interview is started
                if not self.state.is_started.is_set():
                    self.audio_buffer = []
                    self.is_recording = False
                    continue
                
                # START TRIGGER: Don't process audio until interview starts
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
                            
                            # P1 FIX: Use adaptive silence duration instead of fixed threshold
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
        """Concatenate buffer and transcribe using Whisper."""
        if not self.audio_buffer:
            return
        
        # START TRIGGER: Don't transcribe until interview starts
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

        audio_data = np.concatenate(self.audio_buffer).flatten().astype(np.float32)
        
        # FIX 5: Adaptive endpointing with reduced thresholds (0.8s - 1.5s)
        # Track utterance length to adjust silence threshold dynamically
        utterance_duration = len(audio_data) / SAMPLE_RATE
        self.recent_utterance_lengths.append(utterance_duration)
        
        # Keep only last 10 utterances for adaptive learning
        if len(self.recent_utterance_lengths) > 10:
            self.recent_utterance_lengths.pop(0)
        
        # Adjust silence duration based on speaking pattern:
        # - Short utterances (< 2s): user is giving brief answers → shorter silence (0.8s)
        # - Medium utterances (2-5s): normal conversation → default silence (1.0s)
        # - Long utterances (> 5s): user is elaborating → longer silence (1.5s) to avoid cutoff
        if len(self.recent_utterance_lengths) >= 3:
            avg_duration = sum(self.recent_utterance_lengths) / len(self.recent_utterance_lengths)
            
            if avg_duration < 2.0:
                self.adaptive_silence_duration = 0.8  # Quick back-and-forth (was 1.5s)
            elif avg_duration > 5.0:
                self.adaptive_silence_duration = 1.5  # Long explanations (was 3.0s)
            else:
                self.adaptive_silence_duration = 1.0  # Default (was 2.0s)
        
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
        
        # P1 FIX: Backchannel filtering (research-based turn-taking improvement)
        # Filter out common backchannels ("uh-huh", "yeah", "okay") that don't warrant AI response
        # Based on 2026 production voice AI systems (Krisp.ai, Retell AI)
        
        # First remove filler words as before
        full_text = re.sub(r'\b(um|uh|hmm|ah|uhm)\b[\.\,]?', '', full_text, flags=re.IGNORECASE)
        full_text = re.sub(r'\s+', ' ', full_text).strip()
        
        # Now check if remaining text is just a backchannel
        if full_text:
            lowered = full_text.lower()
            backchannel_patterns = [
                # Single-word backchannels
                r'^(yeah|yes|yep|yup|okay|ok|mhm|mmhmm|uh-huh|mm-hmm|right|sure|got it)$',
                # With punctuation
                r'^(yeah|yes|yep|yup|okay|ok|mhm|mmhmm|uh-huh|mm-hmm|right|sure|got it)[\.!\?]*$',
                # Repeated affirmations
                r'^(yeah yeah|ok ok|yes yes)$',
            ]
            
            is_backchannel = any(re.match(pattern, lowered) for pattern in backchannel_patterns)
            
            if is_backchannel:
                print(f"\n[BACKCHANNEL FILTERED]: '{full_text}' (ignored - not a real turn)")
                return  # Don't send to LLM
        
        if len(full_text) > 2:
            # Log transcription for monitoring
            print(f"\n[TRANSCRIPTION]: {full_text}")
            self.state.llm_queue.put(full_text)
