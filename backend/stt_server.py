from __future__ import annotations

import asyncio
import importlib.util
import json
import logging
import time
from dataclasses import dataclass
from typing import Optional

import numpy as np
from fastapi import FastAPI, WebSocket, WebSocketDisconnect

try:
    from faster_whisper import WhisperModel  # type: ignore
except Exception:  # pragma: no cover
    WhisperModel = None  # type: ignore

from config import (
    ASSEMBLYAI_API_KEY,
    DEVICE,
    COMPUTE_TYPE,
    MODEL_SIZE,
    SAMPLE_RATE,
    STT_PROVIDER,
)

logger = logging.getLogger("stt_server")

app = FastAPI(title="SpeechAgent STT Stream", version="1.0.0")


@dataclass
class StreamState:
    buffer: bytearray
    last_audio_ts: float
    last_partial_text: str
    last_partial_at: float = 0.0


def _pcm16le_to_float32(pcm: bytes) -> np.ndarray:
    arr = np.frombuffer(pcm, dtype=np.int16).astype(np.float32)
    return arr / 32768.0


def _rms(x: np.ndarray) -> float:
    if x.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(np.square(x))))


def _transcribe_to_text_whisper(model: object, audio: np.ndarray, beam_size: int, *, vad_filter: bool) -> str:
    segments, _info = model.transcribe(  # type: ignore[union-attr]
        audio,
        beam_size=beam_size,
        language="en",
        condition_on_previous_text=False,
        vad_filter=vad_filter,
    )
    parts: list[str] = []
    for seg in segments:
        nsp = getattr(seg, "no_speech_prob", None)
        if nsp is not None and float(nsp) > 0.72:
            continue
        t = (seg.text or "").strip()
        if t:
            parts.append(t)
    return " ".join(parts).strip()


def _transcribe_to_text_assembly(audio: np.ndarray) -> str:
    from stt_assemblyai import transcribe_float32_mono

    return transcribe_float32_mono(audio, SAMPLE_RATE)


def _transcribe_to_text(
    model: object | None, audio: np.ndarray, beam_size: int, *, vad_filter: bool
) -> str:
    if STT_PROVIDER == "assemblyai":
        return _transcribe_to_text_assembly(audio)
    return _transcribe_to_text_whisper(model, audio, beam_size, vad_filter=vad_filter)  # type: ignore[arg-type]


async def _transcribe_in_thread(
    model: object | None, audio: np.ndarray, beam_size: int, *, vad_filter: bool = True
) -> str:
    """STT must not block the asyncio loop."""
    try:
        return await asyncio.to_thread(
            _transcribe_to_text, model, audio, beam_size, vad_filter=vad_filter
        )
    except Exception:
        logger.exception("STT transcribe failed (%s)", STT_PROVIDER)
        return ""


async def _send_json(ws: WebSocket, payload: dict) -> None:
    await ws.send_text(json.dumps(payload))


@app.websocket("/stt")
async def stt_websocket(ws: WebSocket):
    await ws.accept()

    if STT_PROVIDER == "assemblyai":
        if not ASSEMBLYAI_API_KEY:
            await _send_json(
                ws,
                {
                    "type": "error",
                    "message": "STT_PROVIDER=assemblyai but ASSEMBLYAI_API_KEY / AssemblyAI_API_KEY is missing in .env.",
                },
            )
            await ws.close()
            return
        if importlib.util.find_spec("assemblyai") is None:
            await _send_json(
                ws,
                {
                    "type": "error",
                    "message": "assemblyai package not installed. Run: pip install assemblyai",
                },
            )
            await ws.close()
            return
        model = None
    else:
        if WhisperModel is None:
            await _send_json(
                ws,
                {
                    "type": "error",
                    "message": "faster-whisper is not installed in this Python environment. Install requirements.txt first.",
                },
            )
            await ws.close()
            return
        model = WhisperModel(MODEL_SIZE, device=DEVICE, compute_type=COMPUTE_TYPE)

    state = StreamState(buffer=bytearray(), last_audio_ts=time.time(), last_partial_text="")

    silence_threshold_rms = 0.0035
    silence_timeout_s = 0.9
    min_audio_s = 0.6
    partial_min_interval_s = 2.0
    max_buffer_bytes = int(45 * SAMPLE_RATE * 2)

    control_queue: asyncio.Queue[dict | None] = asyncio.Queue()
    buffer_lock = asyncio.Lock()

    async def pump_ws_to_buffer() -> None:
        try:
            while True:
                msg = await ws.receive()
                if msg.get("type") == "websocket.disconnect":
                    await control_queue.put(None)
                    return

                if msg.get("bytes") is not None:
                    chunk = msg["bytes"]
                    audio = _pcm16le_to_float32(chunk)
                    async with buffer_lock:
                        if _rms(audio) > silence_threshold_rms:
                            state.last_audio_ts = time.time()
                        state.buffer.extend(chunk)
                        if len(state.buffer) > max_buffer_bytes:
                            drop = len(state.buffer) - max_buffer_bytes
                            del state.buffer[:drop]
                elif msg.get("text"):
                    await control_queue.put(msg)
        except WebSocketDisconnect:
            await control_queue.put(None)
        except Exception:
            await control_queue.put(None)

    async def flush_if_silent(force: bool = False) -> Optional[str]:
        now = time.time()
        async with buffer_lock:
            if not state.buffer:
                return None

            silent_for = now - state.last_audio_ts
            audio_s = len(state.buffer) / 2 / SAMPLE_RATE
            if not force and (silent_for < silence_timeout_s or audio_s < min_audio_s):
                return None

            raw = bytes(state.buffer)
            state.buffer.clear()

        max_pcm_bytes = max_buffer_bytes
        if len(raw) > max_pcm_bytes:
            raw = raw[-max_pcm_bytes:]
        audio = _pcm16le_to_float32(raw)
        if _rms(audio) < 0.0022:
            return None

        text = await _transcribe_in_thread(model, audio, beam_size=3, vad_filter=True)
        return text or None

    async def _maybe_emit_partial() -> None:
        async with buffer_lock:
            audio_s = len(state.buffer) / 2 / SAMPLE_RATE
            now = time.time()
            if audio_s < 2.0 or (now - state.last_partial_at) < partial_min_interval_s:
                return
            state.last_partial_at = now
            recent = bytes(state.buffer[-int(1.5 * SAMPLE_RATE) * 2 :])

        recent_audio = _pcm16le_to_float32(recent)
        if _rms(recent_audio) < 0.0022:
            return
        partial = await _transcribe_in_thread(model, recent_audio, beam_size=1, vad_filter=True)
        if partial and partial != state.last_partial_text:
            state.last_partial_text = partial
            await _send_json(ws, {"type": "partial", "text": partial})

    recv_task = asyncio.create_task(pump_ws_to_buffer())

    try:
        await _send_json(
            ws,
            {
                "type": "ready",
                "sample_rate": SAMPLE_RATE,
                "stt_provider": STT_PROVIDER,
            },
        )

        while True:
            try:
                msg = await asyncio.wait_for(control_queue.get(), timeout=0.25)
            except asyncio.TimeoutError:
                final_text = await flush_if_silent(force=False)
                if final_text:
                    await _send_json(ws, {"type": "final", "text": final_text})
                await _maybe_emit_partial()
                continue

            if msg is None:
                break

            if msg.get("text"):
                try:
                    ctrl = json.loads(msg["text"])
                except Exception:
                    ctrl = {}

                if ctrl.get("type") == "flush":
                    final_text = await flush_if_silent(force=True)
                    if final_text:
                        await _send_json(ws, {"type": "final", "text": final_text})
                elif ctrl.get("type") == "close":
                    break

            await _maybe_emit_partial()

    except WebSocketDisconnect:
        return
    finally:
        recv_task.cancel()
        try:
            await recv_task
        except asyncio.CancelledError:
            pass
        except Exception:
            pass


@app.get("/health")
def health():
    return {"status": "healthy", "service": "speechagent-stt-stream", "stt_provider": STT_PROVIDER}


if __name__ == "__main__":
    import uvicorn

    print(f"[Mode] STT websocket server: ws://0.0.0.0:8020/stt (provider={STT_PROVIDER})")
    uvicorn.run("stt_server:app", host="0.0.0.0", port=8020, reload=False)
