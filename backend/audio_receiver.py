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
    """WebSocket server to receive real-time audio from Recall.ai."""
    
    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 8765,
        audio_callback: Optional[Callable] = None
    ):
        """
        Initialize audio receiver WebSocket server.
        
        Args:
            host: Server host address
            port: Server port
            audio_callback: Function called when audio chunk received
                           Signature: callback(bot_id: str, audio_array: np.ndarray)
        """
        self.host = host
        self.port = port
        self.audio_callback = audio_callback
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
                        
                        # Handle audio data event
                        if data.get("event") == "audio_mixed_raw.data":
                            await self._process_audio_message(data, bot_id)
                        
                        # Handle other events (transcript, participant events, etc.)
                        elif data.get("event"):
                            logger.debug(f"Received event: {data['event']}")
                    
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
    
    async def start(self):
        """Start the WebSocket server."""
        logger.info(f"Starting audio receiver on ws://{self.host}:{self.port}")
        
        async with websockets.serve(
            self.handle_connection,
            self.host,
            self.port,
            ping_interval=20,
            ping_timeout=10
        ):
            logger.info("Audio receiver started successfully")
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
