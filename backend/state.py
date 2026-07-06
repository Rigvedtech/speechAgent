import queue
import threading
from typing import Optional

class AgentState:
    """Shared state to seamlessly connect separate modules."""
    def __init__(self):
        self.audio_queue = queue.Queue()
        self.llm_queue = queue.Queue()
        # Partial transcripts while user is still speaking — bot clarifier checks
        self.bot_interrupt_queue = queue.Queue()
        # Set by LLM when bot clarifier is spoken — STT clears in-progress buffer
        self.clear_stt_buffer = threading.Event()
        self.tts_queue = queue.Queue()
        # Set by TTS player when an <END_OF_TURN> finishes playback.
        self.tts_turn_done_event = threading.Event()
        
        # Thread-safe event flags (replacing bare bools)
        self.interrupt_flag = threading.Event()
        self.is_ai_speaking = threading.Event()
        self.is_running = True
        # MANUAL START: Interview doesn't begin until /api/start is called
        self.is_started = threading.Event()

        # Timestamp (monotonic seconds) set when Recall.ai fires a final
        # transcript for this session.  stt_engine.transcribe_buffer() checks
        # this to avoid double-sending the same utterance to the LLM queue.
        self.last_recall_transcript_time: float = 0.0
        # Last time candidate speech was committed (monotonic) — silence watcher.
        self.last_candidate_speech_at: float = 0.0
        self.last_playback_done_at: float = 0.0
        self.pending_presence_check: bool = False
        # True while candidate VAD is actively recording an utterance
        self.candidate_recording: bool = False
        # Optional override for next presence-check delay (set after new main question)
        self.presence_check_delay_sec: Optional[float] = None
        # True while bot speaks a mid-answer clarifier or focused rephrase (not a full turn).
        self.mid_answer_interrupt: bool = False
        # Optional hooks set by SessionManager — preserve/restore STT buffer across mid-answer TTS.
        self.on_preserve_stt_buffer = None
        self.on_restore_stt_buffer = None
        # Optional hook set by SessionManager — cancels post-TTS silence watcher.
        self.on_candidate_speech = None
        self.on_candidate_speech_started = None
        self.on_question_advanced = None
        # Last bot utterance kind: main | clarifier | drag | prompt — for interrupt cooldowns
        self.last_bot_speech_kind: str = ""

        # Structured interview orchestrator (set on POST /api/join or legacy /api/start).
        self.interview_orchestrator = None
        self.interview_ended = threading.Event()
        # Resolved at POST /api/start: "english" | "hinglish"
        self.interview_language: str = "english"
