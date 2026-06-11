"""
Sarvam AI STT Engine (Saaras V3)
Production-grade WebSocket-based speech-to-text with automatic fallback.

Usage (Recall/session mode):
    engine = SarvamSTTEngine(config)
    engine.start_session_loop()          # connect once, keepalive in background
    transcript = engine.transcribe_sync(audio_float32)  # call from STT thread
    engine.stop_session_loop()           # on session teardown

Usage (standalone streaming):
    engine.start_listener_thread(audio_queue, state)
"""

import asyncio
import logging
import time
import json
import base64
import threading
from typing import Optional, Callable
from dataclasses import dataclass

try:
    import websockets
    from websockets.client import WebSocketClientProtocol
except ImportError:
    websockets = None
    WebSocketClientProtocol = None

try:
    import numpy as np
except ImportError:
    np = None

logger = logging.getLogger(__name__)


@dataclass
class SarvamSTTConfig:
    """Configuration for Sarvam STT engine."""
    api_key: str
    model: str = "saaras:v3"
    language_code: str = "en-IN"
    mode: str = "transcribe"  # transcribe, translate, verbatim, translit, codemix
    sample_rate: int = 16000
    high_vad_sensitivity: bool = True
    flush_signal: bool = True
    max_retries: int = 3
    retry_base_seconds: float = 1.0


class SarvamSTTEngine:
    """
    WebSocket-based STT engine using Sarvam AI Saaras V3.
    
    Features:
    - Persistent WebSocket connection for low latency
    - Automatic reconnection with exponential backoff
    - Real-time streaming transcription
    - Production-grade error handling
    """
    
    WEBSOCKET_URL = "wss://api.sarvam.ai/speech-to-text/ws"
    
    def __init__(self, config: SarvamSTTConfig, on_transcript: Optional[Callable[[str, bool], None]] = None):
        """
        Initialize Sarvam STT engine.
        
        Args:
            config: SarvamSTTConfig instance
            on_transcript: Optional callback(text, is_final) — used in streaming mode
        """
        if not websockets:
            raise ImportError("websockets package required for Sarvam STT. Install with: pip install websockets")
        
        self.config = config
        self.on_transcript = on_transcript
        self.ws: Optional[WebSocketClientProtocol] = None
        self.is_connected = False
        self.connection_lock = asyncio.Lock()
        self.retry_count = 0
        self.should_stop = False

        # Background event loop — used by session mode (start_session_loop / transcribe_sync)
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._loop_thread: Optional[threading.Thread] = None
        self._keepalive_task: Optional[asyncio.Task] = None
        
        logger.info(
            f"Sarvam STT initialized: model={config.model}, "
            f"language={config.language_code}, mode={config.mode}, "
            f"sample_rate={config.sample_rate}Hz"
        )
    
    def _is_ws_closed(self) -> bool:
        """Check if WebSocket is closed (compatible with websockets 10.0+)."""
        if not self.ws:
            return True
        # In websockets 10.0+, check the state attribute
        try:
            from websockets.protocol import State
            return self.ws.state != State.OPEN
        except (AttributeError, ImportError):
            # Fallback: assume closed if we can't check
            return True
    
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
                logger.info(f"Connecting to Sarvam STT at {self.WEBSOCKET_URL}")
                start_time = time.time()
                
                # Connect with timeout
                # Note: In websockets 10.0+, use additional_headers instead of extra_headers
                # Sarvam API uses lowercase header name
                self.ws = await asyncio.wait_for(
                    websockets.connect(
                        self.WEBSOCKET_URL,
                        additional_headers={
                            "api-subscription-key": self.config.api_key
                        },
                        ping_interval=20,
                        ping_timeout=10
                    ),
                    timeout=10.0
                )
                
                # Send initial configuration
                config_message = {
                    "model": self.config.model,
                    "language_code": self.config.language_code,
                    "mode": self.config.mode,
                    "sample_rate": self.config.sample_rate,
                    "high_vad_sensitivity": self.config.high_vad_sensitivity,
                    "flush_signal": self.config.flush_signal
                }
                
                await self.ws.send(json.dumps(config_message))
                
                elapsed = (time.time() - start_time) * 1000
                logger.info(f"✓ Sarvam STT connected successfully ({elapsed:.0f}ms)")
                
                self.is_connected = True
                self.retry_count = 0
                return True
                
            except asyncio.TimeoutError:
                logger.error("Sarvam STT connection timeout (10s)")
                self.is_connected = False
                return False
            except Exception as e:
                logger.error(f"Sarvam STT connection failed: {e}")
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
                f"Sarvam STT max retries ({self.config.max_retries}) exceeded. "
                f"Fallback should be activated."
            )
            return False
        
        self.retry_count += 1
        wait_time = self.config.retry_base_seconds * (2 ** (self.retry_count - 1))
        
        logger.warning(
            f"Sarvam STT reconnecting (attempt {self.retry_count}/{self.config.max_retries}) "
            f"after {wait_time:.1f}s..."
        )
        
        await asyncio.sleep(wait_time)
        return await self.connect()
    
    async def ensure_connected(self) -> bool:
        """Ensure a live WebSocket connection, reconnecting immediately if stale."""
        if self.is_connected and not self._is_ws_closed():
            return True
        self.is_connected = False
        self.retry_count = 0
        return await self.connect()

    # ── Background-loop helpers (session mode) ────────────────────────────────

    async def _keepalive_loop(self):
        """
        Send 100 ms of silence every 20 s to prevent Sarvam's ~60 s idle disconnect.
        Reconnects automatically if the connection is found closed.
        """
        SILENCE_100MS = b'\x00' * (self.config.sample_rate * 2 // 10)  # 100 ms S16LE
        try:
            while not self.should_stop:
                await asyncio.sleep(20)
                if self.should_stop:
                    break
                if self._is_ws_closed():
                    logger.info("Sarvam STT connection lost — reconnecting in keepalive")
                    await self.connect()
                    continue
                try:
                    b64 = base64.b64encode(SILENCE_100MS).decode()
                    await self.ws.send(json.dumps({
                        "audio": b64,
                        "encoding": "pcm_s16le",
                        "sample_rate": self.config.sample_rate,
                    }))
                    # Drain any spurious partial-transcript from the silence
                    try:
                        await asyncio.wait_for(self.ws.recv(), timeout=0.5)
                    except asyncio.TimeoutError:
                        pass
                    logger.debug("Sarvam STT keepalive sent")
                except Exception as e:
                    logger.warning(f"Sarvam STT keepalive failed: {e}")
                    self.is_connected = False
        except asyncio.CancelledError:
            pass

    async def _connect_with_keepalive(self) -> bool:
        """Connect and immediately start the keepalive task."""
        connected = await self.connect()
        if connected and self._loop:
            if self._keepalive_task and not self._keepalive_task.done():
                self._keepalive_task.cancel()
            self._keepalive_task = asyncio.ensure_future(self._keepalive_loop())
        return connected

    def _run_background_loop(self):
        """Thread target: run the asyncio event loop forever."""
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def start_session_loop(self):
        """
        Start the persistent background event loop and connect once.
        Call this after creating the engine for a new bot session.
        The loop stays alive for the entire session, keeping the WS warm.
        """
        self._loop = asyncio.new_event_loop()
        self._loop_thread = threading.Thread(
            target=self._run_background_loop,
            daemon=True,
            name="SarvamSTT-Loop",
        )
        self._loop_thread.start()

        # Block until connected (max 12 s) so the first transcription is fast
        future = asyncio.run_coroutine_threadsafe(
            self._connect_with_keepalive(), self._loop
        )
        try:
            connected = future.result(timeout=12)
            if connected:
                logger.info("✓ Sarvam STT session loop started and connected")
            else:
                logger.warning("Sarvam STT session loop started but initial connect failed")
        except Exception as e:
            logger.warning(f"Sarvam STT session loop start error: {e}")

    def stop_session_loop(self):
        """Cleanly stop the background event loop and disconnect."""
        self.should_stop = True
        if self._loop and self._loop.is_running():
            future = asyncio.run_coroutine_threadsafe(self.disconnect(), self._loop)
            try:
                future.result(timeout=3)
            except Exception:
                pass
            self._loop.call_soon_threadsafe(self._loop.stop)
        if self._loop_thread:
            self._loop_thread.join(timeout=3)

    def transcribe_sync(
        self,
        audio_float32,
        sample_rate: int = 16000,
        timeout: float = 8.0,
    ) -> Optional[str]:
        """
        Synchronous transcription entry-point — safe to call from any thread.
        Converts float32 audio → S16LE PCM, sends to Sarvam, flushes, and
        blocks until the final transcript arrives (or timeout).

        Args:
            audio_float32: numpy float32 array, normalised to [-1, 1]
            sample_rate:   audio sample rate in Hz (default 16000)
            timeout:       max seconds to wait for transcript

        Returns:
            Transcript string, or None on failure (caller should fall back to Whisper)
        """
        if not self._loop or not self._loop.is_running():
            logger.warning("Sarvam STT session loop not running — skipping")
            return None
        if np is None:
            logger.error("numpy not available for Sarvam STT float→int16 conversion")
            return None

        # float32 → int16 PCM (S16LE)
        audio_int16 = (audio_float32 * 32767.0).clip(-32768, 32767).astype(np.int16)
        audio_bytes = audio_int16.tobytes()

        future = asyncio.run_coroutine_threadsafe(
            self._transcribe_batch(audio_bytes, sample_rate), self._loop
        )
        try:
            return future.result(timeout=timeout)
        except Exception as e:
            logger.warning(f"Sarvam STT transcribe_sync error: {e}")
            return None

    async def _transcribe_batch(self, audio_bytes: bytes, sample_rate: int) -> Optional[str]:
        """
        Send accumulated PCM audio in chunks, send flush, await final transcript.

        The connection may be shared across utterances.  Each flush signals Sarvam
        to finalise the current utterance; the connection is then ready for the next.
        """
        if not await self.ensure_connected():
            logger.error("Sarvam STT not connected for batch transcription")
            return None

        try:
            # Send audio in 100 ms chunks (Sarvam recommendation)
            CHUNK_BYTES = sample_rate * 2 // 10  # 100 ms at sample_rate, 16-bit
            sent_chunks = 0
            for offset in range(0, len(audio_bytes), CHUNK_BYTES):
                chunk = audio_bytes[offset : offset + CHUNK_BYTES]
                b64 = base64.b64encode(chunk).decode('utf-8')
                await self.ws.send(json.dumps({
                    "audio": b64,
                    "encoding": "pcm_s16le",
                    "sample_rate": sample_rate,
                }))
                sent_chunks += 1

            # Flush — tells Sarvam to finalise this utterance
            await self.ws.send(json.dumps({"flush": True}))
            logger.debug(f"Sarvam STT: sent {sent_chunks} chunks + flush ({len(audio_bytes)} bytes)")

            # Collect responses until is_final or timeout
            best_transcript = ""
            deadline = time.monotonic() + 5.0

            while time.monotonic() < deadline:
                remaining = max(0.1, deadline - time.monotonic())
                try:
                    raw = await asyncio.wait_for(self.ws.recv(), timeout=min(remaining, 2.0))
                    data = json.loads(raw)
                    transcript = (data.get("transcript") or "").strip()
                    is_final = bool(data.get("is_final", False))

                    if transcript:
                        best_transcript = transcript
                        if self.on_transcript:
                            self.on_transcript(transcript, is_final)

                    if is_final:
                        logger.info(f"[Sarvam STT] Final transcript: '{best_transcript}'")
                        return best_transcript or None

                except asyncio.TimeoutError:
                    # No more messages within the window — return best result so far
                    break

            if best_transcript:
                logger.info(f"[Sarvam STT] Returning best transcript (no is_final): '{best_transcript}'")
            return best_transcript or None

        except websockets.exceptions.ConnectionClosed:
            logger.warning("Sarvam STT connection closed during _transcribe_batch")
            self.is_connected = False
            return None
        except Exception as e:
            logger.error(f"Sarvam STT _transcribe_batch error: {e}", exc_info=True)
            return None

    async def send_audio_chunk(self, audio_pcm: bytes) -> bool:
        """
        Send raw PCM audio chunk to Sarvam for transcription.
        
        Args:
            audio_pcm: Raw PCM audio bytes (16kHz, mono, 16-bit)
            
        Returns:
            True if sent successfully
        """
        if not self.is_connected or self._is_ws_closed():
            logger.debug("Sarvam STT not connected, attempting reconnect...")
            if not await self.reconnect():
                return False
        
        try:
            # Sarvam requires base64-encoded audio
            audio_b64 = base64.b64encode(audio_pcm).decode('utf-8')
            
            audio_message = {
                "audio": audio_b64,
                "encoding": "pcm_s16le",  # 16-bit PCM little-endian
                "sample_rate": self.config.sample_rate
            }
            
            start_time = time.time()
            await self.ws.send(json.dumps(audio_message))
            
            elapsed = (time.time() - start_time) * 1000
            logger.debug(
                f"Sent {len(audio_pcm)} bytes to Sarvam STT "
                f"({len(audio_b64)} b64 chars, {elapsed:.1f}ms)"
            )
            
            return True
            
        except websockets.exceptions.ConnectionClosed:
            logger.warning("Sarvam STT connection closed, will reconnect")
            self.is_connected = False
            return False
        except Exception as e:
            logger.error(f"Error sending audio to Sarvam STT: {e}")
            return False
    
    async def receive_transcript(self) -> Optional[dict]:
        """
        Receive transcript from Sarvam AI.
        
        Returns:
            Dict with transcript data or None if connection failed
        """
        if not self.is_connected or self._is_ws_closed():
            return None
        
        try:
            response = await asyncio.wait_for(self.ws.recv(), timeout=5.0)
            data = json.loads(response)
            
            # Log transcript received
            if "transcript" in data:
                is_final = data.get("is_final", False)
                transcript = data["transcript"]
                
                logger.info(
                    f"[SARVAM TRANSCRIPT{' (FINAL)' if is_final else ' (INTERIM)'}]: {transcript}"
                )
                
                if self.on_transcript:
                    self.on_transcript(transcript, is_final)
            
            return data
            
        except asyncio.TimeoutError:
            logger.debug("Sarvam STT receive timeout (no response in 5s)")
            return None
        except websockets.exceptions.ConnectionClosed:
            logger.warning("Sarvam STT connection closed during receive")
            self.is_connected = False
            return None
        except Exception as e:
            logger.error(f"Error receiving from Sarvam STT: {e}")
            return None
    
    async def flush(self):
        """Signal Sarvam to process any buffered audio immediately."""
        if self.is_connected and not self._is_ws_closed():
            try:
                await self.ws.send(json.dumps({"flush": True}))
                logger.debug("Sent flush signal to Sarvam STT")
            except Exception as e:
                logger.error(f"Error flushing Sarvam STT: {e}")
    
    async def disconnect(self):
        """Cleanly disconnect from Sarvam AI."""
        self.should_stop = True
        
        if not self._is_ws_closed():
            try:
                await self.ws.close()
                logger.info("Sarvam STT disconnected")
            except Exception as e:
                logger.error(f"Error disconnecting Sarvam STT: {e}")
        
        self.is_connected = False
    
    def start_listener_thread(self, audio_queue, state):
        """
        Start background thread to process audio from queue and send to Sarvam.
        
        Args:
            audio_queue: Queue containing numpy audio arrays
            state: AgentState for coordination
        """
        def listener():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            try:
                loop.run_until_complete(self._listen_loop(audio_queue, state))
            finally:
                loop.close()
        
        thread = threading.Thread(target=listener, daemon=True, name="Sarvam-STT-Listener")
        thread.start()
        logger.info("Started Sarvam STT listener thread")
        return thread
    
    async def _listen_loop(self, audio_queue, state):
        """Async loop to process audio queue and send to Sarvam."""
        # Connect initially
        if not await self.connect():
            logger.error("Failed to connect Sarvam STT, listener will not start")
            return
        
        while not self.should_stop and state.is_running:
            try:
                # Get audio from queue (non-blocking)
                try:
                    audio_chunk = audio_queue.get(timeout=0.1)
                except:
                    continue
                
                # Convert numpy array to bytes if needed
                if hasattr(audio_chunk, 'tobytes'):
                    audio_bytes = audio_chunk.tobytes()
                else:
                    audio_bytes = audio_chunk
                
                # Send to Sarvam
                success = await self.send_audio_chunk(audio_bytes)
                
                if not success:
                    logger.warning("Failed to send audio to Sarvam STT")
                
            except Exception as e:
                logger.error(f"Error in Sarvam STT listen loop: {e}")
                await asyncio.sleep(1.0)


# Example usage
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    async def main():
        def on_transcript(text: str, is_final: bool):
            print(f"{'[FINAL]' if is_final else '[INTERIM]'} {text}")
        
        config = SarvamSTTConfig(
            api_key="your-api-key-here",
            model="saaras:v3",
            language_code="en-IN"
        )
        
        engine = SarvamSTTEngine(config, on_transcript=on_transcript)
        
        # Connect
        if await engine.connect():
            print("Connected successfully")
            
            # Test with dummy audio
            dummy_audio = b'\x00' * 3200  # 100ms of silence at 16kHz
            await engine.send_audio_chunk(dummy_audio)
            
            # Wait for response
            await asyncio.sleep(2)
            
            # Disconnect
            await engine.disconnect()
    
    asyncio.run(main())
