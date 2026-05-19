from __future__ import annotations

import asyncio
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

from config import DEVICE, COMPUTE_TYPE, MODEL_SIZE, SAMPLE_RATE

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


def _transcribe_to_text(model: object, audio: np.ndarray, beam_size: int, *, vad_filter: bool) -> str:
    segments, _info = model.transcribe(  # type: ignore[union-attr]
        audio,
        beam_size=beam_size,
        language="en",
        condition_on_previous_text=False,
        vad_filter=vad_filter,
    )
    # Drop segments Whisper labels as non-speech (common on loopback hiss / muted-ish noise).
    parts: list[str] = []
    for seg in segments:
        nsp = getattr(seg, "no_speech_prob", None)
        if nsp is not None and float(nsp) > 0.72:
            continue
        t = (seg.text or "").strip()
        if t:
            parts.append(t)
    return " ".join(parts).strip()


async def _transcribe_in_thread(
    model: object, audio: np.ndarray, beam_size: int, *, vad_filter: bool = True
) -> str:
    """faster-whisper transcribe is CPU-heavy and must not block the asyncio loop."""
    try:
        return await asyncio.to_thread(_transcribe_to_text, model, audio, beam_size, vad_filter=vad_filter)
    except Exception:
        logger.exception("Whisper transcribe failed")
        return ""


async def _send_json(ws: WebSocket, payload: dict) -> None:
    await ws.send_text(json.dumps(payload))


@app.websocket("/stt")
async def stt_websocket(ws: WebSocket):
    await ws.accept()

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

    # Streaming strategy (Phase 1):
    # - client sends raw PCM16LE mono 16kHz chunks (binary messages)
    # - server accumulates until silence gap, then runs whisper on the buffered audio
    # - emits partial + final messages as JSON text frames
    #
    # Whisper runs in a worker thread (to_thread). The main task must not own ws.receive() alone:
    # while it awaits transcribe, a dedicated task keeps calling ws.receive() and appends PCM to
    # the buffer so TCP/backlog and control frames do not stall (client otherwise sees RST / 10053).

    model = WhisperModel(MODEL_SIZE, device=DEVICE, compute_type=COMPUTE_TYPE)
    state = StreamState(buffer=bytearray(), last_audio_ts=time.time(), last_partial_text="")

    # Loopback capture is often quieter than mic; slightly higher reduces false "speech" timestamps on hiss.
    silence_threshold_rms = 0.0035
    silence_timeout_s = 0.9
    min_audio_s = 0.6
    partial_min_interval_s = 2.0
    # Loopback often has non-silence noise; if last_audio_ts never ages, flush never runs and the
    # buffer grows until Whisper tries to allocate multi‑GiB STFT buffers and the process dies (10054).
    max_buffer_bytes = int(45 * SAMPLE_RATE * 2)

    # Text control frames only (low volume). Binary PCM is merged in the receiver task so
    # ws.receive() never blocks behind a full Queue while the main task awaits transcribe.
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

        # Hard cap segment length passed to Whisper (safety if buffer grew before trim landed).
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
        await _send_json(ws, {"type": "ready", "sample_rate": SAMPLE_RATE})

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
    return {"status": "healthy", "service": "speechagent-stt-stream"}


if __name__ == "__main__":
    import uvicorn

    print("[Mode] STT websocket server: ws://0.0.0.0:8020/stt")
    uvicorn.run("stt_server:app", host="0.0.0.0", port=8020, reload=False)

