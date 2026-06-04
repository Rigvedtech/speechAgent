"""
REST API Server for Recall.ai Bot Control
Use with Postman to join/leave meetings.
"""

import os
import logging
from typing import Dict, Optional
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from dotenv import load_dotenv
import uvicorn

from recall_bot_service import RecallBotService, BotConfig
from session_manager import SessionManager
from audio_receiver import AudioReceiver

load_dotenv()

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize FastAPI
app = FastAPI(title="Recall.ai Bot API", version="1.0.0")

# Initialize services
recall_service = RecallBotService()
session_manager = SessionManager(recall_service)

# Get config from env
BOT_NAME = os.getenv("BOT_NAME", "Prabhat")
PUBLIC_WEBSOCKET_URL = os.getenv("PUBLIC_WEBSOCKET_URL")

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


class LeaveResponse(BaseModel):
    success: bool
    bot_id: str
    message: str


class StatusResponse(BaseModel):
    bot_id: str
    status: str
    meeting_url: Optional[str]
    is_active: bool


# API Endpoints

@app.post("/api/join", response_model=JoinMeetingResponse)
async def join_meeting(request: JoinMeetingRequest):
    """
    Join a Teams/Zoom/Google Meet meeting.
    DUPLICATE PREVENTION: Returns existing bot if one already exists for this meeting.
    Thread-safe to prevent race conditions from double-clicks.
    
    Request Body:
    {
        "meeting_url": "https://teams.microsoft.com/...",
        "bot_name": "Prabhat"  (optional, defaults from env)
    }
    
    Response:
    {
        "success": true,
        "bot_id": "abc-123",
        "bot_name": "Prabhat",
        "meeting_url": "...",
        "status": "joining" or "already_in_meeting"
    }
    """
    bot_name = request.bot_name or BOT_NAME
    
    # RACE CONDITION FIX: Lock entire check-and-create process
    # This prevents double-clicks from creating duplicate bots
    with session_manager.sessions_lock:
        try:
            # Check if bot already exists for this meeting
            existing_bot_id = session_manager.meeting_to_bot.get(request.meeting_url)
            
            if existing_bot_id:
                logger.warning(
                    f"Bot already exists for meeting. Returning existing bot ID: {existing_bot_id}"
                )
                return JoinMeetingResponse(
                    success=True,
                    bot_id=existing_bot_id,
                    bot_name=bot_name,
                    meeting_url=request.meeting_url,
                    status="already_in_meeting"
                )
            
            logger.info(f"Creating bot '{bot_name}' for meeting: {request.meeting_url[:50]}...")
            
            # Reserve this meeting URL immediately (before creating bot)
            # This prevents race condition where second request checks before first finishes
            session_manager.meeting_to_bot[request.meeting_url] = "CREATING"
            
        except Exception as e:
            logger.error(f"Failed in pre-creation check: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))
    
    # Create bot OUTSIDE the lock (network call can be slow)
    try:
        config = BotConfig(
            meeting_url=request.meeting_url,
            bot_name=bot_name,
            websocket_url=PUBLIC_WEBSOCKET_URL,
            use_output_media=True  # Enable WebRTC Output Media API for low latency
        )
        
        bot_data = recall_service.create_bot(config)
        bot_id = bot_data["id"]
        
        # Create session with bot_data (contains media_url for WebRTC)
        session_manager.create_session(bot_id, request.meeting_url, bot_data=bot_data)
        
        # Log output method
        if bot_data.get("media_url"):
            logger.info(f"Bot '{bot_name}' created with WebRTC streaming. ID: {bot_id}")
        else:
            logger.info(f"Bot '{bot_name}' created with file upload. ID: {bot_id}")
        
        return JoinMeetingResponse(
            success=True,
            bot_id=bot_id,
            bot_name=bot_name,
            meeting_url=request.meeting_url,
            status="joining"
        )
        
    except Exception as e:
        # Clean up the "CREATING" placeholder on failure
        with session_manager.sessions_lock:
            if session_manager.meeting_to_bot.get(request.meeting_url) == "CREATING":
                del session_manager.meeting_to_bot[request.meeting_url]
        
        logger.error(f"Failed to create bot: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


class StartInterviewRequest(BaseModel):
    greeting_message: Optional[str] = None


@app.post("/api/start/{bot_id}")
async def start_interview(bot_id: str, request: StartInterviewRequest = None):
    """
    Start the interview by triggering initial greeting.
    Bot will introduce itself and ask candidate to introduce themselves.
    
    Path Parameter:
    - bot_id: Bot ID
    
    Request Body (optional):
    {
        "greeting_message": "Custom greeting..."  (optional)
    }
    
    Response:
    {
        "success": true,
        "bot_id": "abc-123",
        "message": "Interview started",
        "greeting": "Hello, I am Prabhat..."
    }
    """
    try:
        # Get session
        session = session_manager.get_session(bot_id)
        
        if not session:
            raise HTTPException(status_code=404, detail=f"Bot {bot_id} not found")
        
        if not session.is_active:
            raise HTTPException(status_code=400, detail="Bot session is not active")
        
        if session.state.is_started:
            return {
                "success": False,
                "bot_id": bot_id,
                "message": "Interview already started"
            }
        
        # Get candidate name from document.py
        import document as interview_documents
        candidate_name = getattr(interview_documents, "candidate_name", "").strip() or "the candidate"
        
        # DYNAMIC GREETING: Let LLM generate greeting naturally with context
        # Instead of hardcoded greeting, provide LLM with instruction to greet
        greeting_instruction = (
            f"You are an AI interviewer named {BOT_NAME}. "
            f"The candidate's name is {candidate_name}. "
            f"This is the start of a screening interview. "
            f"Greet the candidate warmly by name, introduce yourself as the interviewer, "
            f"and ask them to briefly introduce themselves."
        )
        
        # Mark as started FIRST
        session.state.is_started = True
        
        # Send greeting instruction to LLM (not TTS directly)
        # LLM will generate natural greeting and send to TTS
        session.state.llm_queue.put(greeting_instruction)
        
        logger.info(f"Interview started for bot {bot_id}, LLM will generate greeting")
        
        return {
            "success": True,
            "bot_id": bot_id,
            "message": "Interview started - LLM generating greeting",
            "greeting": "LLM will generate personalized greeting"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to start interview: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


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
                "is_started": session.state.is_started  # Show if interview started
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
            port=8765,
            audio_callback=session_manager.handle_audio_chunk
        )
        receiver.run()
    
    websocket_thread = threading.Thread(target=start_websocket, daemon=True)
    websocket_thread.start()
    
    logger.info("=" * 60)
    logger.info("Recall.ai Bot API Started")
    logger.info("=" * 60)
    logger.info(f"API Server: http://0.0.0.0:8000")
    logger.info(f"Docs: http://0.0.0.0:8000/docs")
    logger.info(f"Bot Name: {BOT_NAME}")
    logger.info("=" * 60)
    
    # Start FastAPI server
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
