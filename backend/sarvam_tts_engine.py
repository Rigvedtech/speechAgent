"""
Sarvam AI TTS Engine (Bulbul V3)
Production-grade WebSocket-based text-to-speech with automatic fallback.
"""

import asyncio
import logging
import time
import json
import base64
from typing import Optional, Callable
from dataclasses import dataclass
from io import BytesIO

try:
    import websockets
    from websockets.client import WebSocketClientProtocol
except ImportError:
    websockets = None
    WebSocketClientProtocol = None

logger = logging.getLogger(__name__)


@dataclass
class SarvamTTSConfig:
    """Configuration for Sarvam TTS engine."""
    api_key: str
    model: str = "bulbul:v3"
    speaker: str = "shubh"
    language_code: str = "en-IN"
    sample_rate: int = 16000  # 8000, 16000, 22050, 24000
    pace: float = 1.2  # 0.5 to 2.0, higher = faster
    temperature: float = 0.6  # 0.01 to 1.0, higher = more variation
    min_buffer_size: int = 50  # 30-200, affects latency vs stability
    max_chunk_length: int = 150  # Max characters per chunk
    max_text_length: int = 2500  # Sarvam API limit
    max_retries: int = 3
    retry_base_seconds: float = 1.0


class SarvamTTSEngine:
    """
    WebSocket-based TTS engine using Sarvam AI Bulbul V3.
    
    Features:
    - Persistent WebSocket connection for low latency
    - Automatic text chunking for long text (>2500 chars)
    - Streaming PCM audio output at 16kHz
    - Automatic reconnection with exponential backoff
    - Production-grade error handling
    """
    
    WEBSOCKET_BASE_URL = "wss://api.sarvam.ai/text-to-speech/ws"
    
    def __init__(self, config: SarvamTTSConfig):
        """
        Initialize Sarvam TTS engine.
        
        Args:
            config: SarvamTTSConfig instance
        """
        if not websockets:
            raise ImportError("websockets package required for Sarvam TTS. Install with: pip install websockets")
        
        self.config = config
        self.ws: Optional[WebSocketClientProtocol] = None
        self.is_connected = False
        self.connection_lock = asyncio.Lock()
        self.retry_count = 0
        self.should_stop = False
        self._keepalive_task: Optional[asyncio.Task] = None
        self._streaming_task: Optional[asyncio.Task] = None
        self._connected_at: float = 0.0
        
        logger.info(
            f"Sarvam TTS initialized: model={config.model}, speaker={config.speaker}, "
            f"language={config.language_code}, sample_rate={config.sample_rate}Hz, "
            f"pace={config.pace}x, temperature={config.temperature}"
        )
    
    def _is_ws_closed(self) -> bool:
        """Check if WebSocket is closed (compatible with websockets 10.0+)."""
        if not self.ws:
            return True
        # In websockets 10.0+, check the state attribute
        try:
            # WebSocket has a state attribute (State enum)
            from websockets.protocol import State
            return self.ws.state != State.OPEN
        except (AttributeError, ImportError):
            # Fallback: assume closed if we can't check
            return True
    
    async def _stop_keepalive(self):
        """Cancel the application-level keepalive task."""
        if self._keepalive_task and not self._keepalive_task.done():
            self._keepalive_task.cancel()
            try:
                await self._keepalive_task
            except asyncio.CancelledError:
                pass
        self._keepalive_task = None

    async def _keepalive_loop(self):
        """
        Send Sarvam application-level pings to prevent idle disconnect.
        Sarvam closes connections after ~60s without config/text/ping messages.
        """
        try:
            while self.is_connected and not self.should_stop:
                await asyncio.sleep(20)
                if not self.is_connected or self._is_ws_closed():
                    break
                try:
                    await self.ws.send(json.dumps({"type": "ping"}))
                    logger.debug("Sent Sarvam TTS keepalive ping")
                except websockets.exceptions.ConnectionClosed:
                    logger.warning("Sarvam TTS keepalive failed — connection closed")
                    self.is_connected = False
                    break
                except Exception as e:
                    logger.warning(f"Sarvam TTS keepalive error: {e}")
                    self.is_connected = False
                    break
        except asyncio.CancelledError:
            pass

    async def _start_keepalive(self):
        """Start background keepalive pings."""
        await self._stop_keepalive()
        self._keepalive_task = asyncio.create_task(self._keepalive_loop())

    async def _stop_streaming_task(self):
        """Cancel any in-flight TTS synthesis task."""
        if self._streaming_task and not self._streaming_task.done():
            self._streaming_task.cancel()
            try:
                await self._streaming_task
            except asyncio.CancelledError:
                pass
        self._streaming_task = None

    async def _close_ws(self):
        """Close WebSocket and reset connection state."""
        await self._stop_streaming_task()
        await self._stop_keepalive()
        self.is_connected = False
        if self.ws and not self._is_ws_closed():
            try:
                await self.ws.close()
                await asyncio.sleep(0)
            except Exception:
                pass
        self.ws = None
    
    async def connect(self) -> bool:
        """
        Establish WebSocket connection to Sarvam AI.
        
        Returns:
            True if connected successfully
        """
        async with self.connection_lock:
            if self.is_connected and not self._is_ws_closed():
                return True
            
            try:
                # Build URL with model and completion event flag
                # send_completion_event=true ensures we get an explicit "final" event
                ws_url = f"{self.WEBSOCKET_BASE_URL}?model={self.config.model}&send_completion_event=true"
                logger.info(f"Connecting to Sarvam TTS at {ws_url}")
                start_time = time.time()
                
                # Connect with timeout
                # Note: In websockets 10.0+, use additional_headers instead of extra_headers
                # Sarvam API uses lowercase header name
                self.ws = await asyncio.wait_for(
                    websockets.connect(
                        ws_url,
                        additional_headers={
                            "api-subscription-key": self.config.api_key
                        },
                        ping_interval=20,
                        ping_timeout=10
                    ),
                    timeout=10.0
                )
                
                # Send initial configuration
                # IMPORTANT: Sarvam API requires config data inside a "data" object
                # Note: model must be in BOTH URL query param AND config_data
                is_v3 = "v3" in self.config.model
                
                # bulbul:v3 default sample rate is 24000 Hz per Sarvam docs
                sample_rate = self.config.sample_rate
                if is_v3 and sample_rate < 24000:
                    sample_rate = 24000
                    logger.debug(f"Using {sample_rate}Hz sample rate for bulbul:v3")
                
                config_data = {
                    "model": self.config.model,
                    "target_language_code": self.config.language_code,
                    "speaker": self.config.speaker,
                    "speech_sample_rate": sample_rate,
                    "pace": self.config.pace,
                    "output_audio_codec": "mp3",
                    "output_audio_bitrate": "128k",
                    "min_buffer_size": self.config.min_buffer_size,
                    "max_chunk_length": self.config.max_chunk_length,
                }
                
                # v3: preprocessing always enabled; v2: configurable
                if is_v3:
                    config_data["enable_preprocessing"] = True
                    config_data["temperature"] = self.config.temperature
                else:
                    config_data["enable_preprocessing"] = False
                
                config_message = {"type": "config", "data": config_data}
                
                logger.info(f"Sending Sarvam TTS config: speaker={self.config.speaker}, rate={sample_rate}Hz")
                await self.ws.send(json.dumps(config_message))
                
                # Sarvam API does NOT send config_ack (per official SDK/clients).
                # Only drain an immediate error if the server rejects config.
                try:
                    ack = await asyncio.wait_for(self.ws.recv(), timeout=1.0)
                    logger.info(f"Sarvam TTS config response: {ack}")
                    
                    if isinstance(ack, str):
                        ack_data = json.loads(ack)
                        if ack_data.get("type") == "error":
                            error_data = ack_data.get("data", {})
                            error_msg = error_data.get("message") or str(ack_data)
                            logger.error(f"Sarvam TTS config rejected: {error_msg}")
                            await self._close_ws()
                            return False
                except asyncio.TimeoutError:
                    # Normal — no ack expected, proceed to send text
                    logger.debug("No immediate config response (expected for Sarvam TTS)")
                
                elapsed = (time.time() - start_time) * 1000
                logger.info(
                    f"✓ Sarvam TTS connected successfully ({elapsed:.0f}ms) - "
                    f"Speaker: {self.config.speaker}"
                )
                
                self.is_connected = True
                self.retry_count = 0
                self._connected_at = time.time()
                await self._start_keepalive()
                return True
                
            except asyncio.TimeoutError:
                logger.error("Sarvam TTS connection timeout (10s)")
                self.is_connected = False
                return False
            except Exception as e:
                logger.error(f"Sarvam TTS connection failed: {e}")
                self.is_connected = False
                return False
    
    async def reconnect(self) -> bool:
        """
        Attempt to reconnect with exponential backoff.
        
        Returns:
            True if reconnected successfully
        """
        if self.retry_count >= self.config.max_retries:
            logger.error(
                f"Sarvam TTS max retries ({self.config.max_retries}) exceeded. "
                f"Fallback should be activated."
            )
            return False
        
        self.retry_count += 1
        wait_time = self.config.retry_base_seconds * (2 ** (self.retry_count - 1))
        
        logger.warning(
            f"Sarvam TTS reconnecting (attempt {self.retry_count}/{self.config.max_retries}) "
            f"after {wait_time:.1f}s..."
        )
        
        await asyncio.sleep(wait_time)
        return await self.connect()

    async def ensure_connected(self) -> bool:
        """
        Ensure a live WebSocket connection, reconnecting immediately if stale or closed.
        """
        if self.is_connected and not self._is_ws_closed():
            return True

        self.is_connected = False
        self.retry_count = 0
        return await self.connect()

    def update_language_code(self, language_code: str) -> None:
        self.config.language_code = language_code

    async def reconnect_with_settings(self) -> bool:
        """Close and reconnect so new language_code is used in the WebSocket URL."""
        await self.disconnect()
        self.is_connected = False
        self.retry_count = 0
        return await self.connect()
    
    def _split_text(self, text: str) -> list[str]:
        """
        Split text into chunks if > max_text_length.
        Splits at sentence boundaries to maintain naturalness.
        
        Args:
            text: Text to split
            
        Returns:
            List of text chunks
        """
        if len(text) <= self.config.max_text_length:
            return [text]
        
        import re
        
        # Split on sentence boundaries
        sentences = re.split(r'(?<=[.!?])\s+', text)
        
        chunks = []
        current_chunk = ""
        
        for sentence in sentences:
            if len(current_chunk) + len(sentence) + 1 <= self.config.max_text_length:
                current_chunk += " " + sentence if current_chunk else sentence
            else:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                current_chunk = sentence
        
        if current_chunk:
            chunks.append(current_chunk.strip())
        
        logger.debug(f"Split text into {len(chunks)} chunks (max {self.config.max_text_length} chars each)")
        return chunks
    
    async def speak(self, text: str, state=None) -> Optional[bytes]:
        """
        Convert text to speech and return MP3 audio.
        
        Args:
            text: Text to convert to speech
            state: Optional AgentState for interrupt checking
            
        Returns:
            MP3 audio bytes or None on failure
        """
        if not text or len(text.strip()) == 0:
            logger.warning("Empty text provided to Sarvam TTS")
            return None

        for attempt in range(2):
            if not await self.ensure_connected():
                return None

            self._streaming_task = asyncio.create_task(self._speak_once(text, state))
            try:
                result = await self._streaming_task
            except asyncio.CancelledError:
                logger.info("Sarvam TTS speak cancelled")
                return None
            finally:
                self._streaming_task = None

            if result is not None:
                return result

            if attempt == 0:
                logger.info("Sarvam TTS speak failed, reconnecting and retrying once...")
                self.is_connected = False
                await self._close_ws()
                continue

        return None

    async def _speak_once(self, text: str, state=None) -> Optional[bytes]:
        """Single attempt to synthesize text; returns None on failure."""
        try:
            # Check for interrupt before starting
            if state and state.interrupt_flag.is_set():
                logger.info("Sarvam TTS cancelled before starting (interrupt flag set)")
                return None
            
            # Split text if too long
            chunks = self._split_text(text)
            all_audio = BytesIO()
            
            for i, chunk in enumerate(chunks):
                # Check for interrupt between chunks
                if state and state.interrupt_flag.is_set():
                    logger.info(f"Sarvam TTS cancelled at chunk {i+1}/{len(chunks)}")
                    break
                
                # Send text chunk
                # Sarvam expects text in a "data" object with "text" field
                text_message = {
                    "type": "text",
                    "data": {
                        "text": chunk
                    }
                }
                
                logger.info(
                    f"[SARVAM TTS] Speaking ({i+1}/{len(chunks)}): '{chunk}'"
                )
                
                stt_start_time = time.time()
                logger.debug(f"Sending text message: {text_message}")
                await self.ws.send(json.dumps(text_message))
                
                # Send flush signal to process immediately
                flush_message = {"type": "flush"}
                logger.debug("Sending flush signal")
                await self.ws.send(json.dumps(flush_message))
                
                # Receive audio chunks with smart timeout
                first_chunk_time = None
                last_chunk_time = None
                chunk_audio = BytesIO()
                got_final_event = False
                
                while True:
                    # Check for interrupt during audio reception
                    if state and state.interrupt_flag.is_set():
                        logger.info("Sarvam TTS cancelled during audio reception")
                        return None
                    
                    # Use shorter timeout after receiving first chunk
                    # Long initial timeout (3s), short subsequent timeout (1s)
                    recv_timeout = 1.0 if first_chunk_time else 3.0
                    
                    try:
                        response = await asyncio.wait_for(self.ws.recv(), timeout=recv_timeout)
                        
                        # Sarvam returns JSON responses with audio as base64
                        if isinstance(response, str):
                            data = json.loads(response)
                            msg_type = data.get("type")
                            
                            if msg_type == "audio":
                                # Audio data is base64-encoded in data.audio
                                audio_data = data.get("data", {})
                                audio_b64 = audio_data.get("audio")
                                
                                if audio_b64:
                                    now = time.time()
                                    if first_chunk_time is None:
                                        first_chunk_time = now
                                        tts_first_chunk_latency = (first_chunk_time - stt_start_time) * 1000
                                        logger.info(f"TTS first chunk latency: {tts_first_chunk_latency:.0f}ms")
                                    
                                    last_chunk_time = now
                                    
                                    # Decode base64 to MP3 bytes
                                    audio_bytes = base64.b64decode(audio_b64)
                                    chunk_audio.write(audio_bytes)
                                    logger.debug(f"Received audio chunk: {len(audio_bytes)} bytes MP3")
                                    
                            elif msg_type == "event":
                                # Check if it's a final event (sent when send_completion_event=true)
                                event_data = data.get("data", {})
                                if event_data.get("event_type") == "final":
                                    logger.debug("Received final event from Sarvam TTS")
                                    got_final_event = True
                                    break
                                    
                            elif msg_type == "end":
                                # Explicit end message
                                logger.debug("Received end message from Sarvam TTS")
                                got_final_event = True
                                break
                                    
                            elif msg_type == "error":
                                # Log full error response for debugging
                                error_data = data.get("data", {})
                                error_msg = error_data.get("message") or data.get("message") or str(data)
                                logger.error(f"Sarvam TTS error: {error_msg}")
                                return None
                                
                            elif msg_type == "config_ack" or msg_type == "ack":
                                # Configuration acknowledged, continue
                                continue
                        
                        # Handle binary audio data (fallback, some versions may send raw)
                        elif isinstance(response, bytes):
                            now = time.time()
                            if first_chunk_time is None:
                                first_chunk_time = now
                                tts_first_chunk_latency = (first_chunk_time - stt_start_time) * 1000
                                logger.info(f"TTS first chunk latency: {tts_first_chunk_latency:.0f}ms")
                            
                            last_chunk_time = now
                            chunk_audio.write(response)
                            logger.debug(f"Received binary audio chunk: {len(response)} bytes")
                    
                    except asyncio.TimeoutError:
                        # Only warn if we haven't received any audio yet
                        if first_chunk_time is None:
                            logger.warning("Timeout waiting for first Sarvam TTS audio chunk")
                        else:
                            # Got audio and no more coming - this is normal completion
                            logger.debug("No more audio chunks (timeout after last chunk)")
                        break
                
                # Add chunk audio to total
                chunk_bytes = chunk_audio.getvalue()
                if chunk_bytes:
                    all_audio.write(chunk_bytes)
                    
                    total_latency = (time.time() - stt_start_time) * 1000
                    logger.info(
                        f"✓ Sarvam TTS chunk {i+1}/{len(chunks)} completed: "
                        f"{len(chunk_bytes)} bytes PCM, {total_latency:.0f}ms total"
                    )
            
            audio_bytes = all_audio.getvalue()
            
            if not audio_bytes:
                logger.error("No audio received from Sarvam TTS")
                return None
            
            logger.info(f"✓ Sarvam TTS completed: {len(audio_bytes)} total bytes MP3 audio")
            return audio_bytes
            
        except websockets.exceptions.ConnectionClosed:
            logger.warning("Sarvam TTS connection closed during speech")
            self.is_connected = False
            return None
        except Exception as e:
            logger.error(f"Error in Sarvam TTS speak: {e}", exc_info=True)
            return None
    
    async def _speak_once_streaming(self, text: str, state=None):
        """
        Async generator — yields raw MP3 byte chunks as Sarvam sends them.

        This is the streaming sibling of _speak_once().  Instead of collecting
        all audio and returning it as one blob, we yield each WebSocket audio
        message's bytes the instant it arrives so the caller can decode and send
        to the browser without waiting for the whole sentence.
        """
        if state and state.interrupt_flag.is_set():
            return

        chunks = self._split_text(text)

        for i, chunk_text in enumerate(chunks):
            if state and state.interrupt_flag.is_set():
                return

            text_message = {"type": "text", "data": {"text": chunk_text}}
            logger.info(
                f"[SARVAM TTS] Speaking ({i+1}/{len(chunks)}): "
                f"'{chunk_text[:50]}{'...' if len(chunk_text) > 50 else ''}'"
            )
            chunk_start = time.time()
            await self.ws.send(json.dumps(text_message))
            await self.ws.send(json.dumps({"type": "flush"}))

            first_chunk_time = None

            while True:
                if state and state.interrupt_flag.is_set():
                    return

                recv_timeout = 1.0 if first_chunk_time else 3.0

                try:
                    response = await asyncio.wait_for(
                        self.ws.recv(), timeout=recv_timeout
                    )

                    if isinstance(response, str):
                        data = json.loads(response)
                        msg_type = data.get("type")

                        if msg_type == "audio":
                            audio_b64 = data.get("data", {}).get("audio")
                            if audio_b64:
                                now = time.time()
                                if first_chunk_time is None:
                                    first_chunk_time = now
                                    logger.info(
                                        f"TTS first chunk latency: "
                                        f"{(now - chunk_start)*1000:.0f}ms"
                                    )
                                yield base64.b64decode(audio_b64)

                        elif msg_type == "event":
                            if data.get("data", {}).get("event_type") == "final":
                                break

                        elif msg_type == "end":
                            break

                        elif msg_type == "error":
                            error_msg = (
                                data.get("data", {}).get("message") or str(data)
                            )
                            logger.error(f"Sarvam TTS error: {error_msg}")
                            return

                        elif msg_type in ("config_ack", "ack"):
                            continue

                    elif isinstance(response, bytes):
                        now = time.time()
                        if first_chunk_time is None:
                            first_chunk_time = now
                            logger.info(
                                f"TTS first chunk latency: "
                                f"{(now - chunk_start)*1000:.0f}ms"
                            )
                        yield response

                except asyncio.TimeoutError:
                    if first_chunk_time is None:
                        logger.warning(
                            "Timeout waiting for first Sarvam TTS audio chunk"
                        )
                    break

            elapsed = (time.time() - chunk_start) * 1000
            logger.info(
                f"✓ Sarvam TTS chunk {i+1}/{len(chunks)} completed in {elapsed:.0f}ms"
            )

    async def speak_streaming_mp3(self, text: str, state=None):
        """
        Public async generator: yields raw MP3 byte chunks as they arrive from
        Sarvam.  Each yielded bytes object is one audio WebSocket message —
        caller decodes and streams to the browser without waiting for the full
        sentence.  Retries once on ConnectionClosed (mirrors speak()).
        """
        for attempt in range(2):
            if not await self.ensure_connected():
                return
            try:
                async for chunk in self._speak_once_streaming(text, state):
                    yield chunk
                return  # Completed successfully — exit retry loop
            except websockets.exceptions.ConnectionClosed:
                self.is_connected = False
                if attempt == 0:
                    logger.info(
                        "Sarvam TTS connection closed during streaming, "
                        "reconnecting once..."
                    )
                    await self._close_ws()
                    continue
                logger.error("Sarvam TTS streaming failed after reconnect")
                return
            except Exception as e:
                logger.error(f"Sarvam TTS streaming error: {e}", exc_info=True)
                return

    async def cancel(self):
        """Cancel current TTS operation (close and reconnect)."""
        logger.info("Cancelling Sarvam TTS operation")
        await self._close_ws()
    
    async def disconnect(self):
        """Cleanly disconnect from Sarvam AI."""
        self.should_stop = True
        await self._close_ws()
        logger.info("Sarvam TTS disconnected")


# Example usage
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    async def main():
        config = SarvamTTSConfig(
            api_key="your-api-key-here",
            model="bulbul:v3",
            speaker="shubh",
            language_code="en-IN"
        )
        
        engine = SarvamTTSEngine(config)
        
        # Connect
        if await engine.connect():
            print("Connected successfully")
            
            # Test TTS
            audio = await engine.speak("Hello, I am Prabhat. How are you today?")
            
            if audio:
                print(f"Received {len(audio)} bytes of audio")
                # Save to file for testing
                with open("test_sarvam_tts.raw", "wb") as f:
                    f.write(audio)
                print("Saved to test_sarvam_tts.raw (16kHz, mono, 16-bit PCM)")
            
            # Disconnect
            await engine.disconnect()
    
    asyncio.run(main())
