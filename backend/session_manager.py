"""
Session Manager
Manages multiple concurrent meeting sessions with independent STT/LLM/TTS pipelines.
"""

import logging
import queue
import threading
from typing import Dict, Optional
from dataclasses import dataclass, field
import numpy as np

from state import AgentState
from stt_engine import STTEngine
from llm_brain import LLMBrain
from recall_bot_service import RecallBotService
from audio_sender import AudioSender

logger = logging.getLogger(__name__)


@dataclass
class MeetingSession:
    """
    Represents a single meeting session with its own processing pipeline.
    """
    bot_id: str
    meeting_url: str
    state: AgentState = field(default_factory=AgentState)
    stt_engine: Optional[STTEngine] = None
    llm_brain: Optional[LLMBrain] = None
    audio_sender: Optional[AudioSender] = None
    processing_threads: list = field(default_factory=list)
    is_active: bool = True
    
    def __post_init__(self):
        """Initialize processing components."""
        self.stt_engine = STTEngine(self.state)
        self.llm_brain = LLMBrain(self.state)


class SessionManager:
    """
    Manages multiple concurrent meeting sessions.
    Each session has its own STT, LLM, and TTS pipeline.
    """
    
    def __init__(self, recall_service: RecallBotService):
        """
        Initialize session manager.
        
        Args:
            recall_service: RecallBotService instance for bot management
        """
        self.recall_service = recall_service
        self.sessions: Dict[str, MeetingSession] = {}
        self.sessions_lock = threading.Lock()
    
    def create_session(self, bot_id: str, meeting_url: str) -> MeetingSession:
        """
        Create a new meeting session.
        
        Args:
            bot_id: Bot ID from Recall.ai
            meeting_url: Meeting URL bot joined
            
        Returns:
            MeetingSession instance
        """
        with self.sessions_lock:
            if bot_id in self.sessions:
                logger.warning(f"Session {bot_id} already exists")
                return self.sessions[bot_id]
            
            logger.info(f"Creating session for bot {bot_id}")
            session = MeetingSession(bot_id=bot_id, meeting_url=meeting_url)
            
            # Initialize audio sender
            session.audio_sender = AudioSender(self.recall_service)
            
            # Start processing threads
            self._start_session_threads(session)
            
            self.sessions[bot_id] = session
            logger.info(f"Session {bot_id} created and started")
            
            return session
    
    def _start_session_threads(self, session: MeetingSession):
        """
        Start STT, LLM, and TTS processing threads for a session.
        
        Args:
            session: MeetingSession to start threads for
        """
        # STT processing thread
        stt_thread = threading.Thread(
            target=session.stt_engine.process_audio,
            name=f"STT-{session.bot_id[:8]}",
            daemon=True
        )
        stt_thread.start()
        session.processing_threads.append(stt_thread)
        
        # LLM processing thread
        llm_thread = threading.Thread(
            target=session.llm_brain.start,
            name=f"LLM-{session.bot_id[:8]}",
            daemon=True
        )
        llm_thread.start()
        session.processing_threads.append(llm_thread)
        
        # TTS sender thread
        tts_thread = threading.Thread(
            target=self._tts_worker,
            args=(session,),
            name=f"TTS-{session.bot_id[:8]}",
            daemon=True
        )
        tts_thread.start()
        session.processing_threads.append(tts_thread)
        
        logger.info(f"Started {len(session.processing_threads)} processing threads for {session.bot_id}")
    
    def _tts_worker(self, session: MeetingSession):
        """
        Worker thread to send TTS audio to bot.
        
        Args:
            session: MeetingSession to process TTS for
        """
        logger.info(f"TTS worker started for bot {session.bot_id}")
        
        while session.is_active and session.state.is_running:
            try:
                # Get text from TTS queue (with timeout)
                text = session.state.tts_queue.get(timeout=1.0)
                
                # Check for special markers
                if text == "<END_OF_TURN>":
                    session.state.is_ai_speaking = False
                    logger.debug("AI finished speaking")
                    continue
                
                # Generate and send audio to bot
                session.state.is_ai_speaking = True
                
                if session.audio_sender:
                    success = session.audio_sender.send_text_to_bot_sync(
                        session.bot_id,
                        text
                    )
                    
                    if not success:
                        logger.error(f"Failed to send audio for text: {text[:50]}")
                
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"Error in TTS worker: {e}", exc_info=True)
        
        logger.info(f"TTS worker stopped for bot {session.bot_id}")
    
    def handle_audio_chunk(self, bot_id: str, audio_array: np.ndarray):
        """
        Handle incoming audio chunk from Recall.ai.
        Routes audio to appropriate session's STT engine.
        
        Args:
            bot_id: Bot ID that sent the audio
            audio_array: Audio data as numpy array
        """
        with self.sessions_lock:
            session = self.sessions.get(bot_id)
        
        if not session:
            logger.warning(f"Received audio for unknown bot {bot_id}")
            return
        
        if not session.is_active:
            logger.debug(f"Received audio for inactive session {bot_id}")
            return
        
        # Feed audio to STT engine's queue
        try:
            session.state.audio_queue.put(audio_array, block=False)
        except queue.Full:
            logger.warning(f"Audio queue full for bot {bot_id}, dropping chunk")
    
    def get_session(self, bot_id: str) -> Optional[MeetingSession]:
        """
        Get session by bot ID.
        
        Args:
            bot_id: Bot ID
            
        Returns:
            MeetingSession if exists, None otherwise
        """
        with self.sessions_lock:
            return self.sessions.get(bot_id)
    
    def end_session(self, bot_id: str):
        """
        End a meeting session and cleanup resources.
        
        Args:
            bot_id: Bot ID to end session for
        """
        with self.sessions_lock:
            session = self.sessions.get(bot_id)
            
            if not session:
                logger.warning(f"No session found for bot {bot_id}")
                return
            
            logger.info(f"Ending session for bot {bot_id}")
            
            # Mark as inactive
            session.is_active = False
            session.state.is_running = False
            
            # Delete bot from Recall.ai
            try:
                self.recall_service.delete_bot(bot_id)
            except Exception as e:
                logger.error(f"Failed to delete bot {bot_id}: {e}")
            
            # Wait for threads to finish (with timeout)
            for thread in session.processing_threads:
                thread.join(timeout=2.0)
            
            # Remove from sessions
            del self.sessions[bot_id]
            
            logger.info(f"Session {bot_id} ended and cleaned up")
    
    def get_active_sessions(self) -> Dict[str, MeetingSession]:
        """
        Get all active sessions.
        
        Returns:
            Dict of bot_id -> MeetingSession
        """
        with self.sessions_lock:
            return {
                bot_id: session
                for bot_id, session in self.sessions.items()
                if session.is_active
            }
    
    def shutdown_all(self):
        """Shutdown all active sessions."""
        logger.info("Shutting down all sessions")
        
        with self.sessions_lock:
            bot_ids = list(self.sessions.keys())
        
        for bot_id in bot_ids:
            try:
                self.end_session(bot_id)
            except Exception as e:
                logger.error(f"Error ending session {bot_id}: {e}")
        
        logger.info("All sessions shut down")


# Example usage
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    recall_service = RecallBotService()
    manager = SessionManager(recall_service)
    
    # Example: Create a session
    session = manager.create_session(
        bot_id="test-bot-123",
        meeting_url="https://teams.microsoft.com/..."
    )
    
    print(f"Session created: {session.bot_id}")
    print(f"Active sessions: {len(manager.get_active_sessions())}")
