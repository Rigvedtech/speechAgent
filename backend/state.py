import queue
import threading

class AgentState:
    """Shared state to seamlessly connect separate modules."""
    def __init__(self):
        self.audio_queue = queue.Queue()
        self.llm_queue = queue.Queue()
        self.tts_queue = queue.Queue()
        # Set by TTS player when an <END_OF_TURN> finishes playback.
        self.tts_turn_done_event = threading.Event()
        
        self.interrupt_flag = False
        self.is_ai_speaking = False
        self.is_running = True
