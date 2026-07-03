"""
Session Manager
Manages multiple concurrent meeting sessions with independent STT/LLM/TTS pipelines.
Supports WebRTC streaming (Output Media API) for low-latency audio output.
"""

import logging
import queue
import re
import time
import threading
import asyncio
from typing import Dict, Optional
from dataclasses import dataclass, field
import numpy as np

from state import AgentState
from stt_engine import STTEngine
from llm_brain import LLMBrain
from recall_bot_service import RecallBotService, normalize_meeting_url
from integrated_audio_sender import IntegratedAudioSender
from webrtc_stream_manager import WebRTCStreamManager
import config

from transcript_log import close_session, log_transcript, start_session
from language_profiles import get_profile, get_ui_strings

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
    audio_sender: Optional[IntegratedAudioSender] = None
    webrtc_manager: Optional[WebRTCStreamManager] = None  # Legacy WebRTC (unused with webpage mode)
    processing_threads: list = field(default_factory=list)
    is_active: bool = True
    use_webrtc: bool = False   # Legacy flag (raw PCM WebRTC — superseded by use_webpage)
    use_webpage: bool = False  # Output Media webpage mode — PCM streamed via /ws/audio-stream
    # Fallback task that clears is_ai_speaking if browser never sends playback_done
    _speaking_fallback_task: Optional[asyncio.Task] = None
    # Sarvam STT engine (primary) — None when Sarvam is disabled or unavailable
    sarvam_stt_engine: Optional[object] = None
    scheduled_candidate_name: Optional[str] = None
    # Post-playback silence watcher — fires "can you hear me?" after quiet period
    _silence_watch_task: Optional[asyncio.Task] = None
    _presence_checks_this_question: int = 0
    _presence_check_q_index: int = -1
    # Persistent asyncio loop owned by the TTS worker thread
    tts_loop: Optional[asyncio.AbstractEventLoop] = None
    # True after end_of_turn sent — silence check starts only on next playback_done
    _awaiting_turn_playback: bool = False
    # Stored at join; used when POST /api/start triggers greeting
    pending_greeting_message: Optional[str] = None
    created_at: float = field(default_factory=time.time)

    def __post_init__(self):
        """Initialize processing components that don't need Sarvam config."""
        # STTEngine is created later in SessionManager.create_session() once we
        # know whether Sarvam STT is available (requires API key + config).
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
            Bot ID if exists, None if none or still creating
        """
        key = normalize_meeting_url(meeting_url)
        with self.sessions_lock:
            bot_id = self.meeting_to_bot.get(key)
            if bot_id == "CREATING":
                return None
            return bot_id

    def get_meeting_bot_entry(self, meeting_url: str) -> Optional[str]:
        """Return mapped bot id or 'CREATING' placeholder for this meeting."""
        key = normalize_meeting_url(meeting_url)
        with self.sessions_lock:
            return self.meeting_to_bot.get(key)

    def reserve_meeting(self, meeting_url: str) -> str:
        """Mark meeting as CREATING. Returns normalized URL key."""
        key = normalize_meeting_url(meeting_url)
        with self.sessions_lock:
            self.meeting_to_bot[key] = "CREATING"
        return key

    def release_meeting_reservation(self, meeting_url: str):
        """Remove CREATING placeholder if join failed."""
        key = normalize_meeting_url(meeting_url)
        with self.sessions_lock:
            if self.meeting_to_bot.get(key) == "CREATING":
                del self.meeting_to_bot[key]

    def cleanup_stale_bot(self, bot_id: str, meeting_url: str):
        """
        Remove local session/mapping when Recall reports the bot has ended.
        Does not call Recall delete — bot is already gone on their side.
        """
        key = normalize_meeting_url(meeting_url)
        with self.sessions_lock:
            session = self.sessions.get(bot_id)
            if session:
                session.is_active = False
                session.state.is_running = False
                self.cancel_silence_check(session)
                close_session(bot_id)
                del self.sessions[bot_id]
                logger.info(f"Removed stale local session for bot {bot_id[:8]}")
            if self.meeting_to_bot.get(key) == bot_id:
                del self.meeting_to_bot[key]
                logger.info(f"Cleared stale meeting mapping for {key[:50]}...")
    
    def create_session(
        self,
        bot_id: str,
        meeting_url: str,
        bot_data: Optional[Dict] = None,
        use_webpage: bool = False,
    ) -> MeetingSession:
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
            
            # ── Output Media webpage mode (primary low-latency path) ──────────
            if use_webpage:
                session.use_webpage = True
                logger.info(f"Bot {bot_id[:8]} using Output Media webpage streaming")
            else:
                # ── Legacy WebRTC raw PCM mode (kept for reference, rarely active) ─
                media_url = bot_data.get("media_url") if bot_data else None
                if media_url:
                    logger.info(f"Initializing legacy WebRTC streaming for bot {bot_id[:8]}")
                    session.webrtc_manager = WebRTCStreamManager(bot_id, media_url)
                    session.use_webrtc = True

                    def connect_webrtc():
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                        try:
                            connected = loop.run_until_complete(session.webrtc_manager.connect())
                            if connected:
                                logger.info(f"✓ WebRTC connected for bot {bot_id[:8]}")
                            else:
                                logger.warning(f"✗ WebRTC failed for bot {bot_id[:8]}, using file upload")
                        except Exception as e:
                            logger.error(f"WebRTC error for bot {bot_id[:8]}: {e}")
                        finally:
                            loop.close()

                    threading.Thread(target=connect_webrtc, daemon=True).start()
                else:
                    logger.info(f"Bot {bot_id[:8]} using file-upload output_audio (fallback)")
                    session.use_webrtc = False

            # ── Build Sarvam STT engine (primary) + STTEngine (Whisper fallback) ─
            sarvam_stt = None
            if config.SARVAM_STT_ENABLED and config.SARVAM_API_KEY:
                try:
                    from sarvam_stt_engine import SarvamSTTEngine, SarvamSTTConfig
                    sarvam_stt_cfg = SarvamSTTConfig(
                        api_key=config.SARVAM_API_KEY,
                        model=config.SARVAM_STT_MODEL,
                        language_code=config.SARVAM_STT_LANGUAGE,
                        mode=config.SARVAM_STT_MODE,
                        sample_rate=16000,
                        high_vad_sensitivity=config.SARVAM_STT_HIGH_VAD,
                        flush_signal=True,
                        collect_deadline_seconds=config.SARVAM_STT_COLLECT_DEADLINE_SEC,
                        trailing_silence_seconds=config.SARVAM_STT_TRAILING_SILENCE_SEC,
                        wait_after_end_speech_seconds=config.SARVAM_STT_WAIT_AFTER_END_SEC,
                    )
                    sarvam_stt = SarvamSTTEngine(sarvam_stt_cfg)
                    session.sarvam_stt_engine = sarvam_stt
                    logger.info(
                        f"Bot {bot_id[:8]} Sarvam STT primary "
                        f"(model={config.SARVAM_STT_MODEL}, lang={config.SARVAM_STT_LANGUAGE})"
                    )
                except Exception as e:
                    logger.error(f"Failed to create Sarvam STT engine: {e} — will use Whisper only")
                    sarvam_stt = None

            # Connect Sarvam before STT thread starts (Whisper loads lazily on fallback only)
            if sarvam_stt is not None:
                threading.Thread(
                    target=sarvam_stt.start_session_loop,
                    name=f"SarvamSTT-Init-{bot_id[:8]}",
                    daemon=True,
                ).start()
                logger.info(f"Bot {bot_id[:8]} Sarvam STT session loop starting in background")

            session.stt_engine = STTEngine(session.state, sarvam_engine=sarvam_stt)
            session.state.on_candidate_speech = lambda s=session: self.on_candidate_speech(s)
            session.state.on_candidate_speech_started = (
                lambda s=session: self.on_candidate_speech_started(s)
            )
            session.state.on_preserve_stt_buffer = (
                lambda s=session: (
                    s.stt_engine.preserve_answer_in_progress()
                    if s.stt_engine
                    else None
                )
            )
            session.state.on_restore_stt_buffer = (
                lambda s=session: (
                    s.stt_engine.restore_answer_in_progress()
                    if s.stt_engine
                    else None
                )
            )
            session.state.on_question_advanced = (
                lambda s=session: (
                    s.stt_engine._sync_turn_question_index()
                    if s.stt_engine
                    else None
                )
            )

            if config.STT_FALLBACK_ENABLED and config.WHISPER_PRELOAD_ENABLED:
                threading.Thread(
                    target=session.stt_engine._ensure_whisper,
                    name=f"WhisperPreload-{bot_id[:8]}",
                    daemon=True,
                ).start()
                logger.info(f"Bot {bot_id[:8]} Whisper preload started in background")

            # ── Build audio sender ────────────────────────────────────────────
            from api_server import TTS_RATE, TTS_REDUCE_PAUSES
            from ws_hub import broadcast_pcm_sync, send_control_sync

            sarvam_config = None
            if config.SARVAM_TTS_ENABLED:
                sarvam_config = {
                    "model": config.SARVAM_TTS_MODEL,
                    "language_code": config.SARVAM_TTS_LANGUAGE,
                    "sample_rate": config.SARVAM_TTS_SAMPLE_RATE,
                    "pace": config.SARVAM_TTS_PACE,
                    "temperature": config.SARVAM_TTS_TEMPERATURE,
                    "max_retries": config.SARVAM_MAX_RETRIES
                }

            # Wrap broadcast functions with this bot's ID so audio_sender
            # doesn't need to know about the WS hub internals.
            _bot_id = bot_id  # capture for closure
            webpage_pcm_broadcaster = (
                (lambda pcm, _bid=_bot_id: broadcast_pcm_sync(_bid, pcm))
                if session.use_webpage else None
            )
            webpage_ctrl_sender = (
                (lambda msg, _bid=_bot_id: send_control_sync(_bid, msg))
                if session.use_webpage else None
            )

            session.audio_sender = IntegratedAudioSender(
                self.recall_service,
                rate=TTS_RATE,
                reduce_pauses=TTS_REDUCE_PAUSES,
                webrtc_manager=session.webrtc_manager if session.use_webrtc else None,
                use_sarvam=config.SARVAM_TTS_ENABLED,
                sarvam_api_key=config.SARVAM_API_KEY,
                sarvam_speaker=config.SARVAM_TTS_SPEAKER,
                sarvam_config=sarvam_config,
                webpage_broadcaster=webpage_pcm_broadcaster,
                webpage_ctrl_sender=webpage_ctrl_sender,
            )
            
            # Start processing threads
            self._start_session_threads(session)
            
            self.sessions[bot_id] = session
            # Update mapping from "CREATING" placeholder to actual bot_id
            meeting_key = normalize_meeting_url(meeting_url)
            self.meeting_to_bot[meeting_key] = bot_id
            start_session(bot_id)
            
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
        session.tts_loop = loop

        try:
            loop.run_until_complete(self._tts_worker_async(session, loop))
        finally:
            session.tts_loop = None
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
        # Webpage / WebRTC modes: stream each sentence immediately for low latency.
        # File upload mode: batch the whole turn into one clip (avoids overlap).
        batch_turns = not (session.use_webrtc or session.use_webpage)
        turn_sentences: list[str] = []
        
        # Pre-connect Sarvam TTS WebSocket before first sentence (avoids delay on greet)
        if session.audio_sender:
            await session.audio_sender.ensure_sarvam_connected()
        
        _running_loop = asyncio.get_running_loop()

        while session.is_active and session.state.is_running:
            try:
                # Use run_in_executor so the asyncio event loop is NOT blocked while
                # waiting for the next TTS sentence.  This lets the Sarvam TTS keepalive
                # task fire every 20 s, preventing the ~1.1 s reconnect penalty each turn.
                text = await _running_loop.run_in_executor(
                    None, session.state.tts_queue.get, True, 1.0
                )
                
                # FIX 7: Check for interrupt — drain queue if interrupted
                if session.state.interrupt_flag.is_set():
                    logger.info(f"Bot {session.bot_id[:8]} interrupted - draining TTS queue")
                    turn_sentences.clear()
                    # Drain remaining queued sentences — they are stale
                    while not session.state.tts_queue.empty():
                        try:
                            session.state.tts_queue.get_nowait()
                        except:
                            break
                    # Cancel pending playback-done fallback (no longer relevant)
                    if session._speaking_fallback_task:
                        session._speaking_fallback_task.cancel()
                        session._speaking_fallback_task = None
                    self.cancel_silence_check(session)
                    session._awaiting_turn_playback = False
                    # Tell the browser to flush its ring buffer immediately
                    if (session.use_webpage
                            and session.audio_sender
                            and session.audio_sender.webpage_ctrl_sender):
                        session.audio_sender.webpage_ctrl_sender({"type": "flush"})
                    session.state.is_ai_speaking.clear()
                    session.state.interrupt_flag.clear()
                    continue
                
                # Check for special markers
                if text == "<END_OF_TURN>":
                    if batch_turns and turn_sentences and session.audio_sender:
                        full_text = " ".join(turn_sentences)
                        turn_sentences.clear()
                        self.cancel_silence_check(session)
                        session.state.is_ai_speaking.set()
                        logger.info(
                            f"Bot {session.bot_id[:8]} speaking full turn "
                            f"({len(full_text)} chars, file upload batch mode)"
                        )
                        success = await session.audio_sender.send_text_to_bot(
                            session.bot_id,
                            full_text,
                            session.state
                        )
                        if not success:
                            consecutive_failures += 1
                            session.state.is_ai_speaking.clear()
                        else:
                            consecutive_failures = 0
                    else:
                        turn_sentences.clear()

                    # Cancel any leftover fallback from a previous turn
                    if session._speaking_fallback_task:
                        session._speaking_fallback_task.cancel()
                        session._speaking_fallback_task = None

                    if session.use_webpage:
                        # Tell browser the server finished sending audio for this turn.
                        # Silence watcher starts only after debounced playback_done.
                        session._awaiting_turn_playback = True
                        if (
                            session.audio_sender
                            and session.audio_sender.webpage_ctrl_sender
                        ):
                            session.audio_sender.webpage_ctrl_sender(
                                {"type": "end_of_turn"}
                            )
                        # Fallback if browser never sends playback_done
                        session._speaking_fallback_task = asyncio.ensure_future(
                            self._speaking_fallback(session, timeout=30.0)
                        )
                    else:
                        # File-upload / batch mode: no browser feedback — clear after brief delay
                        await asyncio.sleep(0.3)
                        session.state.is_ai_speaking.clear()
                        session.state.last_playback_done_at = time.monotonic()
                        if config.POST_TTS_SILENCE_CHECK_ENABLED:
                            self.cancel_silence_check(session)
                            session._silence_watch_task = asyncio.ensure_future(
                                self._run_silence_check(
                                    session, config.POST_TTS_SILENCE_CHECK_SEC
                                )
                            )

                    # Proactively ensure Sarvam TTS is still connected while the bot is
                    # idle (between turns).  The keepalive task handles this when the
                    # event loop is free, but an explicit ensure_connected() here is a
                    # belt-and-suspenders check that costs nothing if already alive.
                    if (session.use_webpage
                            and session.audio_sender
                            and getattr(session.audio_sender, 'sarvam_engine', None)
                            and not session.audio_sender.sarvam_engine.is_connected):
                        asyncio.ensure_future(
                            session.audio_sender.sarvam_engine.ensure_connected()
                        )
                        logger.debug(f"Bot {session.bot_id[:8]} proactive Sarvam TTS reconnect triggered")

                    session.state.interrupt_flag.clear()  # Reset for next turn
                    logger.debug(f"Bot {session.bot_id[:8]} finished speaking (waiting for playback_done)")
                    consecutive_failures = 0
                    continue
                
                # Validate text
                if not text or len(text.strip()) == 0:
                    logger.warning(f"Bot {session.bot_id[:8]} received empty text, skipping")
                    continue

                if batch_turns:
                    turn_sentences.append(text.strip())
                    continue
                
                # WebRTC / webpage mode: stream each sentence immediately for lower latency
                self.cancel_silence_check(session)
                session._awaiting_turn_playback = False
                session.state.is_ai_speaking.set()
                
                if session.audio_sender:
                    success = await session.audio_sender.send_text_to_bot(
                        session.bot_id,
                        text,
                        session.state
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
    
    async def _speaking_fallback(self, session: MeetingSession, timeout: float = 30.0):
        """
        Safety net: if the browser never sends playback_done (e.g. disconnected,
        browser crash), clear is_ai_speaking after `timeout` seconds so the STT
        is never permanently blocked.  Normally cancelled via task.cancel() when
        playback_done arrives or when the user interrupts.
        """
        try:
            await asyncio.sleep(timeout)
            if session.state.is_ai_speaking.is_set():
                session.state.is_ai_speaking.clear()
                logger.warning(
                    f"Bot {session.bot_id[:8]} playback_done never received — "
                    f"STT unblocked by {timeout}s fallback"
                )
        except asyncio.CancelledError:
            pass  # cancelled by interrupt or by playback_done handler — normal path

    def _sync_presence_question_index(self, session: MeetingSession) -> None:
        orch = session.state.interview_orchestrator
        if not orch:
            return
        idx = orch.current_index
        if idx != session._presence_check_q_index:
            session._presence_checks_this_question = 0
            session._presence_check_q_index = idx

    def cancel_silence_check(self, session: MeetingSession) -> None:
        task = session._silence_watch_task
        if task and not task.done():
            task.cancel()
        session._silence_watch_task = None

    def _candidate_is_silent(self, session: MeetingSession, since: float) -> bool:
        stt = session.stt_engine
        if stt and getattr(stt, "is_recording", False):
            return False
        last_speech = session.state.last_candidate_speech_at
        if last_speech and last_speech >= since:
            return False
        if not session.state.llm_queue.empty():
            return False
        return True

    async def _run_silence_check(self, session: MeetingSession, delay: float) -> None:
        try:
            await asyncio.sleep(delay)
            if not session.is_active or session.state.interview_ended.is_set():
                return
            if session.state.is_ai_speaking.is_set():
                return
            if session._awaiting_turn_playback:
                return

            orch = session.state.interview_orchestrator
            if orch is None:
                return
            from interview_engine import InterviewPhase
            if orch.phase != InterviewPhase.CORE:
                return

            self._sync_presence_question_index(session)
            if session._presence_checks_this_question >= config.MAX_PRESENCE_CHECKS_PER_QUESTION:
                return

            since = session.state.last_playback_done_at
            if not since or not self._candidate_is_silent(session, since):
                return

            import random
            lang = getattr(session.state, "interview_language", "english") or "english"
            phrases = get_ui_strings(lang).presence_phrases
            phrase = random.choice(phrases)
            session._presence_checks_this_question += 1
            session.state.pending_presence_check = True
            log_transcript(session.bot_id, "assistant", phrase)
            session.state.tts_queue.put(phrase)
            session.state.tts_queue.put("<END_OF_TURN>")
            logger.info(
                "[PRESENCE CHECK] bot=%s Q%d check=%d/%d",
                session.bot_id[:8],
                orch.current_index + 1,
                session._presence_checks_this_question,
                config.MAX_PRESENCE_CHECKS_PER_QUESTION,
            )
        except asyncio.CancelledError:
            pass
        finally:
            session._silence_watch_task = None

    def schedule_silence_check(
        self,
        session: MeetingSession,
        delay: Optional[float] = None,
    ) -> None:
        if not config.POST_TTS_SILENCE_CHECK_ENABLED:
            return
        if session.state.interview_ended.is_set():
            return
        orch = session.state.interview_orchestrator
        if orch is None:
            return
        from interview_engine import InterviewPhase
        if orch.phase != InterviewPhase.CORE:
            return

        loop = config.main_event_loop
        if not loop or not loop.is_running():
            return

        self.cancel_silence_check(session)
        override = getattr(session.state, "presence_check_delay_sec", None)
        if override is not None:
            wait = override
            session.state.presence_check_delay_sec = None
        else:
            wait = delay if delay is not None else config.POST_TTS_SILENCE_CHECK_SEC

        def _create_task() -> None:
            session._silence_watch_task = asyncio.ensure_future(
                self._run_silence_check(session, wait)
            )

        loop.call_soon_threadsafe(_create_task)

    def on_playback_done(self, session: MeetingSession) -> None:
        """Called when browser finishes playing bot audio — start silence watcher."""
        session.state.is_ai_speaking.clear()
        session.state.last_playback_done_at = time.monotonic()
        orch = session.state.interview_orchestrator
        bot_kind = getattr(session.state, "last_bot_speech_kind", "")
        if orch is not None:
            if bot_kind == "main":
                orch.mark_main_question_playback_done()
            elif bot_kind in ("clarifier", "drag"):
                orch.mark_mid_answer_bot_playback_done()
        if session._awaiting_turn_playback:
            session._awaiting_turn_playback = False
            mid_answer = getattr(session.state, "mid_answer_interrupt", False)
            if mid_answer:
                session.state.mid_answer_interrupt = False
                hook = getattr(session.state, "on_restore_stt_buffer", None)
                if callable(hook):
                    try:
                        hook()
                    except Exception as ex:
                        logger.warning(
                            f"Bot {session.bot_id[:8]} STT restore after mid-answer failed: {ex}"
                        )
            else:
                self.schedule_silence_check(session)
        if session.audio_sender and session.tts_loop:
            session.audio_sender.ensure_sarvam_connected_sync(session.tts_loop)
        logger.info(
            f"[audio-stream] playback_done — STT unblocked for bot {session.bot_id[:8]}…"
        )

    def on_candidate_speech_started(self, session: MeetingSession) -> None:
        """VAD detected speech — cancel pending presence check (before STT completes)."""
        session.state.pending_presence_check = False
        self.cancel_silence_check(session)

    def on_candidate_speech(self, session: MeetingSession) -> None:
        """Track candidate activity and cancel pending silence check."""
        session.state.last_candidate_speech_at = time.monotonic()
        session.state.pending_presence_check = False
        self.cancel_silence_check(session)

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
    
    # Backchannel patterns shared with stt_engine — single source of truth here.
    _BACKCHANNEL_RE = re.compile(
        r'^(yeah|yes|yep|yup|okay|ok|mhm|mmhmm|uh-huh|mm-hmm|right|sure|'
        r'got it|yeah yeah|ok ok|yes yes)[\.!\?]*$',
        re.IGNORECASE,
    )
    _FILLER_RE = re.compile(r'\b(um|uh|hmm|ah|uhm)\b[\.,]?', re.IGNORECASE)

    def handle_recall_transcript(
        self,
        bot_id: str,
        text: str,
        is_final: bool,
        is_bot_speaker: bool,
    ):
        """
        Called by AudioReceiver when Recall.ai fires a transcript.data event.

        Only *final* segments from *human* speakers are routed to the LLM.
        We also record the timestamp so stt_engine.transcribe_buffer() knows
        Recall already handled this utterance and can skip Whisper/Sarvam.

        This runs on the asyncio thread that drives AudioReceiver — it is
        intentionally lightweight (no blocking I/O).
        """
        # Partial transcripts arrive continuously while the candidate talks.
        # We log them for debugging but do not act on them.
        if not is_final:
            logger.debug(f"[RECALL PARTIAL] bot={bot_id[:8]} '{text[:60]}'")
            return

        # The bot's own speech is also transcribed — ignore it to avoid
        # the agent responding to itself.
        if is_bot_speaker:
            logger.debug(f"[RECALL BOT SPEECH IGNORED] bot={bot_id[:8]} '{text[:40]}'")
            return

        with self.sessions_lock:
            session = self.sessions.get(bot_id)

        if not session or not session.is_active:
            return
        if not session.state.is_started.is_set():
            return
        if session.state.interview_ended.is_set():
            logger.debug(
                f"[RECALL TRANSCRIPT SKIPPED — interview ended] "
                f"bot={bot_id[:8]} '{text[:40]}'"
            )
            return
        if session.state.is_ai_speaking.is_set():
            # Candidate is speaking while bot is — this is an interrupt.
            # The VAD pipeline already handles interrupt_flag; transcript
            # routing during bot speech would cause double-queuing.
            logger.debug(
                f"[RECALL TRANSCRIPT SKIPPED — bot speaking] "
                f"bot={bot_id[:8]} '{text[:40]}'"
            )
            return

        # Clean filler words
        text = self._FILLER_RE.sub('', text)
        text = re.sub(r'\s+', ' ', text).strip()

        if not text or len(text) < 3:
            return

        # Drop pure backchannels
        if self._BACKCHANNEL_RE.match(text):
            logger.info(f"[RECALL BACKCHANNEL FILTERED] '{text}'")
            return

        # Mark the time so stt_engine.transcribe_buffer() can detect the
        # duplicate and skip running Whisper / Sarvam on the same audio.
        session.state.last_recall_transcript_time = time.monotonic()
        self.on_candidate_speech(session)

        logger.info(f"\n[RECALL TRANSCRIPT] '{text}'")
        session.state.llm_queue.put(text)

    def _apply_tts_language_sync(self, session: MeetingSession, language_code: str) -> bool:
        """Reconnect Sarvam TTS on the TTS worker loop (not the HTTP loop)."""
        if not session.audio_sender:
            return False
        tts_loop = session.tts_loop
        if not tts_loop or not tts_loop.is_running():
            for _ in range(50):
                tts_loop = session.tts_loop
                if tts_loop and tts_loop.is_running():
                    break
                time.sleep(0.05)
        if not tts_loop or not tts_loop.is_running():
            logger.warning(
                "[TTS LANG] bot=%s TTS worker loop not ready — language stored only",
                session.bot_id[:8],
            )
            if session.audio_sender.sarvam_engine:
                session.audio_sender.sarvam_engine.update_language_code(language_code)
            return False
        return session.audio_sender.apply_tts_language_sync(language_code, tts_loop)

    async def apply_language_profile(self, session: MeetingSession, language_mode: str) -> None:
        """
        Apply STT/TTS language settings for this interview session.
        Called from POST /api/start before the greeting.
        """
        profile = get_profile(language_mode)
        session.state.interview_language = profile.mode

        if session.sarvam_stt_engine is not None:
            session.sarvam_stt_engine.apply_language_settings_sync(
                profile.speech.stt_language,
                profile.speech.stt_mode,
            )

        if session.audio_sender is not None:
            self._apply_tts_language_sync(session, profile.speech.tts_language)

        logger.info(
            "[LANGUAGE] bot=%s mode=%s stt=%s/%s tts=%s whisper_fb=%s",
            session.bot_id[:8],
            profile.mode,
            profile.speech.stt_language,
            profile.speech.stt_mode,
            profile.speech.tts_language,
            profile.speech.whisper_fallback,
        )

    def configure_interview_session(
        self,
        session: MeetingSession,
        orchestrator,
        language_mode: str,
        greeting_message: Optional[str] = None,
    ) -> None:
        """Attach orchestrator at join; interview speech begins on POST /api/start."""
        session.state.interview_orchestrator = orchestrator
        session.state.interview_ended.clear()
        session.state.interview_language = language_mode
        session.pending_greeting_message = greeting_message
        session.scheduled_candidate_name = orchestrator.candidate_name
        if language_mode == "hinglish":
            orchestrator.localization_status = "pending"
        else:
            orchestrator.localization_status = "not_needed"

    def start_question_localization(self, session: MeetingSession) -> None:
        """Background batch Groq localization for Hinglish (runs during lobby wait)."""
        orch = session.state.interview_orchestrator
        if not orch or orch.language_mode != "hinglish":
            return
        if orch.localization_status not in ("pending", "failed"):
            return

        bot_id = session.bot_id

        def _run() -> None:
            try:
                from question_localizer import localize_planned_questions

                cache = localize_planned_questions(
                    orch.planned_questions, orch.language_mode
                )
                orch.apply_spoken_cache(cache)
                logger.info(
                    "[LOCALIZE] bot=%s ready planned=%d",
                    bot_id[:8],
                    len(orch.planned_questions),
                )
            except Exception as ex:
                orch.mark_localization_failed(str(ex))
                logger.error(
                    "[LOCALIZE] bot=%s failed: %s", bot_id[:8], ex, exc_info=True
                )

        threading.Thread(
            target=_run,
            daemon=True,
            name=f"localize-{bot_id[:8]}",
        ).start()

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
    
    def _clear_meeting_mapping_for_bot(self, bot_id: str, meeting_url: Optional[str] = None):
        """Remove meeting_url → bot_id entries for this bot."""
        if meeting_url:
            meeting_key = normalize_meeting_url(meeting_url)
            if self.meeting_to_bot.get(meeting_key) == bot_id:
                del self.meeting_to_bot[meeting_key]
                logger.info(f"Removed meeting URL mapping for {meeting_key[:50]}...")
                return
        for key, mapped_id in list(self.meeting_to_bot.items()):
            if mapped_id == bot_id:
                del self.meeting_to_bot[key]
                logger.info(f"Removed meeting URL mapping for {key[:50]}...")

    def end_session(self, bot_id: str) -> bool:
        """
        End a meeting session and cleanup resources.
        Always attempts to remove the Recall bot, even if local session is missing.

        Returns:
            True if Recall confirmed bot removal (or already ended).
        """
        with self.sessions_lock:
            session = self.sessions.get(bot_id)

        if session:
            logger.info(f"Ending session for bot {bot_id}")
            self.cancel_silence_check(session)
            close_session(bot_id)
            session.is_active = False
            session.state.is_running = False

            if (
                session.audio_sender
                and getattr(session.audio_sender, "sarvam_engine", None)
            ):
                try:
                    sarvam_tts = session.audio_sender.sarvam_engine
                    tts_loop = session.tts_loop
                    if tts_loop and tts_loop.is_running():
                        future = asyncio.run_coroutine_threadsafe(
                            sarvam_tts.disconnect(), tts_loop
                        )
                        future.result(timeout=5)
                    else:
                        tmp_loop = asyncio.new_event_loop()
                        try:
                            tmp_loop.run_until_complete(sarvam_tts.disconnect())
                        finally:
                            tmp_loop.close()
                    logger.info(f"Sarvam TTS disconnected for bot {bot_id[:8]}")
                except Exception as e:
                    logger.error(
                        f"Error disconnecting Sarvam TTS for bot {bot_id[:8]}: {e}"
                    )

            if session.sarvam_stt_engine is not None:
                try:
                    session.sarvam_stt_engine.stop_session_loop()
                    logger.info(f"Sarvam STT loop stopped for bot {bot_id[:8]}")
                except Exception as e:
                    logger.error(f"Error stopping Sarvam STT for bot {bot_id[:8]}: {e}")

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

            for thread in session.processing_threads:
                thread.join(timeout=2.0)

            with self.sessions_lock:
                self._clear_meeting_mapping_for_bot(bot_id, session.meeting_url)
                if bot_id in self.sessions:
                    del self.sessions[bot_id]
        else:
            logger.warning(
                f"No local session for bot {bot_id[:8]} — will still delete from Recall"
            )
            with self.sessions_lock:
                self._clear_meeting_mapping_for_bot(bot_id)

        recall_removed = False
        try:
            recall_removed = self.recall_service.remove_bot(bot_id)
            if recall_removed:
                logger.info(f"Recall bot {bot_id[:8]} removed from meeting")
            else:
                logger.warning(
                    f"Could not remove Recall bot {bot_id[:8]} from meeting"
                )
        except Exception as e:
            logger.error(f"Failed to remove bot {bot_id} from Recall: {e}")

        logger.info(f"Session {bot_id} ended and cleaned up")
        return recall_removed

    def cleanup_stale_lobby_bots(self, max_age_sec: float):
        """Remove bots stuck in lobby before interview start (never admitted / abandoned)."""
        now = time.time()
        with self.sessions_lock:
            candidates = [
                (bot_id, session)
                for bot_id, session in self.sessions.items()
                if session.is_active
                and not session.state.is_started.is_set()
                and not session.state.interview_ended.is_set()
                and (now - session.created_at) >= max_age_sec
            ]

        for bot_id, _session in candidates:
            try:
                phase, _ = self.recall_service.get_bot_phase(bot_id)
            except Exception as e:
                logger.warning(
                    f"Lobby janitor: could not verify bot {bot_id[:8]}: {e}"
                )
                continue

            if phase in ("lobby", "joining", "unknown"):
                logger.info(
                    f"Lobby timeout ({int(max_age_sec // 60)} min) — removing bot {bot_id[:8]}"
                )
                self.end_session(bot_id)

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
