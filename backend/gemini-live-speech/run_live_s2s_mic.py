"""
Gemini Live API: microphone (PCM 16 kHz int16) -> model -> speaker playback.

Requires GOOGLE_API_KEY and a Live-capable native-audio model in GEMINI_LIVE_MODEL.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import queue
import sys
import threading
from typing import Any

import numpy as np
import sounddevice as sd
from google import genai
from google.genai import types

from audio_pcm import INPUT_RATE, float32_to_pcm16le_mono, parse_rate_from_mime
from settings import load_settings


class _Pcm16Player:
    """Thread-safe int16 mono PCM player at a fixed sample rate."""

    def __init__(self, samplerate: int, device: int | None) -> None:
        self._samplerate = int(samplerate)
        self._device = device
        self._buf = bytearray()
        self._lock = threading.Lock()
        self._stream: sd.RawOutputStream | None = None

    def _callback(self, outdata, frames, time_info, status) -> None:  # type: ignore[no-untyped-def]
        if status:
            print(status, file=sys.stderr)
        need = frames * 2
        with self._lock:
            if len(self._buf) >= need:
                chunk = bytes(self._buf[:need])
                del self._buf[:need]
            else:
                chunk = bytes(self._buf)
                del self._buf[:]
                chunk = chunk + b"\x00" * (need - len(chunk))
        audio = np.frombuffer(chunk, dtype=np.int16).reshape(frames, 1)
        outdata[:] = audio

    def start(self) -> None:
        if self._stream is not None:
            return
        self._stream = sd.RawOutputStream(
            samplerate=self._samplerate,
            channels=1,
            dtype="int16",
            blocksize=960,
            device=self._device,
            callback=self._callback,
        )
        self._stream.start()

    def stop(self) -> None:
        if self._stream is None:
            return
        try:
            self._stream.stop()
            self._stream.close()
        finally:
            self._stream = None

    def enqueue(self, pcm16: bytes) -> None:
        if not pcm16:
            return
        with self._lock:
            self._buf.extend(pcm16)


def _print_devices() -> None:
    print(sd.query_devices())


def _extract_audio_chunks(message: types.LiveServerMessage) -> list[tuple[str | None, bytes]]:
    out: list[tuple[str | None, bytes]] = []
    sc = message.server_content
    if not sc or not sc.model_turn or not sc.model_turn.parts:
        return out
    for part in sc.model_turn.parts:
        inline = part.inline_data
        if not inline or not inline.data:
            continue
        mime = inline.mime_type
        m = (mime or "").lower()
        if "audio" in m or "pcm" in m or "l16" in m:
            out.append((mime, bytes(inline.data)))
    return out


def _log_transcription(message: types.LiveServerMessage) -> None:
    sc = message.server_content
    if not sc:
        return
    if sc.input_transcription and sc.input_transcription.text:
        t = sc.input_transcription.text.strip()
        if t:
            print(f"\n[you] {t}")
    if sc.output_transcription and sc.output_transcription.text:
        t = sc.output_transcription.text.strip()
        if t:
            print(f"[model] {t}")


async def _send_mic_audio(session: Any, mic_q: "queue.Queue[bytes]", stop: asyncio.Event) -> None:
    while not stop.is_set():
        try:
            chunk = await asyncio.to_thread(mic_q.get, True, 0.25)
        except queue.Empty:
            continue
        await session.send_realtime_input(
            audio=types.Blob(data=chunk, mime_type=f"audio/pcm;rate={INPUT_RATE}")
        )


async def _receive_audio(session: Any, player: _Pcm16Player, stop: asyncio.Event) -> None:
    while not stop.is_set():
        try:
            async for message in session.receive():
                if stop.is_set():
                    return
                _log_transcription(message)
                for mime, pcm in _extract_audio_chunks(message):
                    _ = parse_rate_from_mime(mime, player._samplerate)
                    player.enqueue(pcm)
        except asyncio.CancelledError:
            return
        except Exception as exc:  # pragma: no cover - network path
            if stop.is_set():
                return
            print(f"\n[receive] {exc}", file=sys.stderr)
            await asyncio.sleep(0.25)


async def _run_session(model: str, api_key: str, language_code: str, voice_name: str, in_dev: int | None, out_dev: int | None) -> None:
    client = genai.Client(api_key=api_key)
    system_text = (
        "You are a concise English voice assistant. "
        "Respond only in English, even if the audio is noisy. "
        "Keep replies short unless the user asks for detail."
    )
    config = types.LiveConnectConfig(
        response_modalities=["AUDIO"],
        speech_config=types.SpeechConfig(
            language_code=language_code,
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice_name)
            ),
        ),
        system_instruction=types.Content(parts=[types.Part(text=system_text)]),
    )

    stop = asyncio.Event()
    mic_q: queue.Queue[bytes] = queue.Queue(maxsize=200)
    output_rate = 24_000
    player = _Pcm16Player(samplerate=output_rate, device=out_dev)

    async with client.aio.live.connect(model=model, config=config) as session:
        player.start()

        def mic_callback(indata, frames, time_info, status) -> None:  # type: ignore[no-untyped-def]
            if status:
                print(status, file=sys.stderr)
            pcm = float32_to_pcm16le_mono(indata.copy())
            try:
                mic_q.put_nowait(pcm)
            except queue.Full:
                pass

        mic_stream = sd.InputStream(
            samplerate=INPUT_RATE,
            channels=1,
            dtype="float32",
            blocksize=int(INPUT_RATE * 0.02),
            device=in_dev,
            callback=mic_callback,
        )
        mic_stream.start()

        send_task = asyncio.create_task(_send_mic_audio(session, mic_q, stop))
        recv_task = asyncio.create_task(_receive_audio(session, player, stop))

        print("Live session started. Speak into the microphone. Ctrl+C to stop.\n")

        try:
            while True:
                await asyncio.sleep(0.25)
        except KeyboardInterrupt:
            stop.set()
        finally:
            stop.set()
            send_task.cancel()
            recv_task.cancel()
            for t in (send_task, recv_task):
                with contextlib.suppress(asyncio.CancelledError):
                    await t
            mic_stream.stop()
            mic_stream.close()
            player.stop()


async def _main_async() -> None:
    settings = load_settings()
    await _run_session(
        model=settings.live_model,
        api_key=settings.google_api_key,
        language_code=settings.language_code,
        voice_name=settings.voice_name,
        in_dev=settings.input_device,
        out_dev=settings.output_device,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Gemini Live speech-to-speech (mic).")
    parser.add_argument("--list-devices", action="store_true", help="Print sounddevice devices and exit.")
    args = parser.parse_args()
    if args.list_devices:
        _print_devices()
        return

    try:
        asyncio.run(_main_async())
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
