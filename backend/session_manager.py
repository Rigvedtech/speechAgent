"""
Session Manager
Manages multiple concurrent meeting sessions with independent STT/LLM/TTS pipelines.
Supports WebRTC streaming (Output Media API) for low-latency audio output.
"""

import logging
import queue
import threading
import asyncio
from typing import Dict, Optional
from dataclasses import dataclass, field
import numpy as np

from state import AgentState
from stt_engine import STTEngine
from llm_brain import LLMBrain
from recall_bot_service import RecallBotService
from audio_sender import AudioSender
from webrtc_stream_manager import WebRTCStreamManager

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
    webrtc_manager: Optional[WebRTCStreamManager] = None  # WebRTC connection for Output Media API
    processing_threads: list = field(default_factory=list)
    is_active: bool = True
    use_webrtc: bool = False  # Flag to indicate if using WebRTC (Output Media API)
    
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
        # DUPLICATE PREVENTION: Track meeting_url -> bot_id mapping
        self.meeting_to_bot: Dict[str, str] = {}
    
    def get_bot_for_meeting(self, meeting_url: str) -> Optional[str]:
        """
        Check if a bot already exists for this meeting URL.
        
        Args:
            meeting_url: Meeting URL to check
            
        Returns:
            Bot ID if exists, "CREATING" if in progress, None otherwise
        """
        with self.sessions_lock:
            bot_id = self.meeting_to_bot.get(meeting_url)
            # Don't return "CREATING" placeholder as a valid bot ID
            if bot_id == "CREATING":
                return None
            return bot_id
    
    def create_session(self, bot_id: str, meeting_url: str, bot_data: Optional[Dict] = None) -> MeetingSession:
        """
        Create a new meeting session with WebRTC support.
        
        Args:
            bot_id: Bot ID from Recall.ai
            meeting_url: Meeting URL bot joined
            bot_data: Optional bot creation response data (contains media_url for WebRTC)
            
        Returns:
            MeetingSession instance
        """
        with self.sessions_lock:
            if bot_id in self.sessions:
                logger.warning(f"Session {bot_id} already exists")
                return self.sessions[bot_id]
            
            logger.info(f"Creating session for bot {bot_id} in meeting {meeting_url[:50]}...")
            session = MeetingSession(bot_id=bot_id, meeting_url=meeting_url)
            
            # Check if bot supports WebRTC (Output Media API)
            media_url = bot_data.get("media_url") if bot_data else None
            
            if media_url:
                # Initialize WebRTC Stream Manager for Output Media API
                logger.info(f"Initializing WebRTC streaming for bot {bot_id[:8]}")
                session.webrtc_manager = WebRTCStreamManager(bot_id, media_url)
                session.use_webrtc = True
                
                # Connect WebRTC in background (non-blocking)
                def connect_webrtc():
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        connected = loop.run_until_complete(session.webrtc_manager.connect())
                        if connected:
                            logger.info(f"✓ WebRTC connected for bot {bot_id[:8]}")
                        else:
                            logger.warning(f"✗ WebRTC connection failed for bot {bot_id[:8]}, will use file upload fallback")
                    except Exception as e:
                        logger.error(f"WebRTC connection error for bot {bot_id[:8]}: {e}")
                    finally:
                        loop.close()
                
                webrtc_thread = threading.Thread(target=connect_webrtc, daemon=True)
                webrtc_thread.start()
            else:
                logger.info(f"Bot {bot_id[:8]} using legacy file upload (no media_url)")
                session.use_webrtc = False
            
            # Initialize audio sender with WebRTC support
            from api_server import TTS_RATE, TTS_REDUCE_PAUSES
            session.audio_sender = AudioSender(
                self.recall_service,
                rate=TTS_RATE,
                reduce_pauses=TTS_REDUCE_PAUSES,
                webrtc_manager=session.webrtc_manager if session.use_webrtc else None
            )
            
            # Start processing threads
            self._start_session_threads(session)
            
            self.sessions[bot_id] = session
            # Update mapping from "CREATING" placeholder to actual bot_id
            self.meeting_to_bot[meeting_url] = bot_id
            
            logger.info(
                f"Session {bot_id} created for meeting "
                f"(Mode: {'WebRTC streaming' if session.use_webrtc else 'File upload'})"
            )
            
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
        Worker thread to send TTS audio to bot with persistent event loop.
        FIX 2: Create ONE persistent event loop for all TTS work.
        FIX 7: Drain tts_queue on interrupt.
        
        Args:
            session: MeetingSession to process TTS for
        """
        logger.info(f"TTS worker started for bot {session.bot_id}")
        
        # FIX 2: Create persistent event loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            loop.run_until_complete(self._tts_worker_async(session, loop))
        finally:
            loop.close()
            logger.info(f"TTS worker stopped for bot {session.bot_id[:8]}")
    
    async def _tts_worker_async(self, session: MeetingSession, loop: asyncio.AbstractEventLoop):
        """
        Async TTS worker loop with persistent event loop.
        
        Args:
            session: MeetingSession to process TTS for
            loop: Persistent event loop to use
        """
        consecutive_failures = 0
        max_consecutive_failures = 5
        
        while session.is_active and session.state.is_running:
            try:
                # Get text from TTS queue (with timeout)
                text = session.state.tts_queue.get(timeout=1.0)
                
                # FIX 7: Check for interrupt — drain queue if interrupted
                if session.state.interrupt_flag.is_set():
                    logger.info(f"Bot {session.bot_id[:8]} interrupted - draining TTS queue")
                    # Drain remaining queued sentences — they are stale
                    while not session.state.tts_queue.empty():
                        try:
                            session.state.tts_queue.get_nowait()
                        except:
                            break
                    session.state.is_ai_speaking.clear()
                    session.state.interrupt_flag.clear()
                    continue
                
                # Check for special markers
                if text == "<END_OF_TURN>":
                    # Reduced post-send buffer for sentence streaming
                    await asyncio.sleep(1.5)
                    
                    session.state.is_ai_speaking.clear()
                    session.state.interrupt_flag.clear()  # Reset for next turn
                    logger.debug(f"Bot {session.bot_id[:8]} finished speaking")
                    consecutive_failures = 0
                    continue
                
                # Validate text
                if not text or len(text.strip()) == 0:
                    logger.warning(f"Bot {session.bot_id[:8]} received empty text, skipping")
                    continue
                
                # Set speaking flag BEFORE sending
                session.state.is_ai_speaking.set()
                
                if session.audio_sender:
                    # FIX 2: Use await instead of asyncio.run(), pass state for interrupt checking
                    success = await session.audio_sender.send_text_to_bot(
                        session.bot_id,
                        text,
                        session.state  # Pass state for interrupt checking
                    )
                    
                    if success:
                        consecutive_failures = 0
                        logger.debug(f"Bot {session.bot_id[:8]} sent TTS: {text[:30]}...")
                    else:
                        consecutive_failures += 1
                        logger.error(
                            f"Bot {session.bot_id[:8]} failed to send audio "
                            f"(attempt {consecutive_failures}/{max_consecutive_failures})"
                        )
                        
                        if consecutive_failures >= max_consecutive_failures:
                            logger.critical(
                                f"Bot {session.bot_id[:8]} exceeded max TTS failures. "
                                f"Bot may have left the meeting."
                            )
                            consecutive_failures = 0  # Reset to avoid spam
                        
                        # Clear speaking flag on failure
                        session.state.is_ai_speaking.clear()
                else:
                    logger.error(f"Bot {session.bot_id[:8]} has no audio_sender configured")
                    session.state.is_ai_speaking.clear()
                
            except queue.Empty:
                consecutive_failures = 0
                continue
            except Exception as e:
                consecutive_failures += 1
                logger.error(
                    f"Bot {session.bot_id[:8]} TTS worker error: {e}",
                    exc_info=True
                )
                
                session.state.is_ai_speaking.clear()
                
                # Brief pause on error
                await asyncio.sleep(0.5)
    
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
            # Only log warning occasionally to avoid spam
            if not hasattr(self, '_unknown_bot_warnings'):
                self._unknown_bot_warnings = {}
            
            if bot_id not in self._unknown_bot_warnings:
                logger.warning(
                    f"Received audio for unknown bot {bot_id[:8]}... "
                    f"(This may be from a previous session. Further warnings for this bot will be suppressed.)"
                )
                self._unknown_bot_warnings[bot_id] = True
            return
        
        if not session.is_active:
            logger.debug(f"Received audio for inactive session {bot_id[:8]}")
            return
        
        # Feed audio to STT engine's queue
        try:
            session.state.audio_queue.put(audio_array, block=False)
        except queue.Full:
            logger.warning(f"Audio queue full for bot {bot_id[:8]}, dropping chunk (may indicate processing backlog)")
    
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
        Includes WebRTC disconnection if applicable.
        
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
            
            # Disconnect WebRTC if applicable
            if session.webrtc_manager and session.use_webrtc:
                try:
                    logger.info(f"Disconnecting WebRTC for bot {bot_id[:8]}")
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        loop.run_until_complete(session.webrtc_manager.disconnect())
                    finally:
                        loop.close()
                except Exception as e:
                    logger.error(f"Error disconnecting WebRTC for bot {bot_id[:8]}: {e}")
            
            # DUPLICATE PREVENTION: Remove meeting URL mapping
            meeting_url = session.meeting_url
            if meeting_url in self.meeting_to_bot and self.meeting_to_bot[meeting_url] == bot_id:
                del self.meeting_to_bot[meeting_url]
                logger.info(f"Removed meeting URL mapping for {meeting_url[:50]}...")
            
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
