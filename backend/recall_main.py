"""
Recall.ai Meeting Bot Integration
Main entry point for running the integrated system with Recall.ai.
"""

import os
import sys
import logging
import asyncio
import signal
from typing import Optional
from dotenv import load_dotenv

from recall_bot_service import RecallBotService, BotConfig
from audio_receiver import AudioReceiver
from session_manager import SessionManager

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('recall_bot.log')
    ]
)

logger = logging.getLogger(__name__)


class RecallMeetingBot:
    """
    Main application class integrating Recall.ai with STT/LLM/TTS pipeline.
    """
    
    def __init__(self):
        """Initialize the meeting bot application."""
        # Get configuration from environment
        self.websocket_host = os.getenv("WEBSOCKET_HOST", "0.0.0.0")
        self.websocket_port = int(os.getenv("WEBSOCKET_PORT", "8765"))
        self.public_websocket_url = os.getenv("PUBLIC_WEBSOCKET_URL")
        
        if not self.public_websocket_url:
            logger.warning(
                "PUBLIC_WEBSOCKET_URL not set. Bot creation will require manual URL."
            )
        
        # Initialize services
        self.recall_service = RecallBotService()
        self.session_manager = SessionManager(self.recall_service)
        
        # Initialize audio receiver
        self.audio_receiver = AudioReceiver(
            host=self.websocket_host,
            port=self.websocket_port,
            audio_callback=self.session_manager.handle_audio_chunk,
            transcript_callback=self.session_manager.handle_recall_transcript,
            video_callback=self.session_manager.handle_video_frame,
        )
        
        # Shutdown flag
        self.shutdown_requested = False
    
    def create_bot_for_meeting(
        self,
        meeting_url: str,
        bot_name: str = "AI Interviewer"
    ) -> Optional[str]:
        """
        Create a bot to join a meeting.
        
        Args:
            meeting_url: Meeting URL (Teams/Zoom/Meet)
            bot_name: Name for the bot
            
        Returns:
            Bot ID if successful, None otherwise
        """
        try:
            config = BotConfig(
                meeting_url=meeting_url,
                bot_name=bot_name,
                websocket_url=self.public_websocket_url
            )
            
            logger.info(f"Creating bot for meeting: {meeting_url}")
            bot_data = self.recall_service.create_bot(config)
            bot_id = bot_data["id"]
            
            # Create session for this bot
            self.session_manager.create_session(bot_id, meeting_url)
            
            logger.info(
                f"Bot created successfully. ID: {bot_id}, "
                f"Status: {bot_data.get('status')}"
            )
            
            return bot_id
            
        except Exception as e:
            logger.error(f"Failed to create bot: {e}", exc_info=True)
            return None
    
    def handle_shutdown(self, signum, frame):
        """Handle shutdown signal."""
        logger.info(f"Received signal {signum}, initiating shutdown...")
        self.shutdown_requested = True
        self.shutdown()
    
    def shutdown(self):
        """Shutdown all sessions and services."""
        logger.info("Shutting down...")
        
        try:
            self.session_manager.shutdown_all()
        except Exception as e:
            logger.error(f"Error during shutdown: {e}")
        
        logger.info("Shutdown complete")
    
    async def run_async(self):
        """Run the application asynchronously."""
        # Register signal handlers
        signal.signal(signal.SIGINT, self.handle_shutdown)
        signal.signal(signal.SIGTERM, self.handle_shutdown)
        
        logger.info("=" * 60)
        logger.info("Recall.ai Meeting Bot Started")
        logger.info("=" * 60)
        logger.info(f"WebSocket server: ws://{self.websocket_host}:{self.websocket_port}")
        
        if self.public_websocket_url:
            logger.info(f"Public URL: {self.public_websocket_url}")
        else:
            logger.warning("PUBLIC_WEBSOCKET_URL not set - use ngrok to expose WebSocket")
        
        logger.info("=" * 60)
        
        try:
            # Start WebSocket server
            await self.audio_receiver.start()
        except KeyboardInterrupt:
            logger.info("Interrupted by user")
        except Exception as e:
            logger.error(f"Error running application: {e}", exc_info=True)
        finally:
            self.shutdown()
    
    def run(self):
        """Run the application."""
        try:
            asyncio.run(self.run_async())
        except KeyboardInterrupt:
            logger.info("Application stopped by user")
        except Exception as e:
            logger.error(f"Application error: {e}", exc_info=True)


def main():
    """Main entry point."""
    # Check required environment variables
    required_vars = ["RECALL_API_KEY"]
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    
    if missing_vars:
        logger.error(f"Missing required environment variables: {', '.join(missing_vars)}")
        logger.error("Please set them in .env file")
        sys.exit(1)
    
    # Create and run application
    app = RecallMeetingBot()
    app.run()


if __name__ == "__main__":
    main()
