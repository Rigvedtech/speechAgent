"""
Recall.ai Bot Service
Handles bot lifecycle: create, manage, delete bots for meeting integration.
"""

import os
import logging
from typing import Dict, Optional, Any
from dataclasses import dataclass
from datetime import datetime
import requests
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


@dataclass
class BotConfig:
    """Configuration for creating a Recall.ai bot."""
    meeting_url: str
    bot_name: str = "AI Interviewer"
    websocket_url: Optional[str] = None
    greeting_audio_path: Optional[str] = None
    join_at: Optional[str] = None  # ISO 8601 format for scheduled join
    use_output_media: bool = True  # Use Output Media API (WebRTC) for low latency


class RecallBotService:
    """Service to interact with Recall.ai API for bot management."""
    
    BASE_URL = "https://us-west-2.recall.ai/api/v1"
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize Recall.ai bot service.
        
        Args:
            api_key: Recall.ai API key (defaults to RECALL_API_KEY env var)
        """
        self.api_key = api_key or os.getenv("RECALL_API_KEY")
        if not self.api_key:
            raise ValueError("RECALL_API_KEY not found in environment variables")
        
        self.headers = {
            "Authorization": f"Token {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
    
    def create_bot(self, config: BotConfig) -> Dict[str, Any]:
        """
        Create a bot to join a meeting (Production Implementation with WebRTC).
        
        Output Method Selection:
        ========================
        - config.use_output_media = True: Uses Output Media API (WebRTC streaming, <1.5s latency)
        - config.use_output_media = False: Uses output_audio API (file upload, 4-8s latency)
        
        IMPORTANT - Bot "Muted" State:
        ==============================
        The bot will show as "MUTED" in the meeting UI - THIS IS NORMAL.
        - All Recall.ai bots join with microphone indicator OFF by default
        - This is a platform design choice and cannot be changed via API
        - The bot WILL speak when triggered via output_audio or output_media
        - The mute icon is cosmetic and does not affect functionality
        
        Args:
            config: Bot configuration with meeting URL and settings
            
        Returns:
            Dict containing bot_id, status, media_url (if using Output Media API)
            
        Raises:
            requests.HTTPError: If bot creation fails
        """
        payload = {
            "meeting_url": config.meeting_url,
            "bot_name": config.bot_name,
            "recording_config": {
                "audio_mixed_raw": {},  # Enable real-time audio streaming
            }
        }
        
        # Choose audio output method
        if config.use_output_media:
            # OUTPUT MEDIA API (WebRTC) - Production-grade low latency (<1.5s)
            logger.info(f"Creating bot with Output Media API (WebRTC streaming) for {config.meeting_url[:50]}...")
            payload["output_media"] = {
                # Omit camera field entirely (don't set to None or False)
                "microphone": {
                    "kind": "raw",
                    "sample_rate": 16000,
                    "channels": 1
                }
            }
        else:
            # LEGACY OUTPUT AUDIO API (file upload) - Fallback for compatibility
            logger.info(f"Creating bot with output_audio API (file upload) for {config.meeting_url[:50]}...")
            # REQUIRED for output_audio endpoint - add minimal silent MP3
            # This is a 0.1s silent MP3 file in base64 (satisfies API requirement)
            payload["automatic_audio_output"] = {
                "in_call_recording": {
                    "data": {
                        "kind": "mp3",
                        "b64_data": "//uQxAAAAAAAAAAAAAAAAAAAAAAAWGluZwAAAA8AAAACAAACcQCAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgP////////////////////////////////8AAAAATGF2YzU4LjM1AAAAAAAAAAAAAAAAJAAAAAAAAAAAAnEX3+CkAAAAAAD/+xDECgADSAMAAgBMAAABLAAAAHkA"
                    }
                }
            }
        
        # Add WebSocket endpoint for real-time audio if provided
        if config.websocket_url:
            payload["recording_config"]["realtime_endpoints"] = [{
                "type": "websocket",
                "url": config.websocket_url,
                "events": ["audio_mixed_raw.data"]
            }]
        
        # Override with custom greeting audio (only for output_audio API)
        if not config.use_output_media and config.greeting_audio_path and os.path.exists(config.greeting_audio_path):
            with open(config.greeting_audio_path, "rb") as f:
                import base64
                audio_b64 = base64.b64encode(f.read()).decode()
                payload["automatic_audio_output"]["in_call_recording"]["data"] = {
                    "kind": "mp3",
                    "b64_data": audio_b64
                }
        
        # Add scheduled join time if provided
        if config.join_at:
            payload["join_at"] = config.join_at
        
        # Use web_4_core variant for better performance with Output Media
        payload["variant"] = {
            "zoom": "web_4_core",
            "google_meet": "web_4_core",
            "microsoft_teams": "web_4_core",
            "webex": "web_4_core"
        }
        
        logger.info(f"Creating bot for meeting: {config.meeting_url}")
        
        try:
            response = requests.post(
                f"{self.BASE_URL}/bot/",
                headers=self.headers,
                json=payload,
                timeout=30
            )
            response.raise_for_status()
            
            bot_data = response.json()
            bot_id = bot_data.get('id')
            
            # Log media URL if using Output Media API
            if config.use_output_media and 'media_url' in bot_data:
                logger.info(
                    f"Bot created with Output Media API. ID: {bot_id}, "
                    f"Media URL: {bot_data.get('media_url')}"
                )
            else:
                logger.info(f"Bot created successfully. ID: {bot_id}")
            
            return bot_data
            
        except requests.HTTPError as e:
            logger.error(f"Failed to create bot: {e.response.text}")
            raise
        except Exception as e:
            logger.error(f"Error creating bot: {str(e)}")
            raise
    
    def get_bot_status(self, bot_id: str) -> Dict[str, Any]:
        """
        Get current status of a bot.
        
        Args:
            bot_id: Bot ID returned from create_bot
            
        Returns:
            Dict with bot status information
        """
        try:
            response = requests.get(
                f"{self.BASE_URL}/bot/{bot_id}/",
                headers=self.headers,
                timeout=10
            )
            response.raise_for_status()
            return response.json()
            
        except requests.HTTPError as e:
            logger.error(f"Failed to get bot status: {e.response.text}")
            raise
    
    def delete_bot(self, bot_id: str) -> bool:
        """
        Delete a bot and end its meeting participation.
        
        Args:
            bot_id: Bot ID to delete
            
        Returns:
            True if deletion successful
        """
        try:
            response = requests.delete(
                f"{self.BASE_URL}/bot/{bot_id}/",
                headers=self.headers,
                timeout=10
            )
            response.raise_for_status()
            logger.info(f"Bot {bot_id} deleted successfully")
            return True
            
        except requests.HTTPError as e:
            logger.error(f"Failed to delete bot: {e.response.text}")
            return False
    
    def send_audio_to_bot(
        self,
        bot_id: str,
        audio_data: bytes,
        audio_codec: str = "mp3",
        verify_bot_status: bool = True
    ) -> bool:
        """
        Send audio for bot to play in the meeting (production-grade with validation).
        
        Args:
            bot_id: Bot ID
            audio_data: Audio data in bytes (must be MP3 format)
            audio_codec: Audio format (only 'mp3' is supported by Recall.ai)
            verify_bot_status: Check bot is in meeting before sending (default: True)
            
        Returns:
            True if audio sent successfully
            
        Note:
            Bot will show as "muted" in the meeting UI - this is normal Recall.ai behavior.
            Audio will play regardless of the mute icon when sent via this API.
        """
        import base64
        
        # Validate audio codec
        if audio_codec.lower() != "mp3":
            logger.error(f"Unsupported audio codec '{audio_codec}'. Only 'mp3' is supported.")
            return False
        
        # Validate audio data
        if not audio_data or len(audio_data) == 0:
            logger.error(f"Empty audio data provided for bot {bot_id[:8]}")
            return False
        
        # Production: Verify bot is in recording state before sending audio
        if verify_bot_status:
            try:
                bot_status = self.get_bot_status(bot_id)
                status_value = bot_status.get("status_changes", [{}])[-1].get("code", "unknown")
                
                # Only send audio if bot is in active recording state
                if status_value not in ["in_call_recording", "recording"]:
                    logger.warning(
                        f"Bot {bot_id[:8]} not in recording state (status: {status_value}). "
                        f"Audio may not play. Current state: {status_value}"
                    )
                    # Still attempt to send, but warn
                    
            except Exception as e:
                logger.warning(f"Could not verify bot status for {bot_id[:8]}: {e}. Attempting to send anyway.")
        
        audio_b64 = base64.b64encode(audio_data).decode()
        
        # Recall.ai API requires only 'kind' and 'b64_data' fields
        payload = {
            "kind": "mp3",  # Required field - only 'mp3' is currently supported
            "b64_data": audio_b64
        }
        
        try:
            response = requests.post(
                f"{self.BASE_URL}/bot/{bot_id}/output_audio/",
                headers=self.headers,
                json=payload,
                timeout=30
            )
            response.raise_for_status()
            logger.info(
                f"✓ Audio sent successfully to bot {bot_id[:8]} ({len(audio_data)} bytes, {len(audio_b64)} b64 chars). "
                f"Bot will play audio in meeting (even though it shows as 'muted')."
            )
            return True
            
        except requests.HTTPError as e:
            error_detail = e.response.text
            logger.error(
                f"✗ HTTP {e.response.status_code} error sending audio to bot {bot_id[:8]}: {error_detail}"
            )
            
            # Production: Provide actionable error messages
            if "cannot_command_completed_bot" in error_detail:
                logger.error(
                    f"Bot {bot_id[:8]} has left the meeting or shut down. Cannot send audio. "
                    f"Create a new bot to rejoin."
                )
            elif "kind" in error_detail.lower():
                logger.error("API payload format error. Verify 'kind' and 'b64_data' fields are correct.")
            
            return False
            
        except Exception as e:
            logger.error(f"✗ Unexpected error sending audio to bot {bot_id[:8]}: {str(e)}", exc_info=True)
            return False


# Example usage
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    service = RecallBotService()
    
    # Example: Create a bot
    config = BotConfig(
        meeting_url="https://teams.microsoft.com/l/meetup-join/...",
        bot_name="AI Interviewer",
        websocket_url="wss://your-server.com/audio"
    )
    
    try:
        bot = service.create_bot(config)
        print(f"Bot created: {bot['id']}")
        print(f"Status: {bot['status']}")
        
        # Check status
        import time
        time.sleep(5)
        status = service.get_bot_status(bot['id'])
        print(f"Current status: {status['status']}")
        
    except Exception as e:
        print(f"Error: {e}")
