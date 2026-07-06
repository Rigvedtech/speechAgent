"""
Standalone Recall.ai Transcription Demo
========================================
This file demonstrates how to use Recall.ai's built-in transcription service.
It receives PRE-TRANSCRIBED TEXT from Recall.ai (no local STT needed).

Usage:
1. Start ngrok: ngrok http 5000
2. Update .env: PUBLIC_WEBHOOK_URL=https://your-ngrok-url.ngrok.app
3. Run: python recall_transcript.py
4. Create bot via POST http://localhost:5000/create_bot with meeting_url
5. Transcriptions will print to console

This is SEPARATE from your existing STT pipeline - just for demonstration.
"""

import os
import logging
from datetime import datetime
from typing import Dict, Any, Optional
from fastapi import FastAPI, Request, HTTPException
from pydantic import BaseModel
import requests
import uvicorn
from dotenv import load_dotenv

load_dotenv()

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration
RECALL_API_KEY = os.getenv("RECALL_API_KEY")
RECALL_REGION = os.getenv("RECALL_REGION", "us-west-2")
PUBLIC_WEBHOOK_URL = os.getenv("PUBLIC_WEBHOOK_URL")  # Your ngrok URL

if not RECALL_API_KEY:
    raise ValueError("RECALL_API_KEY not found in .env file")

if not PUBLIC_WEBHOOK_URL:
    logger.warning(
        "PUBLIC_WEBHOOK_URL not set. You need to expose this server via ngrok. "
        "Example: ngrok http 5000, then add PUBLIC_WEBHOOK_URL=https://xxx.ngrok.app to .env"
    )

BASE_URL = f"https://{RECALL_REGION}.recall.ai/api/v1"

# FastAPI app
app = FastAPI(title="Recall.ai Transcription Demo", version="1.0.0")


class CreateBotRequest(BaseModel):
    meeting_url: str
    bot_name: Optional[str] = "Transcription Demo Bot"
    mode: Optional[str] = "prioritize_low_latency"  # or "prioritize_accuracy"


class CreateBotResponse(BaseModel):
    success: bool
    bot_id: str
    bot_name: str
    meeting_url: str
    message: str


def recall_api_request(endpoint: str, method: str = "GET", data: Dict = None) -> Dict[str, Any]:
    """Make request to Recall.ai API."""
    headers = {
        "Authorization": f"Token {RECALL_API_KEY}",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    
    url = f"{BASE_URL}{endpoint}"
    
    try:
        if method == "POST":
            response = requests.post(url, headers=headers, json=data, timeout=30)
        elif method == "GET":
            response = requests.get(url, headers=headers, timeout=10)
        else:
            raise ValueError(f"Unsupported method: {method}")
        
        response.raise_for_status()
        return response.json()
        
    except requests.HTTPError as e:
        logger.error(f"Recall.ai API error {e.response.status_code}: {e.response.text}")
        raise HTTPException(
            status_code=e.response.status_code,
            detail=f"Recall.ai API error: {e.response.text}"
        )
    except Exception as e:
        logger.error(f"Request failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/")
async def root():
    """Health check."""
    return {
        "status": "running",
        "service": "Recall.ai Transcription Demo",
        "description": "Receives transcriptions from Recall.ai (no local STT)",
        "endpoints": {
            "create_bot": "POST /create_bot",
            "webhook": "POST /webhook/transcript"
        }
    }


@app.post("/create_bot", response_model=CreateBotResponse)
async def create_bot(request: CreateBotRequest):
    """
    Create a bot with Recall.ai's built-in transcription.
    
    This configures the bot to use Recall.ai's transcription service,
    which means you'll receive PRE-TRANSCRIBED TEXT (not raw audio).
    
    Request Body:
    {
        "meeting_url": "https://teams.microsoft.com/...",
        "bot_name": "Transcription Demo Bot",
        "mode": "prioritize_low_latency"  // or "prioritize_accuracy"
    }
    """
    if not PUBLIC_WEBHOOK_URL:
        raise HTTPException(
            status_code=500,
            detail="PUBLIC_WEBHOOK_URL not configured. Please set up ngrok and update .env"
        )
    
    webhook_url = f"{PUBLIC_WEBHOOK_URL}/webhook/transcript"
    
    # Bot configuration with Recall.ai transcription
    bot_config = {
        "meeting_url": request.meeting_url,
        "bot_name": request.bot_name,
        "recording_config": {
            # Configure TRANSCRIPTION (not raw audio)
            "transcript": {
                "provider": {
                    "recallai_streaming": {
                        "mode": request.mode,  # "prioritize_low_latency" or "prioritize_accuracy"
                        "language_code": "en" if request.mode == "prioritize_low_latency" else "auto"
                    }
                },
                "diarization": {
                    "use_separate_streams_when_available": True  # Speaker identification
                }
            },
            # Webhook endpoint to receive transcript events
            "realtime_endpoints": [
                {
                    "type": "webhook",
                    "url": webhook_url,
                    "events": [
                        "transcript.data",          # Final transcript utterances
                        "transcript.partial_data"   # Partial/interim transcripts (optional)
                    ]
                }
            ]
        }
    }
    
    logger.info(f"Creating bot with Recall.ai transcription for: {request.meeting_url}")
    logger.info(f"Transcription mode: {request.mode}")
    logger.info(f"Webhook URL: {webhook_url}")
    
    try:
        bot_data = recall_api_request("/bot/", method="POST", data=bot_config)
        bot_id = bot_data["id"]
        
        logger.info(f"✓ Bot created successfully: {bot_id}")
        logger.info(f"✓ Transcriptions will be printed to console when received")
        
        return CreateBotResponse(
            success=True,
            bot_id=bot_id,
            bot_name=request.bot_name,
            meeting_url=request.meeting_url,
            message=f"Bot created! Transcriptions will appear in console. Webhook: {webhook_url}"
        )
        
    except Exception as e:
        logger.error(f"Failed to create bot: {e}")
        raise


@app.post("/webhook/transcript")
async def receive_transcript(request: Request):
    """
    Webhook endpoint to receive transcript events from Recall.ai.
    
    This receives PRE-TRANSCRIBED TEXT from Recall.ai's transcription service.
    No local STT processing needed!
    """
    try:
        body = await request.json()
        event_type = body.get("event")
        
        # Handle final transcript
        if event_type == "transcript.data":
            data = body.get("data", {}).get("data", {})
            
            # Extract transcript information
            participant = data.get("participant", {})
            speaker_name = participant.get("name", "Unknown")
            speaker_id = participant.get("id", "unknown")
            
            words = data.get("words", [])
            transcript_text = " ".join([w.get("text", "") for w in words]).strip()
            
            language_code = data.get("language_code", "unknown")
            start_time = data.get("start_timestamp_ms", 0) / 1000.0  # Convert to seconds
            
            # Print to console (this is where you'd see the transcription)
            timestamp = datetime.now().strftime("%H:%M:%S")
            
            print("\n" + "="*80)
            print(f"🎙️  FINAL TRANSCRIPTION [{timestamp}]")
            print(f"Speaker: {speaker_name} (ID: {speaker_id})")
            print(f"Language: {language_code}")
            print(f"Time: {start_time:.2f}s")
            print(f"Text: {transcript_text}")
            print("="*80 + "\n")
            
            logger.info(f"Received final transcript from {speaker_name}: {transcript_text[:50]}...")
        
        # Handle partial/interim transcript (optional - shows real-time progress)
        elif event_type == "transcript.partial_data":
            data = body.get("data", {}).get("data", {})
            
            participant = data.get("participant", {})
            speaker_name = participant.get("name", "Unknown")
            
            words = data.get("words", [])
            partial_text = " ".join([w.get("text", "") for w in words]).strip()
            
            # Print partial transcript (lighter formatting)
            timestamp = datetime.now().strftime("%H:%M:%S")
            print(f"⏳ [{timestamp}] {speaker_name}: {partial_text}")
            
            logger.debug(f"Received partial transcript from {speaker_name}")
        
        else:
            logger.debug(f"Received event: {event_type}")
        
        return {"ok": True}
        
    except Exception as e:
        logger.error(f"Error processing webhook: {e}", exc_info=True)
        return {"ok": False, "error": str(e)}


@app.get("/info")
async def info():
    """Show configuration information."""
    return {
        "recall_region": RECALL_REGION,
        "webhook_url_configured": PUBLIC_WEBHOOK_URL is not None,
        "public_webhook_url": PUBLIC_WEBHOOK_URL,
        "transcription_modes": {
            "prioritize_low_latency": "1-3 seconds latency, English only",
            "prioritize_accuracy": "3-10 minutes latency, all languages, more features"
        },
        "how_it_works": {
            "1": "Create bot via POST /create_bot",
            "2": "Bot joins meeting and Recall.ai transcribes audio in their cloud",
            "3": "Transcriptions sent to /webhook/transcript via HTTP webhook",
            "4": "Transcriptions printed to console (no local STT needed)"
        }
    }


if __name__ == "__main__":
    print("\n" + "="*80)
    print("🎙️  Recall.ai Transcription Demo Server")
    print("="*80)
    print(f"Recall Region: {RECALL_REGION}")
    print(f"Webhook URL: {PUBLIC_WEBHOOK_URL or 'NOT CONFIGURED'}")
    print("\nThis demonstrates Recall.ai's built-in transcription service.")
    print("You'll receive PRE-TRANSCRIBED TEXT (no local STT needed).\n")
    
    if not PUBLIC_WEBHOOK_URL:
        print("⚠️  WARNING: PUBLIC_WEBHOOK_URL not set!")
        print("   1. Start ngrok: ngrok http 5000")
        print("   2. Add to .env: PUBLIC_WEBHOOK_URL=https://your-ngrok-url.ngrok.app")
        print("   3. Restart this server\n")
    
    print("Endpoints:")
    print("  - GET  http://localhost:5000/         (health check)")
    print("  - GET  http://localhost:5000/info     (configuration info)")
    print("  - POST http://localhost:5000/create_bot (create bot with transcription)")
    print("="*80 + "\n")
    
    uvicorn.run(app, host="0.0.0.0", port=5000, log_level="info")
