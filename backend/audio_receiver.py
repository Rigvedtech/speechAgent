"""
Audio Receiver - WebSocket Server
Receives real-time audio streams from Recall.ai bots and routes to STT pipeline.
"""

import asyncio
import json
import base64
import logging
from typing import Dict, Callable, Optional
import numpy as np
import websockets
from websockets.server import WebSocketServerProtocol

logger = logging.getLogger(__name__)


class AudioReceiver:
    """WebSocket server to receive real-time audio and transcripts from Recall.ai."""
    
    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 8765,
        audio_callback: Optional[Callable] = None,
        transcript_callback: Optional[Callable] = None,
        video_callback: Optional[Callable] = None,
    ):
        """
        Initialize audio receiver WebSocket server.
        
        Args:
            host: Server host address
            port: Server port
            audio_callback: Invoked per PCM audio chunk.
                           Signature: callback(bot_id: str, audio_array: np.ndarray)
            transcript_callback: Invoked per transcript segment from Recall.ai.
                           Signature: callback(bot_id, text, is_final, is_bot_speaker,
                                               participant_id=None, participant_name=None)
            video_callback: Invoked per separate participant PNG frame.
                           Signature: callback(bot_id, png_bytes, participant_id,
                                               participant_name, media_type)
        """
        self.host = host
        self.port = port
        self.audio_callback = audio_callback
        self.transcript_callback = transcript_callback
        self.video_callback = video_callback
        self.active_connections: Dict[str, WebSocketServerProtocol] = {}
        self.bot_sessions: Dict[str, dict] = {}  # bot_id -> session info
    
    async def handle_connection(self, websocket: WebSocketServerProtocol):
        """
        Handle incoming WebSocket connection from Recall.ai.
        
        Args:
            websocket: WebSocket connection
        """
        connection_id = id(websocket)
        self.active_connections[connection_id] = websocket
        bot_id = None
        
        logger.info(f"New WebSocket connection: {connection_id}")
        
        try:
            async for message in websocket:
                try:
                    # Parse incoming message
                    if isinstance(message, str):
                        data = json.loads(message)
                        
                        # Extract bot ID from first message
                        if not bot_id and "bot" in data.get("data", {}):
                            bot_id = data["data"]["bot"].get("id")
                            logger.info(f"Connection {connection_id} associated with bot {bot_id}")
                        
                        # Route events by type
                        event_type = data.get("event")
                        if event_type == "audio_mixed_raw.data":
                            await self._process_audio_message(data, bot_id)
                        elif event_type == "transcript.data":
                            await self._process_transcript_message(data, bot_id)
                        elif event_type == "video_separate_png.data":
                            await self._process_video_png_message(data, bot_id)
                        elif event_type and "video" in str(event_type).lower():
                            # Surface unexpected video event names (schema drift)
                            logger.info(
                                "[CAMERA] Unhandled video-related event=%s keys=%s",
                                event_type,
                                list((data.get("data") or {}).keys())[:12],
                            )
                        elif event_type:
                            logger.debug(f"Received event: {event_type}")
                    
                    else:
                        logger.warning(f"Received non-JSON message: {type(message)}")
                
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to decode JSON: {e}")
                except Exception as e:
                    logger.error(f"Error processing message: {e}", exc_info=True)
        
        except websockets.exceptions.ConnectionClosed:
            logger.info(f"Connection {connection_id} closed")
        
        finally:
            # Cleanup
            if connection_id in self.active_connections:
                del self.active_connections[connection_id]
            if bot_id and bot_id in self.bot_sessions:
                del self.bot_sessions[bot_id]
            
            logger.info(f"Connection {connection_id} cleaned up")
    
    async def _process_audio_message(self, data: dict, bot_id: Optional[str]):
        """
        Process audio data message from Recall.ai.
        
        Args:
            data: Message data containing audio buffer
            bot_id: Associated bot ID
        """
        try:
            # Extract audio buffer (base64 encoded)
            buffer_b64 = data["data"]["data"]["buffer"]
            
            # Decode base64 to bytes
            audio_bytes = base64.b64decode(buffer_b64)
            
            # Convert to numpy array (16-bit PCM, 16kHz, mono)
            # S16LE = signed 16-bit little-endian
            audio_array = np.frombuffer(audio_bytes, dtype=np.int16)
            
            # Convert to float32 normalized [-1.0, 1.0] for processing
            audio_float = audio_array.astype(np.float32) / 32768.0
            
            # Extract timestamp info
            timestamp = data["data"]["data"]["timestamp"]
            relative_time = timestamp.get("relative", 0)
            
            logger.debug(
                f"Received audio chunk: {len(audio_float)} samples "
                f"({len(audio_float)/16000:.2f}s) at t={relative_time:.2f}s"
            )
            
            # Call the registered callback with audio data
            if self.audio_callback and bot_id:
                try:
                    self.audio_callback(bot_id, audio_float)
                except Exception as e:
                    logger.error(f"Error in audio callback: {e}", exc_info=True)
        
        except KeyError as e:
            logger.error(f"Missing expected field in audio message: {e}")
        except Exception as e:
            logger.error(f"Failed to process audio: {e}", exc_info=True)

    async def _process_transcript_message(self, data: dict, bot_id: Optional[str]):
        """
        Parse a transcript.data event from Recall.ai and invoke transcript_callback.

        Recall.ai fires partial segments continuously while the speaker talks and
        then one final segment (is_final=True) once their VAD decides the turn is
        complete.  We only care about final segments for routing to the LLM, but
        we pass the flag through so callers can decide.

        Event shape:
            data["data"]["data"] = {
                "speaker": {"id": str, "name": str, "is_bot": bool},
                "words":   [{"text": str, ...}, ...],
                "is_final": bool,
                "lang": str,
            }
        """
        if not self.transcript_callback or not bot_id:
            return

        try:
            payload = data["data"]["data"]
            speaker = payload.get("speaker", {})
            is_bot_speaker = bool(speaker.get("is_bot", False))
            is_final = bool(payload.get("is_final", False))
            words = payload.get("words", [])
            text = " ".join(w.get("text", "") for w in words).strip()

            if not text:
                return

            logger.debug(
                f"[RECALL TRANSCRIPT] bot={bot_id[:8]} is_final={is_final} "
                f"is_bot={is_bot_speaker} text='{text[:60]}'"
            )

            participant_id = speaker.get("id")
            participant_name = speaker.get("name")
            try:
                self.transcript_callback(
                    bot_id,
                    text,
                    is_final,
                    is_bot_speaker,
                    participant_id=participant_id,
                    participant_name=participant_name,
                )
            except TypeError:
                # Backward-compatible callers without participant kwargs
                self.transcript_callback(bot_id, text, is_final, is_bot_speaker)
            except Exception as e:
                logger.error(f"Error in transcript callback: {e}", exc_info=True)

        except (KeyError, TypeError) as e:
            # Log the raw event once so we can debug the actual schema if it differs
            logger.warning(
                f"Could not parse transcript.data event (key={e}). "
                f"Raw payload: {str(data)[:300]}"
            )
        except Exception as e:
            logger.error(f"Failed to process transcript: {e}", exc_info=True)

    async def _process_video_png_message(self, data: dict, bot_id: Optional[str]):
        """Parse video_separate_png.data and invoke video_callback."""
        if not self.video_callback or not bot_id:
            if not getattr(self, "_logged_video_no_cb", False):
                self._logged_video_no_cb = True
                logger.warning(
                    "[CAMERA] video_separate_png received but callback/bot_id missing "
                    "callback=%s bot_id=%s",
                    bool(self.video_callback),
                    bot_id,
                )
            return
        try:
            # Recall nests payload under data.data; tolerate slight schema drift
            outer = data.get("data") or {}
            payload = outer.get("data") if isinstance(outer.get("data"), dict) else outer
            if not isinstance(payload, dict):
                logger.warning("[CAMERA] unexpected video payload type=%s", type(payload))
                return
            buffer_b64 = payload.get("buffer")
            if not buffer_b64:
                logger.warning(
                    "[CAMERA] video event missing buffer keys=%s",
                    list(payload.keys())[:20],
                )
                return
            png_bytes = base64.b64decode(buffer_b64)
            participant = payload.get("participant") or {}
            if not isinstance(participant, dict):
                participant = {}
            participant_id = participant.get("id")
            participant_name = participant.get("name")
            media_type = payload.get("type") or "webcam"
            if participant_id is None:
                logger.warning(
                    "[CAMERA] video event missing participant.id keys=%s",
                    list(payload.keys())[:20],
                )
                return
            if not getattr(self, "_logged_first_video", False):
                self._logged_first_video = True
                logger.info(
                    "[CAMERA] First video_separate_png frame bot=%s id=%s name=%r "
                    "type=%s bytes=%d",
                    str(bot_id)[:8],
                    participant_id,
                    participant_name,
                    media_type,
                    len(png_bytes),
                )
            try:
                self.video_callback(
                    bot_id,
                    png_bytes,
                    str(participant_id),
                    participant_name,
                    media_type,
                )
            except Exception as e:
                logger.error(f"Error in video callback: {e}", exc_info=True)
        except (KeyError, TypeError, ValueError) as e:
            logger.warning(
                "[CAMERA] Could not parse video_separate_png.data (key=%s). Raw: %s",
                e,
                str(data)[:400],
            )
        except Exception as e:
            logger.error(f"Failed to process video PNG: {e}", exc_info=True)

    async def start(self):
        """Start the WebSocket server."""
        logger.info(f"Starting audio receiver on ws://{self.host}:{self.port}")
        
        # PNG frames in JSON can exceed the default 1 MiB message cap
        async with websockets.serve(
            self.handle_connection,
            self.host,
            self.port,
            ping_interval=20,
            ping_timeout=10,
            max_size=8 * 1024 * 1024,
            max_queue=64,
        ):
            logger.info(
                "Audio receiver started successfully (max_size=8MiB for video PNG)"
            )
            await asyncio.Future()  # Run forever
    
    def run(self):
        """Run the WebSocket server (blocking)."""
        try:
            asyncio.run(self.start())
        except KeyboardInterrupt:
            logger.info("Audio receiver stopped by user")
        except Exception as e:
            logger.error(f"Audio receiver error: {e}", exc_info=True)


# Example usage
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    def handle_audio(bot_id: str, audio_array: np.ndarray):
        """Example audio handler."""
        print(f"Received {len(audio_array)} samples from bot {bot_id}")
        # Here you would feed to your STT engine
    
    receiver = AudioReceiver(
        host="0.0.0.0",
        port=8765,
        audio_callback=handle_audio
    )
    
    receiver.run()
