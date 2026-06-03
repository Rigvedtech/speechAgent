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
        "status": "joining"
    }
    """
    try:
        bot_name = request.bot_name or BOT_NAME
        
        logger.info(f"Creating bot '{bot_name}' for meeting: {request.meeting_url}")
        
        # Create bot configuration
        config = BotConfig(
            meeting_url=request.meeting_url,
            bot_name=bot_name,
            websocket_url=PUBLIC_WEBSOCKET_URL
        )
        
        # Create bot via Recall.ai
        bot_data = recall_service.create_bot(config)
        bot_id = bot_data["id"]
        
        # Create session for this bot
        session_manager.create_session(bot_id, request.meeting_url)
        
        logger.info(f"Bot '{bot_name}' created successfully. ID: {bot_id}")
        
        return JoinMeetingResponse(
            success=True,
            bot_id=bot_id,
            bot_name=bot_name,
            meeting_url=request.meeting_url,
            status="joining"
        )
        
    except Exception as e:
        logger.error(f"Failed to join meeting: {e}", exc_info=True)
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
    List all active bot sessions.
    
    Response:
    {
        "active_sessions": 2,
        "bots": [
            {"bot_id": "abc-123", "meeting_url": "..."},
            ...
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
                "is_active": session.is_active
            }
            for bot_id, session in sessions.items()
        ]
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
