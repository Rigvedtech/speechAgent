"""
WebRTC Stream Manager
Handles real-time audio streaming to Recall.ai Output Media API via WebSocket.
Production-grade with connection management, error handling, and auto-reconnect.
"""

import os
import logging
import asyncio
import time
from typing import Optional, Callable
from io import BytesIO
import websockets
from pydub import AudioSegment

logger = logging.getLogger(__name__)


class WebRTCStreamManager:
    """
    Manages WebSocket connection for real-time PCM audio streaming to Recall.ai bot.
    
    Features:
    - MP3 to PCM conversion (16kHz, 16-bit, mono)
    - Real-time chunked streaming (20ms chunks)
    - Connection health monitoring
    - Automatic reconnection on failures
    - Graceful error handling
    """
    
    # Audio format constants (Recall.ai requirements)
    SAMPLE_RATE = 16000  # 16kHz
    SAMPLE_WIDTH = 2     # 16-bit
    CHANNELS = 1         # Mono
    CHUNK_DURATION_MS = 20  # 20ms chunks
    CHUNK_SIZE = int((SAMPLE_RATE * SAMPLE_WIDTH * CHANNELS * CHUNK_DURATION_MS) / 1000)  # 640 bytes
    
    def __init__(self, bot_id: str, media_url: str):
        """
        Initialize WebRTC stream manager.
        
        Args:
            bot_id: Bot ID
            media_url: WebSocket URL for Output Media API (from bot creation response)
        """
        self.bot_id = bot_id
        self.media_url = media_url
        self.websocket: Optional[websockets.WebSocketClientProtocol] = None
        self.is_connected = False
        self.is_streaming = False
        self.connection_lock = asyncio.Lock()
        self.reconnect_attempts = 0
        self.max_reconnect_attempts = 5
        self.last_activity_time = time.time()
        
        logger.info(f"WebRTC Stream Manager initialized for bot {bot_id[:8]}...")
    
    async def connect(self) -> bool:
        """
        Establish WebSocket connection to Recall.ai Output Media API.
        
        Returns:
            True if connected successfully
        """
        async with self.connection_lock:
            if self.is_connected and self.websocket:
                logger.debug(f"Bot {self.bot_id[:8]} already connected")
                return True
            
            try:
                logger.info(f"Connecting to Output Media API for bot {self.bot_id[:8]}...")
                
                # Connect with timeout
                self.websocket = await asyncio.wait_for(
                    websockets.connect(
                        self.media_url,
                        ping_interval=20,  # Keep-alive ping every 20s
                        ping_timeout=10,    # Timeout if no pong within 10s
                        close_timeout=5,
                        max_size=None       # No message size limit
                    ),
                    timeout=10.0
                )
                
                self.is_connected = True
                self.reconnect_attempts = 0
                self.last_activity_time = time.time()
                
                logger.info(f"✓ Bot {self.bot_id[:8]} connected to Output Media API")
                return True
                
            except asyncio.TimeoutError:
                logger.error(f"✗ Connection timeout for bot {self.bot_id[:8]}")
                return False
            except Exception as e:
                logger.error(f"✗ Connection failed for bot {self.bot_id[:8]}: {e}")
                return False
    
    async def disconnect(self):
        """Gracefully disconnect WebSocket."""
        async with self.connection_lock:
            if self.websocket and self.is_connected:
                try:
                    await asyncio.wait_for(
                        self.websocket.close(),
                        timeout=5.0
                    )
                    logger.info(f"Disconnected bot {self.bot_id[:8]} from Output Media API")
                except Exception as e:
                    logger.warning(f"Error disconnecting bot {self.bot_id[:8]}: {e}")
                finally:
                    self.websocket = None
                    self.is_connected = False
    
    def convert_mp3_to_pcm(self, mp3_data: bytes) -> bytes:
        """
        Convert MP3 audio to 16kHz 16-bit mono PCM (required by Recall.ai).
        
        Args:
            mp3_data: MP3 audio data
            
        Returns:
            PCM audio data (raw bytes)
        """
        try:
            # Load MP3 from bytes
            audio = AudioSegment.from_mp3(BytesIO(mp3_data))
            
            # Convert to required format
            audio = audio.set_frame_rate(self.SAMPLE_RATE)  # 16kHz
            audio = audio.set_channels(self.CHANNELS)        # Mono
            audio = audio.set_sample_width(self.SAMPLE_WIDTH)  # 16-bit
            
            # Export as raw PCM
            pcm_data = audio.raw_data
            
            logger.debug(
                f"Converted MP3 ({len(mp3_data)} bytes) to PCM ({len(pcm_data)} bytes) "
                f"for bot {self.bot_id[:8]}"
            )
            
            return pcm_data
            
        except Exception as e:
            logger.error(f"Failed to convert MP3 to PCM for bot {self.bot_id[:8]}: {e}")
            raise
    
    async def stream_pcm_audio(self, pcm_data: bytes, state = None) -> bool:
        """
        Stream PCM audio in real-time chunks (20ms each).
        Simulates real-time audio by spacing chunks appropriately.
        FIX 3: Add interrupt check inside the chunk send loop.
        
        Args:
            pcm_data: PCM audio data (16kHz, 16-bit, mono)
            state: Optional AgentState for interrupt checking
            
        Returns:
            True if streaming successful
        """
        if not self.is_connected or not self.websocket:
            logger.error(f"Bot {self.bot_id[:8]} not connected. Attempting reconnect...")
            connected = await self.connect()
            if not connected:
                return False
        
        try:
            self.is_streaming = True
            total_chunks = len(pcm_data) // self.CHUNK_SIZE
            
            logger.info(
                f"Streaming {len(pcm_data)} bytes PCM audio to bot {self.bot_id[:8]} "
                f"({total_chunks} chunks @ 20ms each = {total_chunks * 0.02:.2f}s)"
            )
            
            start_time = time.time()
            
            # Stream in 20ms chunks
            for i in range(0, len(pcm_data), self.CHUNK_SIZE):
                # FIX 3: Check for interrupt at the top of each iteration
                if state and state.interrupt_flag.is_set():
                    logger.info(f"Bot {self.bot_id[:8]} interrupted during PCM streaming")
                    break
                    
                chunk = pcm_data[i:i + self.CHUNK_SIZE]
                
                # Pad last chunk if needed (must be exactly CHUNK_SIZE)
                if len(chunk) < self.CHUNK_SIZE:
                    chunk += b'\x00' * (self.CHUNK_SIZE - len(chunk))
                
                # Send chunk via WebSocket
                await self.websocket.send(chunk)
                
                # Rate limiting: Wait 20ms between chunks to simulate real-time
                # This prevents sending audio too fast and causing playback issues
                await asyncio.sleep(0.02)  # 20ms
                
                self.last_activity_time = time.time()
            
            elapsed = time.time() - start_time
            
            logger.info(
                f"✓ Streamed {total_chunks} chunks to bot {self.bot_id[:8]} in {elapsed:.2f}s "
                f"(expected: {total_chunks * 0.02:.2f}s)"
            )
            
            self.is_streaming = False
            return True
            
        except websockets.exceptions.ConnectionClosed as e:
            logger.error(f"✗ WebSocket closed during streaming for bot {self.bot_id[:8]}: {e}")
            self.is_connected = False
            self.is_streaming = False
            return False
        except Exception as e:
            logger.error(f"✗ Streaming failed for bot {self.bot_id[:8]}: {e}", exc_info=True)
            self.is_streaming = False
            return False
    
    async def stream_audio_from_mp3(self, mp3_data: bytes, state = None) -> bool:
        """
        High-level method: Convert MP3 to PCM and stream in real-time.
        
        Args:
            mp3_data: MP3 audio data
            state: Optional AgentState for interrupt checking
            
        Returns:
            True if successful
        """
        try:
            # Convert MP3 to PCM
            pcm_data = self.convert_mp3_to_pcm(mp3_data)
            
            # Stream PCM in real-time chunks with interrupt checking
            success = await self.stream_pcm_audio(pcm_data, state)
            
            return success
            
        except Exception as e:
            logger.error(f"Failed to stream MP3 audio for bot {self.bot_id[:8]}: {e}")
            return False
    
    def is_healthy(self) -> bool:
        """
        Check if WebSocket connection is healthy.
        
        Returns:
            True if connection is healthy and active
        """
        if not self.is_connected or not self.websocket:
            return False
        
        # Check if connection is stale (no activity for 60s)
        if time.time() - self.last_activity_time > 60:
            logger.warning(f"Bot {self.bot_id[:8]} connection appears stale")
            return False
        
        # Check WebSocket state
        if self.websocket.closed:
            logger.warning(f"Bot {self.bot_id[:8]} WebSocket is closed")
            self.is_connected = False
            return False
        
        return True
    
    async def ensure_connected(self) -> bool:
        """
        Ensure WebSocket is connected, reconnect if needed.
        
        Returns:
            True if connected
        """
        if self.is_healthy():
            return True
        
        logger.info(f"Reconnecting bot {self.bot_id[:8]}...")
        return await self.connect()


# Example usage
if __name__ == "__main__":
    import sys
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    async def test_streaming():
        # Example: Stream audio to a bot
        bot_id = "test-bot-123"
        media_url = "wss://us-west-2.recall.ai/bot/test-bot-123/output_media/stream"
        
        manager = WebRTCStreamManager(bot_id, media_url)
        
        # Connect
        connected = await manager.connect()
        if not connected:
            print("Failed to connect")
            return
        
        # Read MP3 file
        with open("test_audio.mp3", "rb") as f:
            mp3_data = f.read()
        
        # Stream audio
        success = await manager.stream_audio_from_mp3(mp3_data)
        print(f"Streaming result: {success}")
        
        # Disconnect
        await manager.disconnect()
    
    # Run test
    asyncio.run(test_streaming())
