"""
REST API Server for Recall.ai Bot Control
Use with Postman to join/leave meetings.
"""

import os
import asyncio
import logging
from pathlib import Path
from typing import Optional, List

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, field_validator
from dotenv import load_dotenv
import uvicorn

from recall_bot_service import (
    RecallBotService,
    BotConfig,
    normalize_meeting_url,
    bot_phase_message,
)
from session_manager import SessionManager
from audio_receiver import AudioReceiver
from transcript_log import log_transcript
import config as app_config
import ws_hub

load_dotenv()

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize FastAPI
app = FastAPI(title="Recall.ai Bot API", version="1.0.0")

# Serve audio-worklet-processor.js and other static assets
STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

@app.on_event("startup")
async def _capture_main_loop():
    """
    Store the running event loop in config.main_event_loop so TTS worker threads
    can schedule broadcasts via asyncio.run_coroutine_threadsafe.

    Stored in config (not here) to avoid the Python 'double module' problem:
    when api_server.py is run as __main__, any module that later does
    `from api_server import ...` gets a SECOND copy of this module with its own
    globals — meaning a module-level _main_loop here would never be visible to
    importers.  config.py is always imported under the same key in sys.modules.
    """
    import config as _cfg
    _cfg.main_event_loop = asyncio.get_running_loop()
    logger.info("[startup] Main event loop captured in config.main_event_loop")

# All WebSocket hub state and broadcast helpers live in ws_hub.py
# (avoids the Python __main__ double-module problem — see ws_hub.py for details)

# Initialize services
recall_service = RecallBotService()
session_manager = SessionManager(recall_service)

# Get config from env
BOT_NAME = os.getenv("BOT_NAME", "Prabhat")
PUBLIC_WEBSOCKET_URL = os.getenv("PUBLIC_WEBSOCKET_URL")
WEBSOCKET_PORT = int(os.getenv("WEBSOCKET_PORT", "8765"))

# TTS Configuration
TTS_RATE = os.getenv("TTS_RATE", "+35%")
TTS_REDUCE_PAUSES = os.getenv("TTS_REDUCE_PAUSES", "true").lower() == "true"


# Request/Response Models
class JoinMeetingRequest(BaseModel):
    meeting_url: str
    bot_name: Optional[str] = None


class JoinMeetingResponse(BaseModel):
    success: bool
    bot_id: str
    bot_name: str
    meeting_url: str
    status: str
    message: Optional[str] = None


class LeaveResponse(BaseModel):
    success: bool
    bot_id: str
    message: str


class StatusResponse(BaseModel):
    bot_id: str
    status: str
    meeting_url: Optional[str]
    is_active: bool


# ─── Output Media Webpage ────────────────────────────────────────────────────

@app.get("/voice-agent", response_class=HTMLResponse)
async def voice_agent_page():
    """
    Recall.ai loads this URL inside its headless Chromium bot.
    Pass ?bot_id=<uuid>&name=<display_name> in the URL.
    """
    html_path = STATIC_DIR / "output-media.html"
    return HTMLResponse(content=html_path.read_text(encoding="utf-8"))


# ─── Audio-stream WebSocket endpoint ────────────────────────────────────────

@app.websocket("/ws/audio-stream/{page_session_id}")
async def audio_stream_ws(websocket: WebSocket, page_session_id: str):
    """
    Recall.ai's output-media page connects here to receive PCM audio.
    The path param is the page_session_id embedded in the page URL at bot creation.

    Protocol:
      Server → Client (binary)  : raw Int16 PCM, 24 kHz mono (Sarvam bulbul:v3)
      Server → Client (text)    : JSON control {type: "start_speaking" | "stop_speaking" | "ping"}
      Client → Server (text)    : JSON {type: "pong"} heartbeat reply
    """
    await websocket.accept()

    # Resolve page_session_id → bot_id via ws_hub (shared module, no double-copy issue)
    bot_id = ws_hub.resolve_bot_id(page_session_id)
    logger.info(f"[audio-stream] Page connected — session={page_session_id[:8]}… bot={bot_id[:8]}…")

    await ws_hub.add_client(bot_id, websocket)

    import json as _json
    try:
        while True:
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=25)
                try:
                    msg = _json.loads(data)
                    if msg.get('type') == 'playback_done':
                        # Browser ring buffer drained — audio has finished playing.
                        session = session_manager.get_session(bot_id)
                        if session:
                            session_manager.on_playback_done(session)
                    # pong and unknown messages are silently ignored
                except Exception:
                    pass
            except asyncio.TimeoutError:
                await websocket.send_text(_json.dumps({"type": "ping"}))
    except WebSocketDisconnect:
        logger.info(f"[audio-stream] Page disconnected — session={page_session_id[:8]}…")
    except Exception as e:
        logger.warning(f"[audio-stream] Error — session={page_session_id[:8]}…: {e}")
    finally:
        await ws_hub.remove_client(bot_id, websocket)
        logger.info(f"[audio-stream] Cleaned up — session={page_session_id[:8]}…")


# ─── API Endpoints ────────────────────────────────────────────────────────────

@app.post("/api/join", response_model=JoinMeetingResponse)
async def join_meeting(request: JoinMeetingRequest):
    """
    Join a Teams/Zoom/Google Meet meeting.
    One bot per meeting URL — duplicate joins return 409 with a clear message.
    """
    bot_name = request.bot_name or BOT_NAME
    meeting_url = request.meeting_url.strip()
    if not meeting_url:
        raise HTTPException(status_code=400, detail="meeting_url is required")

    meeting_key = normalize_meeting_url(meeting_url)

    # ── Phase 1: check local map under lock ───────────────────────────────
    existing_bot_id: Optional[str] = None
    with session_manager.sessions_lock:
        existing = session_manager.meeting_to_bot.get(meeting_key)
        if existing == "CREATING":
            raise HTTPException(
                status_code=409,
                detail={
                    "message": "A bot is already being created for this meeting. Please wait.",
                    "phase": "joining",
                },
            )
        if existing:
            existing_bot_id = existing

    # ── Phase 2: verify existing bot with Recall (outside lock) ───────────
    if existing_bot_id:
        try:
            phase, status_code = recall_service.get_bot_phase(existing_bot_id)
        except Exception as e:
            logger.warning(f"Could not verify existing bot {existing_bot_id[:8]}: {e}")
            raise HTTPException(
                status_code=409,
                detail={
                    "message": "Another bot is already registered for this meeting.",
                    "bot_id": existing_bot_id,
                    "phase": "unknown",
                },
            )

        if phase == "ended":
            session_manager.cleanup_stale_bot(existing_bot_id, meeting_url)
        else:
            raise HTTPException(
                status_code=409,
                detail={
                    "message": bot_phase_message(phase),
                    "bot_id": existing_bot_id,
                    "phase": phase,
                    "recall_status": status_code,
                },
            )

    # ── Phase 3: atomically reserve slot (double-check after stale cleanup) ─
    with session_manager.sessions_lock:
        existing = session_manager.meeting_to_bot.get(meeting_key)
        if existing == "CREATING":
            raise HTTPException(
                status_code=409,
                detail={
                    "message": "A bot is already being created for this meeting. Please wait.",
                    "phase": "joining",
                },
            )
        if existing:
            # Another request won the race after our stale cleanup
            raise HTTPException(
                status_code=409,
                detail={
                    "message": "Another bot is already active for this meeting.",
                    "bot_id": existing,
                    "phase": "unknown",
                },
            )
        session_manager.meeting_to_bot[meeting_key] = "CREATING"

    # ── Phase 4: create bot (Recall API — slow, outside lock) ───────────────
    try:
        import uuid as _uuid

        logger.info(f"Creating bot '{bot_name}' for meeting: {meeting_url[:50]}...")

        public_base = os.getenv("PUBLIC_NGROK_URL", "").rstrip("/")
        page_session_id = str(_uuid.uuid4())
        output_media_page_url: Optional[str] = None

        if app_config.RECALL_USE_OUTPUT_MEDIA and public_base:
            import urllib.parse
            output_media_page_url = (
                f"{public_base}/voice-agent"
                f"?page_session_id={page_session_id}"
                f"&name={urllib.parse.quote(bot_name)}"
            )
            logger.info(f"Output Media page URL: {output_media_page_url}")
        elif app_config.RECALL_USE_OUTPUT_MEDIA:
            logger.warning(
                "RECALL_USE_OUTPUT_MEDIA=true but PUBLIC_NGROK_URL is not set — "
                "falling back to file-upload. Add PUBLIC_NGROK_URL to .env."
            )

        config = BotConfig(
            meeting_url=meeting_url,
            bot_name=bot_name,
            websocket_url=PUBLIC_WEBSOCKET_URL,
            use_output_media=app_config.RECALL_USE_OUTPUT_MEDIA,
            output_media_url=output_media_page_url,
        )

        bot_data = recall_service.create_bot(config)
        bot_id = bot_data["id"]

        use_webpage = bool(output_media_page_url)
        if use_webpage:
            ws_hub.register_page_session(page_session_id, bot_id)

        session_manager.create_session(
            bot_id, meeting_url, bot_data=bot_data, use_webpage=use_webpage
        )

        if bot_data.get("media_url"):
            logger.info(f"Bot '{bot_name}' created with WebRTC streaming. ID: {bot_id}")
        else:
            logger.info(f"Bot '{bot_name}' created with file upload. ID: {bot_id}")

        return JoinMeetingResponse(
            success=True,
            bot_id=bot_id,
            bot_name=bot_name,
            meeting_url=meeting_url,
            status="joining",
            message="Bot created and joining the meeting.",
        )

    except HTTPException:
        session_manager.release_meeting_reservation(meeting_url)
        raise
    except Exception as e:
        session_manager.release_meeting_reservation(meeting_url)
        logger.error(f"Failed to create bot: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


class QuestionBankItem(BaseModel):
    id: str
    difficulty: str
    source: str
    question: str

    @field_validator("id", mode="before")
    @classmethod
    def coerce_id_to_str(cls, v):
        if v is None:
            raise ValueError("id is required")
        return str(v).strip()


class StartInterviewRequest(BaseModel):
    candidate_name: str
    jdText: str
    cvText: str
    questions: List[QuestionBankItem]
    greeting_message: Optional[str] = None


@app.post("/api/start/{bot_id}")
async def start_interview(bot_id: str, request: StartInterviewRequest = None):
    """
    Start the interview with injected JD, resume, and question bank.

    Request Body:
    {
        "candidate_name": "Pranay",
        "jdText": "...",
        "cvText": "...",
        "questions": [
            {"id": "q1", "difficulty": "Low", "source": "jd", "question": "..."}
        ],
        "greeting_message": "optional custom greeting instruction"
    }
    """
    try:
        # Get session
        session = session_manager.get_session(bot_id)
        
        if not session:
            raise HTTPException(status_code=404, detail=f"Bot {bot_id} not found")
        
        if not session.is_active:
            raise HTTPException(status_code=400, detail="Bot session is not active")
        
        if session.state.is_started.is_set():
            raise HTTPException(
                status_code=409,
                detail={
                    "success": False,
                    "bot_id": bot_id,
                    "message": "Interview already started",
                },
            )

        if request is None:
            raise HTTPException(
                status_code=400,
                detail="Request body required: candidate_name, jdText, cvText, questions",
            )

        candidate_name = (request.candidate_name or "").strip()
        jd_text = (request.jdText or "").strip()
        cv_text = (request.cvText or "").strip()

        if not candidate_name:
            raise HTTPException(status_code=400, detail="candidate_name is required")
        if not jd_text:
            raise HTTPException(status_code=400, detail="jdText is required")
        if not cv_text:
            raise HTTPException(status_code=400, detail="cvText is required")
        if not request.questions:
            raise HTTPException(status_code=400, detail="questions list cannot be empty")

        from interview_engine import InterviewOrchestrator, parse_bank_questions

        try:
            bank = parse_bank_questions([q.model_dump() for q in request.questions])
            orchestrator = InterviewOrchestrator.create(
                bot_id=bot_id,
                candidate_name=candidate_name,
                jd_text=jd_text,
                cv_text=cv_text,
                bank=bank,
            )
        except ValueError as ve:
            raise HTTPException(status_code=400, detail=str(ve))

        session.state.interview_orchestrator = orchestrator
        session.state.interview_ended.clear()

        # Bot must be admitted to the meeting before interview starts
        try:
            phase, status_code = recall_service.get_bot_phase(bot_id)
        except Exception as e:
            logger.error(f"Failed to verify bot status before start: {e}")
            raise HTTPException(
                status_code=503,
                detail={
                    "message": "Could not verify bot meeting status. Try again shortly.",
                    "bot_id": bot_id,
                },
            )

        if phase == "ended":
            raise HTTPException(
                status_code=400,
                detail={
                    "message": "Bot is no longer in the meeting. Create a new bot with /api/join.",
                    "bot_id": bot_id,
                    "phase": phase,
                    "recall_status": status_code,
                },
            )

        if phase in ("lobby", "joining"):
            raise HTTPException(
                status_code=409,
                detail={
                    "message": "Bot has not entered the meeting yet. Admit the bot from the lobby first.",
                    "bot_id": bot_id,
                    "phase": phase,
                    "recall_status": status_code,
                },
            )

        if phase != "in_meeting":
            raise HTTPException(
                status_code=409,
                detail={
                    "message": f"Bot is not ready to start (status: {status_code}). Wait until it joins the meeting.",
                    "bot_id": bot_id,
                    "phase": phase,
                    "recall_status": status_code,
                },
            )
        
        # Get candidate name from injected session data
        candidate_name = orchestrator.candidate_name
        
        # Fixed professional greeting — bypasses LLM to guarantee consistent interview tone
        # Custom greeting_message (from API caller) goes via LLM as before
        if request.greeting_message:
            greeting_instruction = request.greeting_message

            session.state.is_started.set()
            session.state.llm_queue.put(greeting_instruction)
        else:
            greeting_text = (
                f"Hello {candidate_name}, welcome. "
                f"I'm {BOT_NAME}, your interviewer today. "
                f"Before we begin, could you please introduce yourself briefly?"
            )

            session.state.is_started.set()
            log_transcript(bot_id, "assistant", greeting_text)
            session.state.tts_queue.put(greeting_text)
            session.state.tts_queue.put("<END_OF_TURN>")

            # Advance orchestrator phase directly (no LLM bootstrap needed)
            orchestrator.on_greeting_sent()

            logger.info(
                "[INTERVIEW GREETING] bot=%s fixed greeting sent to TTS",
                bot_id[:8],
            )

        logger.info(
            "Interview started for bot %s candidate=%s planned_questions=%d",
            bot_id,
            candidate_name,
            len(orchestrator.planned_questions),
        )

        return {
            "success": True,
            "bot_id": bot_id,
            "message": "Interview started",
            "candidate_name": candidate_name,
            "questions_planned": len(orchestrator.planned_questions),
            "planned_question_ids": [q.id for q in orchestrator.planned_questions],
            "phase": orchestrator.phase.value,
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to start interview: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/interview/{bot_id}/report")
async def get_interview_report(bot_id: str):
    """
    Get structured interview report card (scores, develop/fix areas).
    Available once interview has started; best after interview ends.
    """
    session = session_manager.get_session(bot_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Bot {bot_id} not found")

    orch = session.state.interview_orchestrator
    if not orch:
        raise HTTPException(
            status_code=400,
            detail="Interview not started — call POST /api/start first",
        )

    report = orch.build_report()
    logger.info(
        "[REPORT] bot=%s scored=%d overall_avg=%s stopped=%s",
        bot_id[:8],
        report.get("questions_scored"),
        report.get("overall_average"),
        report.get("stopped_reason"),
    )
    return {"success": True, "report": report}


@app.delete("/api/leave/{bot_id}", response_model=LeaveResponse)
async def leave_meeting(bot_id: str):
    """
    Leave a meeting (remove bot).
    
    Path Parameter:
    - bot_id: Bot ID returned from /join
    
    Response:
    {
        "success": true,
        "bot_id": "abc-123",
        "message": "Bot removed from meeting"
    }
    """
    try:
        logger.info(f"Removing bot {bot_id} from meeting")
        
        # End session
        session_manager.end_session(bot_id)
        
        return LeaveResponse(
            success=True,
            bot_id=bot_id,
            message="Bot removed from meeting"
        )
        
    except Exception as e:
        logger.error(f"Failed to leave meeting: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/status/{bot_id}", response_model=StatusResponse)
async def get_bot_status(bot_id: str):
    """
    Get bot status.
    
    Path Parameter:
    - bot_id: Bot ID
    
    Response:
    {
        "bot_id": "abc-123",
        "status": "in_call",
        "meeting_url": "...",
        "is_active": true
    }
    """
    try:
        # Get from Recall.ai API
        status_data = recall_service.get_bot_status(bot_id)
        
        # Get local session
        session = session_manager.get_session(bot_id)
        
        return StatusResponse(
            bot_id=bot_id,
            status=status_data.get("status_changes", [{}])[-1].get("code", "unknown") if status_data.get("status_changes") else "unknown",
            meeting_url=status_data.get("meeting_url"),
            is_active=session.is_active if session else False
        )
        
    except Exception as e:
        logger.error(f"Failed to get status: {e}")
        raise HTTPException(status_code=404, detail=f"Bot {bot_id} not found")


@app.get("/api/sessions")
async def list_active_sessions():
    """
    List all active bot sessions with start status.
    
    Response:
    {
        "active_sessions": 2,
        "bots": [
            {
                "bot_id": "abc-123",
                "meeting_url": "...",
                "is_started": true
            }
        ]
    }
    """
    sessions = session_manager.get_active_sessions()
    
    return {
        "active_sessions": len(sessions),
        "bots": [
            {
                "bot_id": bot_id,
                "meeting_url": session.meeting_url,
                "is_active": session.is_active,
                "is_started": session.state.is_started.is_set(),
                "interview_ended": session.state.interview_ended.is_set(),
                "interview_phase": (
                    session.state.interview_orchestrator.phase.value
                    if session.state.interview_orchestrator
                    else None
                ),
                "questions_scored": (
                    len(session.state.interview_orchestrator.answer_records)
                    if session.state.interview_orchestrator
                    else 0
                ),
            }
            for bot_id, session in sessions.items()
        ]
    }


@app.get("/api/diagnostic/audio")
async def audio_diagnostic():
    """
    Production diagnostic endpoint - explains bot audio behavior and mute state.
    
    This endpoint provides critical information about how Recall.ai bots work.
    """
    sessions = session_manager.get_active_sessions()
    
    diagnostic_info = {
        "bot_audio_behavior": {
            "why_bot_shows_muted": "Recall.ai bots join meetings with microphone OFF by default. This is normal and expected.",
            "does_mute_prevent_speaking": False,
            "explanation": "The 'muted' icon is cosmetic. When you send audio via output_audio API, the bot WILL speak into the meeting regardless of the mute indicator.",
            "api_limitation": "Recall.ai does not provide an API to change the visual mute indicator. All production implementations work this way.",
            "how_bot_speaks": "Bot plays audio when triggered via POST /bot/{id}/output_audio/ endpoint (happens automatically when AI responds)"
        },
        "current_bot_status": {
            "active_bots": len(sessions),
            "bots": [
                {
                    "bot_id": bot_id[:8] + "...",
                    "can_speak": session.is_active and session.audio_sender is not None,
                    "meeting_url": session.meeting_url[:50] + "..." if len(session.meeting_url) > 50 else session.meeting_url
                }
                for bot_id, session in sessions.items()
            ]
        },
        "troubleshooting": {
            "if_bot_not_speaking": [
                "1. Check logs for '✓ Audio sent successfully' messages",
                "2. Verify bot status is 'in_call_recording' via GET /api/status/{bot_id}",
                "3. Check for 'kind field required' errors (should be fixed)",
                "4. Ensure automatic_audio_output is configured (should be present)",
                "5. Verify MP3 format is being used (not WAV)"
            ],
            "common_errors": {
                "kind_field_required": "Fixed - MP3 format with 'kind' field is now included",
                "cannot_command_completed_bot": "Bot has left meeting - create new bot",
                "bot_shows_muted": "Not an error - this is normal behavior"
            }
        },
        "production_status": {
            "audio_output_api": "✓ Configured with automatic_audio_output",
            "mp3_format": "✓ Using MP3 (required by Recall.ai)",
            "kind_field": "✓ Included in payload",
            "error_handling": "✓ Production-grade with retries",
            "bot_status_verification": "✓ Checks bot state before sending audio"
        }
    }
    
    return diagnostic_info


@app.get("/api/active_meetings")
async def list_active_meetings():
    """
    List all active meetings with their bot IDs.
    Useful for debugging duplicate bot issues.
    
    Response:
    {
        "active_meetings": 1,
        "meetings": [
            {
                "meeting_url": "https://teams.microsoft.com/...",
                "bot_id": "abc-123",
                "status": "active"
            }
        ]
    }
    """
    with session_manager.sessions_lock:
        meetings = []
        for meeting_url, bot_id in session_manager.meeting_to_bot.items():
            session = session_manager.sessions.get(bot_id)
            meetings.append({
                "meeting_url": meeting_url,
                "bot_id": bot_id,
                "status": "active" if (session and session.is_active) else "inactive"
            })
        
        return {
            "active_meetings": len(meetings),
            "meetings": meetings
        }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "recall-bot-api",
        "websocket_url": PUBLIC_WEBSOCKET_URL,
        "bot_name": BOT_NAME
    }


if __name__ == "__main__":
    # Start WebSocket receiver in background
    import threading
    import asyncio
    
    def start_websocket():
        receiver = AudioReceiver(
            host="0.0.0.0",
            port=WEBSOCKET_PORT,
            audio_callback=session_manager.handle_audio_chunk,
            transcript_callback=session_manager.handle_recall_transcript,
        )
        receiver.run()
    
    websocket_thread = threading.Thread(target=start_websocket, daemon=True)
    websocket_thread.start()
    
    logger.info("=" * 60)
    logger.info("Recall.ai Bot API Started")
    logger.info("=" * 60)
    logger.info(f"API Server: http://0.0.0.0:8000")
    logger.info(f"WebSocket: ws://0.0.0.0:{WEBSOCKET_PORT}")
    logger.info(f"Docs: http://0.0.0.0:8000/docs")
    logger.info(f"Bot Name: {BOT_NAME}")
    logger.info("=" * 60)
    
    # Start FastAPI server
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
