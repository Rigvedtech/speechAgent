"""
Sarvam AI STT Engine (Saaras V3)
Production-grade WebSocket-based speech-to-text with automatic fallback.

Usage (Recall/session mode):
    engine = SarvamSTTEngine(config)
    engine.start_session_loop()          # connect once, reader in background
    transcript = engine.transcribe_sync(audio_float32)  # call from STT thread
    engine.stop_session_loop()           # on session teardown
"""

import asyncio
import logging
import time
import json
import base64
import threading
from typing import Optional, Callable, Tuple
from urllib.parse import urlencode
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
    collect_deadline_seconds: float = 10.0
    trailing_silence_seconds: float = 0.9
    wait_after_end_speech_seconds: float = 0.6


class SarvamSTTEngine:
    """
    WebSocket-based STT engine using Sarvam AI Saaras V3.

    Connection params go on the WebSocket URL (per Sarvam AsyncAPI).
    Audio is sent as nested JSON; flush uses {"type": "flush"}.
    A background reader drains server messages so the socket stays healthy.
    """

    WEBSOCKET_URL = "wss://api.sarvam.ai/speech-to-text/ws"

    def __init__(self, config: SarvamSTTConfig, on_transcript: Optional[Callable[[str, bool], None]] = None):
        if not websockets:
            raise ImportError("websockets package required for Sarvam STT. Install with: pip install websockets")

        self.config = config
        self.on_transcript = on_transcript
        self.ws: Optional[WebSocketClientProtocol] = None
        self.is_connected = False
        self.connection_lock = asyncio.Lock()
        self.retry_count = 0
        self.should_stop = False

        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._loop_thread: Optional[threading.Thread] = None
        self._reader_task: Optional[asyncio.Task] = None
        self._batch_task: Optional[asyncio.Task] = None
        self._batch_cancel: Optional[asyncio.Event] = None
        self._ws_lock: Optional[asyncio.Lock] = None
        self._msg_queue: Optional[asyncio.Queue] = None
        self._utterance_active = False

        logger.info(
            f"Sarvam STT initialized: model={config.model}, "
            f"language={config.language_code}, mode={config.mode}, "
            f"sample_rate={config.sample_rate}Hz"
        )

    def _build_ws_url(self) -> str:
        """Sarvam STT expects connection config as query parameters."""
        params = {
            "model": self.config.model,
            "language-code": self.config.language_code,
            "mode": self.config.mode,
            "sample_rate": str(self.config.sample_rate),
            "high_vad_sensitivity": "true" if self.config.high_vad_sensitivity else "false",
            "flush_signal": "true" if self.config.flush_signal else "false",
            "vad_signals": "true",
            "input_audio_codec": "pcm_s16le",
        }
        return f"{self.WEBSOCKET_URL}?{urlencode(params)}"

    def _build_audio_message(self, pcm_bytes: bytes, sample_rate: int) -> dict:
        """Sarvam AsyncAPI: audio nested under audio.data with sample_rate + encoding."""
        return {
            "audio": {
                "data": base64.b64encode(pcm_bytes).decode("utf-8"),
                "sample_rate": str(sample_rate),
                "encoding": "audio/wav",
            }
        }

    def _parse_message(self, raw: str) -> Tuple[Optional[str], bool, str, Optional[str]]:
        """
        Parse Sarvam STT WebSocket response.

        Returns:
            (transcript_or_none, is_final, kind, signal_type)
        """
        data = json.loads(raw)
        msg_type = data.get("type")

        if msg_type == "data":
            inner = data.get("data") or {}
            if isinstance(inner, dict):
                transcript = (inner.get("transcript") or inner.get("translation") or "").strip()
                if transcript:
                    return transcript, True, "data", None
            return None, False, "data", None

        if msg_type == "events":
            inner = data.get("data") or {}
            signal = inner.get("signal_type") if isinstance(inner, dict) else None
            logger.debug(f"Sarvam STT VAD event: {signal}")
            return None, False, "events", signal

        if msg_type == "error":
            inner = data.get("data") or {}
            err = inner.get("error") if isinstance(inner, dict) else data.get("error")
            code = inner.get("code") if isinstance(inner, dict) else data.get("code")
            logger.error(f"Sarvam STT API error ({code}): {err}")
            return None, False, "error", None

        # Legacy flat format fallback
        transcript = (data.get("transcript") or "").strip()
        if transcript:
            return transcript, bool(data.get("is_final", True)), "data", None

        return None, False, "unknown", None

    def _is_ws_closed(self) -> bool:
        """Check if WebSocket is closed (websockets 10+)."""
        if not self.ws:
            return True
        try:
            from websockets.protocol import State
            if self.ws.state != State.OPEN:
                return True
        except (AttributeError, ImportError):
            pass
        if getattr(self.ws, "close_code", None) is not None:
            return True
        return False

    async def _stop_reader(self):
        if self._reader_task and not self._reader_task.done():
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass
        self._reader_task = None

    async def _reader_loop(self):
        """Continuously read server messages into the queue."""
        while not self.should_stop:
            try:
                if self._is_ws_closed():
                    await asyncio.sleep(0.15)
                    continue
                raw = await self.ws.recv()
                if not isinstance(raw, str):
                    continue
                transcript, is_final, kind, signal = self._parse_message(raw)
                if self._msg_queue is not None:
                    await self._msg_queue.put((transcript, is_final, kind, signal))
                if transcript and self.on_transcript:
                    self.on_transcript(transcript, is_final)
                if kind == "error":
                    self.is_connected = False
            except websockets.exceptions.ConnectionClosed:
                self.is_connected = False
                logger.debug("Sarvam STT reader: connection closed")
                await asyncio.sleep(0.25)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"Sarvam STT reader error: {e}")
                await asyncio.sleep(0.1)

    async def _start_reader(self):
        await self._stop_reader()
        if self._loop and self.is_connected:
            self._reader_task = asyncio.ensure_future(self._reader_loop())

    async def _drain_stale_messages(self):
        if not self._msg_queue:
            return
        while True:
            try:
                self._msg_queue.get_nowait()
            except asyncio.QueueEmpty:
                break

    async def connect(self) -> bool:
        """Establish WebSocket connection to Sarvam AI."""
        async with self.connection_lock:
            if self.is_connected and not self._is_ws_closed():
                return True

            await self._stop_reader()

            try:
                ws_url = self._build_ws_url()
                logger.info(f"Connecting to Sarvam STT at {self.WEBSOCKET_URL}")
                start_time = time.time()

                self.ws = await asyncio.wait_for(
                    websockets.connect(
                        ws_url,
                        additional_headers={"api-subscription-key": self.config.api_key},
                        ping_interval=20,
                        ping_timeout=10,
                        max_size=10 * 1024 * 1024,
                    ),
                    timeout=10.0,
                )

                elapsed = (time.time() - start_time) * 1000
                logger.info(f"✓ Sarvam STT connected successfully ({elapsed:.0f}ms)")

                self.is_connected = True
                self.retry_count = 0

                if self._msg_queue is None and self._loop:
                    self._msg_queue = asyncio.Queue()

                await self._start_reader()
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
        """Attempt to reconnect with exponential backoff."""
        await self._cancel_batch_task()
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
        """Ensure a live WebSocket connection."""
        if self.is_connected and not self._is_ws_closed():
            return True
        self.is_connected = False
        self.retry_count = 0
        return await self.connect()

    def _run_background_loop(self):
        """Thread target: run the asyncio event loop forever."""
        asyncio.set_event_loop(self._loop)
        self._ws_lock = asyncio.Lock()
        self._msg_queue = asyncio.Queue()
        self._batch_cancel = asyncio.Event()
        self._loop.run_forever()

    def start_session_loop(self):
        """Start persistent background loop and connect once."""
        self._loop = asyncio.new_event_loop()
        self._loop_thread = threading.Thread(
            target=self._run_background_loop,
            daemon=True,
            name="SarvamSTT-Loop",
        )
        self._loop_thread.start()

        future = asyncio.run_coroutine_threadsafe(self.connect(), self._loop)
        try:
            connected = future.result(timeout=12)
            if connected:
                logger.info("✓ Sarvam STT session loop started and connected")
            else:
                logger.warning("Sarvam STT session loop started but initial connect failed")
        except Exception as e:
            logger.warning(f"Sarvam STT session loop start error: {e}")

    async def _cancel_batch_task(self):
        """Cancel any in-flight batch transcription."""
        if self._batch_cancel:
            self._batch_cancel.set()
        if self._batch_task and not self._batch_task.done():
            self._batch_task.cancel()
            try:
                await self._batch_task
            except asyncio.CancelledError:
                pass
        self._batch_task = None
        if self._batch_cancel:
            self._batch_cancel.clear()
        await self._drain_stale_messages()

    async def _shutdown(self):
        """Gracefully cancel tasks and close the WebSocket."""
        self.should_stop = True
        await self._cancel_batch_task()
        await self._stop_reader()

        if self.ws and not self._is_ws_closed():
            try:
                await self.ws.close()
                await asyncio.sleep(0)
                logger.info("Sarvam STT disconnected")
            except Exception as e:
                logger.error(f"Error disconnecting Sarvam STT: {e}")

        self.is_connected = False
        self.ws = None

        pending = [
            t for t in asyncio.all_tasks()
            if t is not asyncio.current_task() and not t.done()
        ]
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)

    def stop_session_loop(self):
        """Cleanly stop the background event loop and disconnect."""
        self.should_stop = True
        if self._loop and self._loop.is_running():
            future = asyncio.run_coroutine_threadsafe(self._shutdown(), self._loop)
            try:
                future.result(timeout=5)
            except Exception:
                pass
            self._loop.call_soon_threadsafe(self._loop.stop)
        if self._loop_thread:
            self._loop_thread.join(timeout=3)

    def update_language_settings(self, language_code: str, mode: str) -> None:
        """Update STT language/mode (reconnect required to take effect)."""
        self.config.language_code = language_code
        self.config.mode = mode

    async def reconnect_with_settings(self) -> bool:
        """Disconnect and reconnect with current config (e.g. after language change)."""
        await self._cancel_batch_task()
        if self.ws and not self._is_ws_closed():
            try:
                await self.ws.close()
            except Exception:
                pass
        self.ws = None
        self.is_connected = False
        self.retry_count = 0
        return await self.connect()

    def apply_language_settings_sync(self, language_code: str, mode: str) -> bool:
        """Thread-safe: update language and reconnect the session WebSocket."""
        self.update_language_settings(language_code, mode)
        if not self._loop or not self._loop.is_running():
            logger.warning("Sarvam STT loop not running — language settings stored only")
            return False
        future = asyncio.run_coroutine_threadsafe(
            self.reconnect_with_settings(), self._loop
        )
        try:
            ok = future.result(timeout=15)
            logger.info(
                "[STT LANG] Sarvam reconnected lang=%s mode=%s ok=%s",
                language_code,
                mode,
                ok,
            )
            return ok
        except Exception as ex:
            logger.warning("[STT LANG] Sarvam reconnect failed: %s", ex)
            return False

    def _float32_to_pcm_bytes(self, audio_float32) -> bytes:
        if np is None:
            raise RuntimeError("numpy required for Sarvam STT")
        audio_int16 = (audio_float32 * 32767.0).clip(-32768, 32767).astype(np.int16)
        return audio_int16.tobytes()

    def transcribe_sync(
        self,
        audio_float32,
        sample_rate: int = 16000,
        timeout: float = 8.0,
    ) -> Optional[str]:
        """
        Synchronous transcription — send full utterance, flush, await transcript.
        Safe to call from any thread.
        """
        if not self._loop or not self._loop.is_running():
            logger.warning("Sarvam STT session loop not running — skipping")
            return None
        try:
            audio_bytes = self._float32_to_pcm_bytes(audio_float32)
        except Exception as e:
            logger.error(f"Sarvam STT float→int16 conversion error: {e}")
            return None

        future = asyncio.run_coroutine_threadsafe(
            self._run_transcribe_batch(audio_bytes, sample_rate), self._loop
        )
        try:
            return future.result(timeout=timeout)
        except Exception as e:
            logger.warning(f"Sarvam STT transcribe_sync error: {e}")
            if self._loop and self._loop.is_running():
                asyncio.run_coroutine_threadsafe(self._cancel_batch_task(), self._loop)
            return None

    async def _run_transcribe_batch(self, audio_bytes: bytes, sample_rate: int) -> Optional[str]:
        """Wrap batch transcription in a tracked task for cancellation."""
        await self._cancel_batch_task()
        self._batch_task = asyncio.create_task(
            self._transcribe_batch(audio_bytes, sample_rate)
        )
        try:
            return await self._batch_task
        finally:
            self._batch_task = None

    async def _send_pcm_chunk(self, pcm_bytes: bytes, sample_rate: int) -> bool:
        if not self._ws_lock:
            return False
        try:
            msg = self._build_audio_message(pcm_bytes, sample_rate)
            async with self._ws_lock:
                if self._is_ws_closed():
                    return False
                await self.ws.send(json.dumps(msg))
            return True
        except websockets.exceptions.ConnectionClosed:
            self.is_connected = False
            return False
        except Exception as e:
            logger.warning(f"Sarvam STT send chunk error: {e}")
            self.is_connected = False
            return False

    async def _collect_transcript_until_final(
        self,
        deadline_seconds: float = 10.0,
    ) -> Optional[str]:
        """Accumulate transcript segments until END_SPEECH or deadline."""
        if not self._msg_queue:
            return None

        parts: list[str] = []
        deadline = time.monotonic() + max(1.0, deadline_seconds)
        saw_end_speech = False
        last_data_at = 0.0

        while time.monotonic() < deadline:
            if self._batch_cancel and self._batch_cancel.is_set():
                logger.debug("Sarvam STT collect cancelled")
                return None
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            try:
                transcript, is_final, kind, signal = await asyncio.wait_for(
                    self._msg_queue.get(), timeout=min(remaining, 2.0)
                )
                now = time.monotonic()
                if kind == "events" and signal == "END_SPEECH":
                    saw_end_speech = True
                    if parts and (now - last_data_at) >= self.config.wait_after_end_speech_seconds:
                        break
                if transcript:
                    # Sarvam may occasionally re-emit identical text chunks.
                    if not parts or transcript != parts[-1]:
                        parts.append(transcript)
                    last_data_at = now
                    logger.debug(f"Sarvam STT segment: '{transcript}'")
                if saw_end_speech and parts and (now - last_data_at) >= self.config.wait_after_end_speech_seconds:
                    break
                # Allow trailing chunks after the latest transcript before finalizing.
                if parts and (now - last_data_at) >= self.config.trailing_silence_seconds:
                    break
            except asyncio.TimeoutError:
                if parts and (time.monotonic() - last_data_at) >= self.config.trailing_silence_seconds:
                    break

        full_text = " ".join(parts).strip()
        if full_text:
            logger.info(f"[Sarvam STT] Final transcript: '{full_text}'")
        return full_text or None

    async def _transcribe_batch(self, audio_bytes: bytes, sample_rate: int) -> Optional[str]:
        """Send utterance in 100ms chunks, flush, await final transcript."""
        if not await self.ensure_connected():
            logger.error("Sarvam STT not connected for batch transcription")
            return None

        await self._drain_stale_messages()
        self._utterance_active = True

        try:
            CHUNK_BYTES = sample_rate * 2 // 10  # 100 ms, 16-bit mono
            sent_chunks = 0

            for offset in range(0, len(audio_bytes), CHUNK_BYTES):
                if self._batch_cancel and self._batch_cancel.is_set():
                    logger.debug("Sarvam STT batch cancelled mid-send")
                    return None
                chunk = audio_bytes[offset : offset + CHUNK_BYTES]
                if not await self._send_pcm_chunk(chunk, sample_rate):
                    if not await self.reconnect():
                        return None
                    if not await self._send_pcm_chunk(chunk, sample_rate):
                        return None
                sent_chunks += 1
                # Small yield so reader can process incoming messages
                await asyncio.sleep(0)

            if not self._ws_lock:
                return None

            async with self._ws_lock:
                if self._is_ws_closed():
                    return None
                await self.ws.send(json.dumps({"type": "flush"}))

            logger.debug(
                f"Sarvam STT: sent {sent_chunks} chunks + flush ({len(audio_bytes)} bytes)"
            )
            return await self._collect_transcript_until_final(
                deadline_seconds=self.config.collect_deadline_seconds
            )

        except asyncio.CancelledError:
            logger.debug("Sarvam STT _transcribe_batch cancelled")
            raise
        except websockets.exceptions.ConnectionClosed:
            logger.warning("Sarvam STT connection closed during _transcribe_batch")
            self.is_connected = False
            return None
        except Exception as e:
            logger.error(f"Sarvam STT _transcribe_batch error: {e}", exc_info=True)
            return None
        finally:
            self._utterance_active = False

    async def disconnect(self):
        """Cleanly disconnect from Sarvam AI."""
        await self._shutdown()
