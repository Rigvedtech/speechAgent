"""
Audio Sender
Handles TTS audio generation and sending to Recall.ai bot for playback in meeting.
Supports both Output Media API (WebRTC streaming) and output_audio API (file upload).
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
    """
    Generate TTS audio and send to Recall.ai bot.
    
    Supports two output methods:
    - WebRTC streaming (Output Media API) for low latency (<1.5s)
    - File upload (output_audio API) for fallback/compatibility (4-8s latency)
    """
    
    def __init__(
        self,
        recall_service: RecallBotService,
        voice: str = "en-IN-PrabhatNeural",
        rate: str = "+35%",
        reduce_pauses: bool = True,
        webrtc_manager: Optional[any] = None  # WebRTCStreamManager instance
    ):
        """
        Initialize audio sender.
        
        Args:
            recall_service: RecallBotService instance
            voice: Edge-TTS voice name
            rate: Speech rate adjustment (+35% = 35% faster)
            reduce_pauses: If True, reduces pauses at sentence boundaries
            webrtc_manager: Optional WebRTCStreamManager for Output Media API
        """
        self.recall_service = recall_service
        self.voice = voice
        self.rate = rate
        self.reduce_pauses = reduce_pauses
        self.webrtc_manager = webrtc_manager
        self.temp_dir = Path("tmp_audio")
        self.temp_dir.mkdir(exist_ok=True)
        
        # Determine output method
        self.use_webrtc = webrtc_manager is not None
        
        if self.use_webrtc:
            logger.info(f"AudioSender initialized with WebRTC streaming (low latency mode)")
        else:
            logger.info(f"AudioSender initialized with file upload (legacy mode)")
    
    def _preprocess_text_for_tts(self, text: str) -> str:
        """
        Preprocess text to reduce pauses at full stops.
        Edge-TTS adds ~800ms pause at each full stop - we reduce this.
        
        Args:
            text: Original text
            
        Returns:
            Processed text with reduced pauses
        """
        if not self.reduce_pauses:
            return text
        
        # Replace ". " with ", " to reduce pause duration
        # Full stop triggers 800ms pause, comma triggers 300ms pause
        # Keep final full stop to maintain natural ending
        sentences = text.split('. ')
        
        if len(sentences) <= 1:
            return text
        
        # Join with commas except the last sentence
        processed = ', '.join(sentences[:-1])
        
        # Add back the last sentence with its full stop
        if sentences[-1]:
            processed += '. ' + sentences[-1]
        
        return processed
    
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
        
        Automatically chooses best method:
        - WebRTC streaming if webrtc_manager is available (low latency)
        - File upload if webrtc_manager is None (legacy/fallback)
        
        Args:
            bot_id: Bot ID to send audio to
            text: Text to speak
            
        Returns:
            True if all audio sent successfully
        """
        if self.use_webrtc and self.webrtc_manager:
            return await self._send_via_webrtc(bot_id, text)
        else:
            return await self._send_via_file_upload(bot_id, text)
    
    async def _send_via_webrtc(self, bot_id: str, text: str) -> bool:
        """
        Send audio via WebRTC streaming (Output Media API).
        Low latency (<1.5s), real-time streaming.
        
        Args:
            bot_id: Bot ID
            text: Text to speak
            
        Returns:
            True if successful
        """
        import uuid
        import time
        import re
        
        start_time = time.time()
        
        # Preprocess text
        text = self._preprocess_text_for_tts(text)
        text = re.sub(r'\s+', ' ', text.strip())
        
        # For WebRTC, we stream sentence-by-sentence for lower perceived latency
        sentences = re.split(r'(?<=[.!?])\s+', text)
        
        # Merge very short sentences
        merged_sentences = []
        buffer = ""
        for sentence in sentences:
            if len(buffer) > 0:
                buffer += " " + sentence
            else:
                buffer = sentence
            
            if len(buffer) > 30 or sentence == sentences[-1]:
                merged_sentences.append(buffer.strip())
                buffer = ""
        
        if not merged_sentences:
            return False
        
        all_success = True
        total_bytes = 0
        
        try:
            # Ensure WebRTC connection is established
            connected = await self.webrtc_manager.ensure_connected()
            if not connected:
                logger.error(f"Failed to connect WebRTC for bot {bot_id[:8]}")
                # Fallback to file upload
                logger.warning(f"Falling back to file upload for bot {bot_id[:8]}")
                return await self._send_via_file_upload(bot_id, text)
            
            for i, sentence in enumerate(merged_sentences):
                if not sentence.strip():
                    continue
                
                filename = f"tts_{uuid.uuid4().hex[:8]}"
                mp3_path = self.temp_dir / f"{filename}.mp3"
                
                try:
                    # Generate MP3
                    success = await self.generate_audio(sentence, mp3_path)
                    if not success:
                        logger.error(f"Failed to generate TTS for sentence {i+1}")
                        all_success = False
                        continue
                    
                    # Read MP3
                    with open(mp3_path, "rb") as f:
                        mp3_data = f.read()
                    
                    total_bytes += len(mp3_data)
                    
                    # Stream via WebRTC
                    success = await self.webrtc_manager.stream_audio_from_mp3(mp3_data)
                    
                    if not success:
                        logger.error(f"Failed to stream sentence {i+1} via WebRTC")
                        all_success = False
                    
                except Exception as e:
                    logger.error(f"Error processing sentence {i+1}: {e}")
                    all_success = False
                
                finally:
                    # Cleanup
                    try:
                        mp3_path.unlink(missing_ok=True)
                    except Exception:
                        pass
            
            elapsed = time.time() - start_time
            
            if all_success:
                logger.info(
                    f"✓ Streamed {len(merged_sentences)} sentences via WebRTC to bot {bot_id[:8]}: "
                    f"'{text[:40]}...' ({total_bytes} bytes, {elapsed:.2f}s)"
                )
            else:
                logger.warning(f"Partially streamed audio via WebRTC to bot {bot_id[:8]}")
            
            return all_success
            
        except Exception as e:
            logger.error(f"WebRTC streaming failed for bot {bot_id}: {e}", exc_info=True)
            return False
    
    async def _send_via_file_upload(self, bot_id: str, text: str) -> bool:
        """
        Send audio via file upload (output_audio API).
        Legacy/fallback method. Higher latency (4-8s).
        Uses sentence-level streaming for faster perceived latency.
        
        Args:
            bot_id: Bot ID to send audio to
            text: Text to speak
            
        Returns:
            True if all audio sent successfully
        """
        import uuid
        import time
        import re
        
        start_time = time.time()
        
        # Preprocess text to reduce pauses
        text = self._preprocess_text_for_tts(text)
        
        # Remove extra spaces and normalize punctuation
        text = re.sub(r'\s+', ' ', text.strip())
        
        # Split on sentence boundaries but keep short sentences together
        sentences = re.split(r'(?<=[.!?])\s+', text)
        
        # Merge very short sentences (< 10 chars) with next to reduce pauses
        merged_sentences = []
        buffer = ""
        for sentence in sentences:
            if len(buffer) > 0:
                buffer += " " + sentence
            else:
                buffer = sentence
            
            # Send if buffer is substantial (> 30 chars) or it's the last sentence
            if len(buffer) > 30 or sentence == sentences[-1]:
                merged_sentences.append(buffer.strip())
                buffer = ""
        
        if not merged_sentences:
            return False
        
        all_success = True
        total_bytes = 0
        
        try:
            for i, sentence in enumerate(merged_sentences):
                if not sentence.strip():
                    continue
                
                # Generate unique filename for each sentence
                filename = f"tts_{uuid.uuid4().hex[:8]}"
                mp3_path = self.temp_dir / f"{filename}.mp3"
                
                try:
                    # Generate MP3 for this sentence
                    success = await self.generate_audio(sentence, mp3_path)
                    if not success:
                        logger.error(f"Failed to generate TTS for sentence {i+1}: {sentence[:30]}")
                        all_success = False
                        continue
                    
                    # Verify file exists and has content
                    if not mp3_path.exists() or mp3_path.stat().st_size == 0:
                        logger.error(f"Generated audio file is empty: {mp3_path}")
                        all_success = False
                        continue
                    
                    # Read audio file
                    with open(mp3_path, "rb") as f:
                        audio_data = f.read()
                    
                    total_bytes += len(audio_data)
                    
                    # Send to bot immediately (streaming approach)
                    success = self.recall_service.send_audio_to_bot(
                        bot_id=bot_id,
                        audio_data=audio_data,
                        audio_codec="mp3"
                    )
                    
                    if not success:
                        logger.error(f"Failed to send sentence {i+1} to bot: {sentence[:30]}")
                        all_success = False
                    
                except Exception as e:
                    logger.error(f"Error processing sentence {i+1}: {e}")
                    all_success = False
                
                finally:
                    # Cleanup temp file for this sentence
                    try:
                        mp3_path.unlink(missing_ok=True)
                    except Exception:
                        pass
            
            elapsed = time.time() - start_time
            
            if all_success:
                logger.info(
                    f"Sent {len(merged_sentences)} sentences to bot {bot_id[:8]}: '{text[:40]}...' "
                    f"({total_bytes} bytes, {elapsed:.2f}s)"
                )
            else:
                logger.warning(
                    f"Partially sent audio to bot {bot_id[:8]} (some sentences failed)"
                )
            
            return all_success
            
        except Exception as e:
            logger.error(f"Failed to send audio to bot: {e}", exc_info=True)
            return False
    
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
