"""
Integrated Audio Sender with Sarvam AI TTS + Edge-TTS Fallback
Automatically handles failover and provides low-latency TTS with production-grade reliability.
Supports three output modes:
  1. Webpage (Output Media): MP3 → PCM Int16 → WebSocket to browser page (lowest latency)
  2. WebRTC raw PCM: legacy path (rarely used)
  3. File upload: fallback via Recall output_audio API
"""

import io
import os
import logging
import asyncio
from pathlib import Path
from typing import Callable, Optional
import edge_tts
from recall_bot_service import RecallBotService
from config import TTS_STREAMING_ENABLED

# Import Sarvam TTS
try:
    from sarvam_tts_engine import SarvamTTSEngine, SarvamTTSConfig
    SARVAM_AVAILABLE = True
except ImportError:
    SARVAM_AVAILABLE = False
    logging.warning("Sarvam TTS not available, will use Edge-TTS only")

logger = logging.getLogger(__name__)


class IntegratedAudioSender:
    """
    Production audio sender with automatic failover.
    
    Primary: Sarvam AI Bulbul V3 (WebSocket, <500ms latency)
    Fallback: Microsoft Edge-TTS (reliable, ~2s latency)
    
    Supports both WebRTC streaming and file upload to Recall.ai.
    """
    
    def __init__(
        self,
        recall_service: RecallBotService,
        voice: str = "en-IN-PrabhatNeural",
        rate: str = "+35%",
        reduce_pauses: bool = True,
        webrtc_manager: Optional[any] = None,
        use_sarvam: bool = True,
        sarvam_api_key: str = "",
        sarvam_speaker: str = "shubh",
        sarvam_config: Optional[dict] = None,
        # Output Media webpage mode callbacks (set when use_output_media=True)
        webpage_broadcaster: Optional[Callable[[bytes], None]] = None,
        webpage_ctrl_sender: Optional[Callable[[dict], None]] = None,
    ):
        """
        Initialize integrated audio sender.
        
        Args:
            recall_service: RecallBotService instance
            voice: Edge-TTS voice name (fallback)
            rate: Speech rate for Edge-TTS
            reduce_pauses: Reduce pauses in Edge-TTS
            webrtc_manager: Optional WebRTCStreamManager
            use_sarvam: Use Sarvam TTS as primary
            sarvam_api_key: Sarvam API key
            sarvam_speaker: Sarvam speaker name (default: shubh)
            sarvam_config: Optional dict with Sarvam configuration overrides
        """
        self.recall_service = recall_service
        self.voice = voice
        self.rate = rate
        self.reduce_pauses = reduce_pauses
        self.webrtc_manager = webrtc_manager
        self.temp_dir = Path("tmp_audio")
        self.temp_dir.mkdir(exist_ok=True)

        # Output method flags (checked in priority order: webpage > webrtc > file upload)
        self.webpage_broadcaster = webpage_broadcaster     # (pcm_bytes) → None
        self.webpage_ctrl_sender = webpage_ctrl_sender     # (dict)      → None
        self.use_webpage = webpage_broadcaster is not None
        self.use_webrtc = webrtc_manager is not None and not self.use_webpage
        self._tts_sample_rate = 24000
        
        # Initialize Sarvam TTS if enabled
        self.sarvam_engine = None
        self.use_sarvam = use_sarvam and SARVAM_AVAILABLE and sarvam_api_key
        self.using_fallback = False
        
        if self.use_sarvam:
            try:
                # Build Sarvam config
                config_dict = sarvam_config or {}
                self._tts_sample_rate = int(config_dict.get("sample_rate", 24000))
                config = SarvamTTSConfig(
                    api_key=sarvam_api_key,
                    speaker=sarvam_speaker,
                    model=config_dict.get("model", "bulbul:v3"),
                    language_code=config_dict.get("language_code", "en-IN"),
                    sample_rate=config_dict.get("sample_rate", 24000),
                    pace=config_dict.get("pace", 1.2),
                    temperature=config_dict.get("temperature", 0.6),
                    max_retries=config_dict.get("max_retries", 3)
                )
                
                self.sarvam_engine = SarvamTTSEngine(config)
                output_mode = "Webpage-PCM" if self.use_webpage else ("WebRTC" if self.use_webrtc else "File upload")
                logger.info(
                    f"IntegratedAudioSender initialized — Sarvam TTS (primary) + Edge-TTS (fallback). "
                    f"Speaker: {sarvam_speaker}, Output: {output_mode}"
                )
            except Exception as e:
                logger.error(f"Failed to initialize Sarvam TTS: {e}. Using Edge-TTS only.")
                self.use_sarvam = False
                self.using_fallback = True
        
        if not self.use_sarvam:
            output_mode = "Webpage-PCM" if self.use_webpage else ("WebRTC" if self.use_webrtc else "File upload")
            logger.info(f"IntegratedAudioSender initialized — Edge-TTS only. Output: {output_mode}")
    
    def _decode_mp3_to_pcm(self, mp3_bytes: bytes) -> bytes:
        """Convert MP3 → mono Int16 PCM at configured TTS sample rate."""
        try:
            from pydub import AudioSegment
            audio = AudioSegment.from_mp3(io.BytesIO(mp3_bytes))
            audio = audio.set_channels(1).set_sample_width(2)
            if audio.frame_rate != self._tts_sample_rate:
                audio = audio.set_frame_rate(self._tts_sample_rate)
            return audio.raw_data
        except Exception as e:
            logger.error(f"MP3→PCM conversion failed: {e}")
            return b""

    def _try_decode_mp3(self, mp3_bytes: bytes) -> Optional[bytes]:
        """Decode partial MP3; None if ffmpeg needs more frames."""
        try:
            from pydub import AudioSegment
            audio = AudioSegment.from_mp3(io.BytesIO(mp3_bytes))
            audio = audio.set_channels(1).set_sample_width(2)
            if audio.frame_rate != self._tts_sample_rate:
                audio = audio.set_frame_rate(self._tts_sample_rate)
            return audio.raw_data
        except Exception:
            return None

    def _streaming_pcm_tail_guard_bytes(self) -> int:
        """
        Hold back this many PCM bytes on early flushes.

        MP3 bit-reservoir means the last ~1–2 frames can change slightly when
        more stream data arrives. Keeping a short tail unsent avoids word-end
        clicks while still allowing early playback (~2s TTFB).
        """
        # 60 ms of Int16 mono at TTS rate (slightly safer than 40 ms)
        return max(int(self._tts_sample_rate * 0.06 * 2) & ~1, 2880)

    def _pcm_ws_chunk_bytes(self) -> int:
        """Frame-aligned WebSocket PCM chunk: 100 ms Int16 mono (even byte count)."""
        return max(int(self._tts_sample_rate * 0.1 * 2) & ~1, 4800)

    def _send_pcm_to_webpage(self, pcm: bytes, *, announce: bool = True) -> int:
        """
        Push Int16 PCM to the Output Media page in frame-aligned chunks.
        Returns bytes sent. Optionally emits start_speaking before the first chunk.
        """
        if not pcm or not self.webpage_broadcaster:
            return 0
        if announce and self.webpage_ctrl_sender:
            self.webpage_ctrl_sender({"type": "start_speaking"})
        chunk = self._pcm_ws_chunk_bytes()
        sent = 0
        for i in range(0, len(pcm), chunk):
            piece = pcm[i : i + chunk]
            # Drop a trailing odd byte if somehow present (Int16 alignment).
            if len(piece) & 1:
                piece = piece[:-1]
            if not piece:
                continue
            self.webpage_broadcaster(piece)
            sent += len(piece)
        return sent

    @staticmethod
    def _mp3_to_pcm_int16(mp3_bytes: bytes, target_rate: int = 24000) -> bytes:
        """Legacy static helper — prefer instance _decode_mp3_to_pcm."""
        try:
            from pydub import AudioSegment
            audio = AudioSegment.from_mp3(io.BytesIO(mp3_bytes))
            audio = audio.set_channels(1).set_sample_width(2)
            if audio.frame_rate != target_rate:
                audio = audio.set_frame_rate(target_rate)
            return audio.raw_data
        except Exception as e:
            logger.error(f"MP3→PCM conversion failed: {e}")
            return b""

    async def ensure_sarvam_connected(self) -> bool:
        """Pre-connect Sarvam WebSocket so first sentence has no connect delay."""
        if not self.use_sarvam or not self.sarvam_engine or self.using_fallback:
            return False
        
        connected = await self.sarvam_engine.ensure_connected()
        if connected:
            logger.info("✓ Sarvam TTS pre-connected and ready")
        else:
            logger.warning("Sarvam TTS pre-connect failed — will retry on first speak")
        return connected

    def ensure_sarvam_connected_sync(
        self, tts_loop: "asyncio.AbstractEventLoop"
    ) -> None:
        """Fire-and-forget pre-connect on the TTS worker loop (e.g. when candidate turn starts)."""
        import asyncio

        if not self.use_sarvam or not self.sarvam_engine or self.using_fallback:
            return
        if not tts_loop or not tts_loop.is_running():
            return
        asyncio.run_coroutine_threadsafe(
            self.ensure_sarvam_connected(), tts_loop
        )

    async def apply_tts_language(self, language_code: str) -> bool:
        """Update Sarvam TTS language and reconnect WebSocket (TTS worker loop only)."""
        if not self.use_sarvam or not self.sarvam_engine:
            return False
        self.sarvam_engine.update_language_code(language_code)
        ok = await self.sarvam_engine.reconnect_with_settings()
        logger.info("[TTS LANG] Sarvam language=%s reconnected=%s", language_code, ok)
        return ok

    def apply_tts_language_sync(
        self, language_code: str, tts_loop: "asyncio.AbstractEventLoop"
    ) -> bool:
        """Thread-safe: reconnect Sarvam TTS on the TTS worker event loop."""
        import asyncio

        if not self.use_sarvam or not self.sarvam_engine:
            return False
        if not tts_loop or not tts_loop.is_running():
            logger.warning("[TTS LANG] TTS worker loop not running — language stored only")
            self.sarvam_engine.update_language_code(language_code)
            return False
        self.sarvam_engine.update_language_code(language_code)
        future = asyncio.run_coroutine_threadsafe(
            self.sarvam_engine.reconnect_with_settings(), tts_loop
        )
        try:
            ok = future.result(timeout=15)
            logger.info(
                "[TTS LANG] Sarvam language=%s reconnected=%s", language_code, ok
            )
            return ok
        except Exception as ex:
            logger.warning("[TTS LANG] Sarvam reconnect failed: %s", ex)
            return False
    
    async def send_text_to_bot(self, bot_id: str, text: str, state=None) -> bool:
        """
        Generate TTS and send to bot.
        
        Tries Sarvam first, falls back to Edge-TTS on failure.
        
        Args:
            bot_id: Bot ID
            text: Text to speak
            state: Optional AgentState for interrupt checking
            
        Returns:
            True if successful
        """
        import time
        start_time = time.time()
        
        # Try Sarvam TTS first if enabled
        if self.use_sarvam and self.sarvam_engine and not self.using_fallback:
            try:
                # Batch decode is cleaner (no partial-frame hiss). Streaming only if enabled.
                if (
                    self.use_webpage
                    and self.webpage_broadcaster
                    and TTS_STREAMING_ENABLED
                ):
                    success = await self._send_via_sarvam_streaming(bot_id, text, state)
                else:
                    success = await self._send_via_sarvam(bot_id, text, state)

                if success:
                    elapsed = (time.time() - start_time) * 1000
                    logger.info(f"✓ Sarvam TTS pipeline completed in {elapsed:.0f}ms")
                    return True
                else:
                    logger.warning("Sarvam TTS failed for this utterance, using Edge-TTS fallback")
            
            except Exception as e:
                logger.error(f"Sarvam TTS exception: {e}. Using Edge-TTS for this utterance.")
        
        # Fallback to Edge-TTS
        logger.info("Using Edge-TTS (fallback mode)")
        success = await self._send_via_edge_tts(bot_id, text, state)
        
        if success:
            elapsed = (time.time() - start_time) * 1000
            logger.info(f"✓ Edge-TTS pipeline completed in {elapsed:.0f}ms")
        
        return success
    
    async def _send_via_sarvam(self, bot_id: str, text: str, state=None) -> bool:
        """
        Send audio using Sarvam TTS.
        
        Args:
            bot_id: Bot ID
            text: Text to speak
            state: Optional AgentState for interrupt checking
            
        Returns:
            True if successful
        """
        import re
        
        # Check interrupt before starting
        if state and state.interrupt_flag.is_set():
            logger.info("Sarvam TTS cancelled (interrupt before start)")
            return False
        
        # Preprocess text
        text = re.sub(r'\s+', ' ', text.strip())
        
        if not text:
            return False
        
        connected = await self.sarvam_engine.ensure_connected()
        if not connected:
            logger.error("Failed to connect Sarvam TTS")
            return False
        
        # Generate audio using Sarvam (returns MP3 directly)
        audio_mp3 = await self.sarvam_engine.speak(text, state)
        
        if not audio_mp3:
            logger.error("Sarvam TTS returned no audio")
            return False
        
        # Check interrupt after TTS generation
        if state and state.interrupt_flag.is_set():
            logger.info("Sarvam TTS cancelled (interrupt after generation)")
            return False
        
        # Route audio to the correct output path
        if self.use_webpage and self.webpage_broadcaster:
            # Output Media webpage: convert MP3 → PCM and stream over WebSocket
            pcm = self._decode_mp3_to_pcm(audio_mp3)
            if not pcm:
                logger.error("Sarvam TTS: MP3→PCM conversion returned empty bytes")
                return False
            sent = self._send_pcm_to_webpage(pcm, announce=True)
            logger.info(
                f"✓ Streamed {sent} PCM bytes ({len(audio_mp3)} MP3 bytes) "
                f"via WebSocket to Output Media page (Sarvam TTS)"
            )
            return sent > 0

        elif self.use_webrtc and self.webrtc_manager:
            success = await self.webrtc_manager.stream_audio_from_mp3(audio_mp3, state)
            if success:
                logger.info(f"✓ Streamed {len(audio_mp3)} bytes MP3 via WebRTC (Sarvam TTS)")
            return success

        else:
            success = self.recall_service.send_audio_to_bot(
                bot_id=bot_id,
                audio_data=audio_mp3,
                audio_codec="mp3"
            )
            if success:
                logger.info(f"✓ Sent {len(audio_mp3)} bytes MP3 via file upload (Sarvam TTS)")
            return success
    
    async def _send_via_sarvam_streaming(self, bot_id: str, text: str, state=None) -> bool:
        """
        Stream Sarvam TTS → Output Media with low TTFB and gapless playback.

        Production strategy (avoids the old stutter):
          Re-decoding the *entire* growing MP3 with ffmpeg every ~1.5 KB made
          decode time exceed newly added audio as the buffer grew → PCM underruns
          and jerky speech.

          Instead:
            1. Accumulate the full MP3 stream in memory (never clear mid-utterance).
            2. Decode on a worker thread (do not block the TTS loop on ffmpeg).
            3. First decode only after ~0.5 s of MP3 (~TTFB), then re-decode at
               ~1.0 s MP3 steps so each decode covers far more audio than it costs.
            4. Emit only *new* PCM; hold a short tail on non-final flushes
               (MP3 bit-reservoir).
            5. Final decode flushes the remainder with no guard.
            6. WebSocket chunks are 100 ms frame-aligned Int16.

        start_speaking is sent only with the first PCM (avoids premature
        playback_done while the worklet buffer is still empty).
        """
        import re

        if state and state.interrupt_flag.is_set():
            return False

        text = re.sub(r'\s+', ' ', text.strip())
        if not text:
            return False

        connected = await self.sarvam_engine.ensure_connected()
        if not connected:
            logger.error("Failed to connect Sarvam TTS for streaming")
            return False

        # ~0.5 s / ~1.0 s of audio at ~128 kbps CBR (Sarvam MP3).
        # Steps must stay large: decode cost grows with buffer size; tiny steps
        # made ffmpeg slower than realtime and starved the browser ring buffer.
        FIRST_DECODE_BYTES = 8192
        DECODE_STEP_BYTES = 16384
        MIN_PCM_OUTPUT = max(int(self._tts_sample_rate * 0.05 * 2) & ~1, 2400)
        TAIL_GUARD = self._streaming_pcm_tail_guard_bytes()

        mp3_buffer = bytearray()
        pcm_emitted = 0
        total_pcm = 0
        start_speaking_sent = False
        last_decode_at_len = 0
        decode_count = 0

        def _broadcast_pcm(pcm: bytes) -> None:
            nonlocal start_speaking_sent, total_pcm
            if not pcm:
                return
            sent = self._send_pcm_to_webpage(pcm, announce=not start_speaking_sent)
            if sent:
                start_speaking_sent = True
                total_pcm += sent

        async def _emit_stable_pcm(*, final: bool) -> None:
            """Decode full MP3-so-far off-thread; send only new stable PCM."""
            nonlocal pcm_emitted, last_decode_at_len, decode_count
            if not mp3_buffer:
                return
            snapshot = bytes(mp3_buffer)
            last_decode_at_len = len(snapshot)
            if final:
                pcm = await asyncio.to_thread(self._decode_mp3_to_pcm, snapshot)
            else:
                pcm = await asyncio.to_thread(self._try_decode_mp3, snapshot)
            decode_count += 1
            if not pcm:
                return
            if not final and len(pcm) < MIN_PCM_OUTPUT:
                return
            # Int16 alignment
            if len(pcm) & 1:
                pcm = pcm[:-1]
            if final:
                stable_end = len(pcm)
            else:
                stable_end = max(pcm_emitted, len(pcm) - TAIL_GUARD)
                stable_end &= ~1
            if stable_end > pcm_emitted:
                _broadcast_pcm(pcm[pcm_emitted:stable_end])
                logger.debug(
                    "[TTS Streaming] emit +%d PCM (emitted=%d total_dec=%d final=%s n=%d)",
                    stable_end - pcm_emitted,
                    stable_end,
                    len(pcm),
                    final,
                    decode_count,
                )
                pcm_emitted = stable_end

        try:
            async for mp3_chunk in self.sarvam_engine.speak_streaming_mp3(text, state):
                if state and state.interrupt_flag.is_set():
                    break

                if not mp3_chunk:
                    continue
                mp3_buffer.extend(mp3_chunk)

                if pcm_emitted == 0:
                    if len(mp3_buffer) >= FIRST_DECODE_BYTES:
                        await _emit_stable_pcm(final=False)
                elif len(mp3_buffer) - last_decode_at_len >= DECODE_STEP_BYTES:
                    await _emit_stable_pcm(final=False)

            if mp3_buffer and not (state and state.interrupt_flag.is_set()):
                await _emit_stable_pcm(final=True)

        except Exception as e:
            logger.error(f"Sarvam TTS streaming error: {e}", exc_info=True)

        if total_pcm > 0:
            logger.info(
                f"✓ Streamed {total_pcm} PCM bytes via WebSocket to Output Media page "
                f"(Sarvam TTS streaming, {decode_count} decode(s), paced)"
            )
            return True

        logger.warning("Sarvam TTS streaming produced no audio")
        return False

    async def _send_via_edge_tts(self, bot_id: str, text: str, state=None) -> bool:
        """
        Send audio using Edge-TTS (fallback).
        
        Args:
            bot_id: Bot ID
            text: Text to speak
            state: Optional AgentState for interrupt checking
            
        Returns:
            True if successful
        """
        import uuid
        import re
        
        # Check interrupt
        if state and state.interrupt_flag.is_set():
            logger.info("Edge-TTS cancelled (interrupt before start)")
            return False
        
        # Preprocess text
        if self.reduce_pauses:
            sentences = text.split('. ')
            if len(sentences) > 1:
                text = ', '.join(sentences[:-1])
                if sentences[-1]:
                    text += '. ' + sentences[-1]
        
        text = re.sub(r'\s+', ' ', text.strip())
        
        if not text:
            return False
        
        # Generate MP3 with Edge-TTS
        mp3_path = self.temp_dir / f"edge_tts_{uuid.uuid4().hex[:8]}.mp3"
        
        try:
            communicate = edge_tts.Communicate(text, self.voice, rate=self.rate)
            await communicate.save(str(mp3_path))
            
            if not mp3_path.exists() or mp3_path.stat().st_size == 0:
                logger.error("Edge-TTS generated empty audio")
                return False
            
            # Check interrupt after generation
            if state and state.interrupt_flag.is_set():
                logger.info("Edge-TTS cancelled (interrupt after generation)")
                return False
            
            # Read MP3
            with open(mp3_path, "rb") as f:
                mp3_data = f.read()
            
            # Route to correct output path
            if self.use_webpage and self.webpage_broadcaster:
                pcm = self._decode_mp3_to_pcm(mp3_data)
                if not pcm:
                    logger.error("Edge-TTS: MP3→PCM conversion returned empty bytes")
                    return False
                sent = self._send_pcm_to_webpage(pcm, announce=True)
                logger.info(
                    f"✓ Streamed {sent} PCM bytes via WebSocket to Output Media page (Edge-TTS)"
                )
                return sent > 0

            elif self.use_webrtc and self.webrtc_manager:
                success = await self.webrtc_manager.stream_audio_from_mp3(mp3_data, state)
                if success:
                    logger.info(f"✓ Streamed {len(mp3_data)} bytes MP3 via WebRTC (Edge-TTS)")
                return success
            else:
                success = self.recall_service.send_audio_to_bot(
                    bot_id=bot_id,
                    audio_data=mp3_data,
                    audio_codec="mp3"
                )
                if success:
                    logger.info(f"✓ Sent {len(mp3_data)} bytes MP3 via file upload (Edge-TTS)")
                return success
        
        except Exception as e:
            logger.error(f"Edge-TTS error: {e}", exc_info=True)
            return False
        
        finally:
            # Cleanup
            mp3_path.unlink(missing_ok=True)


# Maintain backwards compatibility - alias to new class
AudioSender = IntegratedAudioSender


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    async def main():
        from recall_bot_service import RecallBotService
        
        recall_service = RecallBotService()
        
        # Test with Sarvam
        sender = IntegratedAudioSender(
            recall_service,
            use_sarvam=True,
            sarvam_api_key="your-api-key",
            sarvam_speaker="shubh"
        )
        
        # Test TTS
        success = await sender.send_text_to_bot(
            bot_id="test-bot-id",
            text="Hello, I am Prabhat. How are you today?"
        )
        
        print(f"TTS test: {'SUCCESS' if success else 'FAILED'}")
    
    asyncio.run(main())
