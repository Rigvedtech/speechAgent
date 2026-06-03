"""
Audio Sender
Handles TTS audio generation and sending to Recall.ai bot for playback in meeting.
"""

import os
import logging
import asyncio
import base64
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
    
    def convert_to_wav(self, input_path: Path, output_path: Path) -> bool:
        """
        Convert MP3 to WAV using ffmpeg (16kHz mono).
        
        Args:
            input_path: Input MP3 file
            output_path: Output WAV file
            
        Returns:
            True if conversion successful
        """
        import subprocess
        import shutil
        
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            logger.warning("ffmpeg not found, skipping WAV conversion")
            return False
        
        try:
            cmd = [
                ffmpeg,
                "-hide_banner",
                "-loglevel", "error",
                "-y",
                "-i", str(input_path),
                "-ar", "16000",  # 16kHz sample rate
                "-ac", "1",       # Mono
                "-acodec", "pcm_s16le",  # 16-bit PCM
                str(output_path)
            ]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
                check=False
            )
            
            if result.returncode == 0 and output_path.exists():
                logger.debug(f"Converted to WAV: {output_path.name}")
                return True
            else:
                logger.error(f"ffmpeg conversion failed: {result.stderr}")
                return False
                
        except Exception as e:
            logger.error(f"Error converting audio: {e}")
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
        wav_path = self.temp_dir / f"{filename}.wav"
        
        try:
            # Generate MP3 using Edge-TTS
            success = await self.generate_audio(text, mp3_path)
            if not success:
                return False
            
            # Try to convert to WAV (preferred for Teams)
            final_path = mp3_path
            audio_codec = "mp3"
            
            if self.convert_to_wav(mp3_path, wav_path):
                final_path = wav_path
                audio_codec = "wav"
                # Clean up MP3
                try:
                    mp3_path.unlink(missing_ok=True)
                except:
                    pass
            else:
                logger.info("Using MP3 format (install ffmpeg for WAV)")
            
            # Read audio file
            with open(final_path, "rb") as f:
                audio_data = f.read()
            
            # Send to bot
            success = self.recall_service.send_audio_to_bot(
                bot_id=bot_id,
                audio_data=audio_data,
                audio_codec=audio_codec,
                sample_rate=16000
            )
            
            elapsed = time.time() - start_time
            logger.info(
                f"Sent audio to bot {bot_id}: '{text[:50]}...' "
                f"({len(audio_data)} bytes, {elapsed:.2f}s)"
            )
            
            return success
            
        except Exception as e:
            logger.error(f"Failed to send audio to bot: {e}")
            return False
            
        finally:
            # Cleanup temp files
            try:
                mp3_path.unlink(missing_ok=True)
                wav_path.unlink(missing_ok=True)
            except:
                pass
    
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
