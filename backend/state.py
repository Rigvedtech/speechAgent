import queue
import threading

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

        # Structured interview orchestrator (set on /api/start).
        self.interview_orchestrator = None
        self.interview_ended = threading.Event()
