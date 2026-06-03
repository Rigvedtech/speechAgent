"""
Audio Sender
Handles TTS audio generation and sending to Recall.ai bot for playback in meeting.
"""

import os
import logging
import asyncio
from pathlib import Path
from typing import Optional
import edge_tts
from recall_bot_service import RecallBotService

logger = logging.getLogger(__name__)


class AudioSender:
    """Generate TTS audio and send to Recall.ai bot."""
    
    def __init__(
        self,
        recall_service: RecallBotService,
        voice: str = "en-IN-PrabhatNeural",
        rate: str = "+0%"
    ):
        """
        Initialize audio sender.
        
        Args:
            recall_service: RecallBotService instance
            voice: Edge-TTS voice name
            rate: Speech rate adjustment
        """
        self.recall_service = recall_service
        self.voice = voice
        self.rate = rate
        self.temp_dir = Path("tmp_audio")
        self.temp_dir.mkdir(exist_ok=True)
    
    async def generate_audio(self, text: str, output_path: Path) -> bool:
        """
        Generate audio from text using Edge-TTS.
        
        Args:
            text: Text to convert to speech
            output_path: Where to save audio file
            
        Returns:
            True if generation successful
        """
        try:
            communicate = edge_tts.Communicate(text, self.voice, rate=self.rate)
            await communicate.save(str(output_path))
            
            if output_path.exists() and output_path.stat().st_size > 0:
                logger.debug(f"Generated audio: {output_path.name}")
                return True
            else:
                logger.error("Generated audio file is empty")
                return False
                
        except Exception as e:
            logger.error(f"Failed to generate audio: {e}")
            return False
    
    async def send_text_to_bot(self, bot_id: str, text: str) -> bool:
        """
        Generate TTS audio and send to bot for playback in meeting.
        
        Args:
            bot_id: Bot ID to send audio to
            text: Text to speak
            
        Returns:
            True if audio sent successfully
        """
        import uuid
        import time
        
        start_time = time.time()
        
        # Generate unique filename
        filename = f"tts_{uuid.uuid4().hex[:8]}"
        mp3_path = self.temp_dir / f"{filename}.mp3"
        
        try:
            # Generate MP3 using Edge-TTS
            success = await self.generate_audio(text, mp3_path)
            if not success:
                logger.error(f"Failed to generate TTS audio for text: {text[:50]}")
                return False
            
            # Verify file exists and has content
            if not mp3_path.exists() or mp3_path.stat().st_size == 0:
                logger.error(f"Generated audio file is empty or missing: {mp3_path}")
                return False
            
            # Read audio file
            with open(mp3_path, "rb") as f:
                audio_data = f.read()
            
            # Send to bot (Recall.ai only supports MP3)
            success = self.recall_service.send_audio_to_bot(
                bot_id=bot_id,
                audio_data=audio_data,
                audio_codec="mp3"
            )
            
            elapsed = time.time() - start_time
            
            if success:
                logger.info(
                    f"Sent audio to bot {bot_id}: '{text[:50]}...' "
                    f"({len(audio_data)} bytes, {elapsed:.2f}s)"
                )
            else:
                logger.error(
                    f"Failed to send audio to bot {bot_id} for text: {text[:50]}"
                )
            
            return success
            
        except Exception as e:
            logger.error(f"Failed to send audio to bot: {e}", exc_info=True)
            return False
            
        finally:
            # Cleanup temp files
            try:
                mp3_path.unlink(missing_ok=True)
            except Exception as e:
                logger.warning(f"Failed to cleanup temp file {mp3_path}: {e}")
    
    def send_text_to_bot_sync(self, bot_id: str, text: str) -> bool:
        """
        Synchronous wrapper for send_text_to_bot.
        
        Args:
            bot_id: Bot ID
            text: Text to speak
            
        Returns:
            True if successful
        """
        return asyncio.run(self.send_text_to_bot(bot_id, text))


# Example usage
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    # Initialize services
    recall_service = RecallBotService()
    sender = AudioSender(recall_service)
    
    # Example: Send audio to a bot
    bot_id = "your-bot-id-here"
    text = "Hello! I'm your AI interviewer. Let's begin the interview."
    
    success = sender.send_text_to_bot_sync(bot_id, text)
    print(f"Audio sent: {success}")
