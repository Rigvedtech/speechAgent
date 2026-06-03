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
        Create a bot to join a meeting.
        
        Args:
            config: Bot configuration with meeting URL and settings
            
        Returns:
            Dict containing bot_id, status, and other bot details
            
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
        
        # Add WebSocket endpoint for real-time audio if provided
        if config.websocket_url:
            payload["recording_config"]["realtime_endpoints"] = [{
                "type": "websocket",
                "url": config.websocket_url,
                "events": ["audio_mixed_raw.data"]
            }]
        
        # Add greeting audio if provided
        if config.greeting_audio_path and os.path.exists(config.greeting_audio_path):
            with open(config.greeting_audio_path, "rb") as f:
                import base64
                audio_b64 = base64.b64encode(f.read()).decode()
                payload["automatic_audio_output"] = {
                    "b64_data": audio_b64,
                    "audio_codec": "wav"
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
            logger.info(f"Bot created successfully. ID: {bot_data.get('id')}")
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
        audio_codec: str = "wav",
        sample_rate: int = 16000
    ) -> bool:
        """
        Send audio for bot to play in the meeting.
        
        Args:
            bot_id: Bot ID
            audio_data: Audio data in bytes
            audio_codec: Audio format (wav or mp3)
            sample_rate: Audio sample rate
            
        Returns:
            True if audio sent successfully
        """
        import base64
        
        audio_b64 = base64.b64encode(audio_data).decode()
        
        payload = {
            "b64_data": audio_b64,
            "audio_codec": audio_codec,
            "sample_rate": sample_rate,
            "channels": 1
        }
        
        try:
            response = requests.post(
                f"{self.BASE_URL}/bot/{bot_id}/output_audio/",
                headers=self.headers,
                json=payload,
                timeout=30
            )
            response.raise_for_status()
            logger.debug(f"Audio sent to bot {bot_id}")
            return True
            
        except requests.HTTPError as e:
            logger.error(f"Failed to send audio to bot: {e.response.text}")
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
