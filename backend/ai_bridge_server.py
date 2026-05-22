from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import time
import uuid
from pathlib import Path
from threading import Lock
from typing import Any, Dict, List, Optional, Tuple

from dotenv import load_dotenv
from fastapi import FastAPI
from pydantic import BaseModel

from llm_brain import LLMBrain
from state import AgentState


class FixedLineRequest(BaseModel):
    room_id: str
    call_id: str
    phrase: str


class TurnRequest(BaseModel):
    room_id: str
    call_id: str
    transcript: str
    turn_id: str
    history: List[str] = []


app = FastAPI(title="SpeechAgent AI Bridge", version="1.0.0")

BACKEND_DIR = Path(__file__).resolve().parent
MEETING_BOT_DIR = BACKEND_DIR / "meeting-bot"
DOTENV_PATH = MEETING_BOT_DIR / ".env"
PUBLIC_AUDIO_DIR = MEETING_BOT_DIR / "wwwroot" / "generated-audio"
# One LLMBrain per room so Teams path matches standalone `main.py` (SYSTEM_PROMPT, JD/resume, persona, history).
ROOM_BRAINS: Dict[str, LLMBrain] = {}
ROOM_BRAINS_LOCK = Lock()

# Same env files as standalone pipeline (TTS_VOICE, TTS_RATE, LLM keys, etc.)
load_dotenv(BACKEND_DIR / ".env", override=False)
load_dotenv(MEETING_BOT_DIR / ".env", override=False)


def _load_env_file(path: Path) -> Dict[str, str]:
    values: Dict[str, str] = {}
    if not path.exists():
        return values

    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _resolve_public_base_url() -> str:
    env_file = _load_env_file(DOTENV_PATH)
    candidates = [
        os.getenv("MEETINGBOT_PUBLIC_SERVICE_HOST", ""),
        os.getenv("MEETINGBOT_CALLBACK_BASE_URL", ""),
        env_file.get("MeetingBot__PublicServiceHost", ""),
        env_file.get("MeetingBot__CallbackBaseUrl", ""),
    ]
    for value in candidates:
        if value and value.strip():
            return value.strip().rstrip("/")
    return ""


def _tts_voice_and_rate() -> tuple[str, str]:
    voice = (os.getenv("TTS_VOICE") or "en-IN-PrabhatNeural").strip() or "en-IN-PrabhatNeural"
    rate = (os.getenv("TTS_RATE") or "+0%").strip() or "+0%"
    return voice, rate


def _synthesize_speech_wav_windows_sapi(text: str, destination: Path) -> bool:
    escaped_text = text.replace("'", "''")
    escaped_path = str(destination).replace("'", "''")
    script = (
        "Add-Type -AssemblyName System.Speech;"
        "$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer;"
        "$synth.SetOutputToWaveFile('{path}');"
        "$synth.Speak('{text}');"
        "$synth.Dispose();"
    ).format(path=escaped_path, text=escaped_text)

    result = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0 and destination.exists() and destination.stat().st_size > 0


async def _edge_tts_save_mp3(text: str, out_mp3: Path) -> bool:
    import edge_tts

    voice, rate = _tts_voice_and_rate()
    communicate = edge_tts.Communicate(text, voice, rate=rate)
    await communicate.save(str(out_mp3))
    return out_mp3.exists() and out_mp3.stat().st_size > 0


def _ffmpeg_mp3_to_wav(mp3: Path, wav: Path) -> bool:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return False
    try:
        result = subprocess.run(
            [
                ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-i",
                str(mp3),
                "-ar",
                "16000",
                "-ac",
                "1",
                str(wav),
            ],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        return result.returncode == 0 and wav.exists() and wav.stat().st_size > 0
    except Exception:
        return False


def _synthesize_meeting_audio(text: str, base_name: str) -> Tuple[bool, Optional[Path], str]:
    """
    Prefer Microsoft Edge neural TTS (same voice as standalone `main.py`, e.g. en-IN-PrabhatNeural).
    Produces 16 kHz mono WAV when ffmpeg is available; otherwise keeps MP3 for playPrompt.
    Falls back to Windows SAPI WAV if Edge fails.
    """
    PUBLIC_AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    wav_path = PUBLIC_AUDIO_DIR / f"{base_name}.wav"
    mp3_tmp = PUBLIC_AUDIO_DIR / f"{base_name}.tmp.mp3"
    mp3_final = PUBLIC_AUDIO_DIR / f"{base_name}.mp3"

    try:
        mp3_tmp.unlink(missing_ok=True)
    except Exception:
        pass

    try:
        asyncio.run(_edge_tts_save_mp3(text, mp3_tmp))
    except Exception:
        mp3_tmp.unlink(missing_ok=True)
        if _synthesize_speech_wav_windows_sapi(text, wav_path):
            return True, wav_path, "Windows SpeechSynthesizer (Edge TTS failed to run)."
        return False, None, "Edge TTS and Windows Speech fallback both failed."

    if not mp3_tmp.exists() or mp3_tmp.stat().st_size == 0:
        if _synthesize_speech_wav_windows_sapi(text, wav_path):
            return True, wav_path, "Windows SpeechSynthesizer (Edge produced no audio)."
        return False, None, "Edge TTS produced no audio and SAPI fallback failed."

    if _ffmpeg_mp3_to_wav(mp3_tmp, wav_path):
        try:
            mp3_tmp.unlink(missing_ok=True)
        except Exception:
            pass
        voice, _ = _tts_voice_and_rate()
        return True, wav_path, f"Microsoft Edge TTS ({voice}) -> WAV via ffmpeg."

    try:
        mp3_tmp.replace(mp3_final)
    except Exception:
        shutil.move(str(mp3_tmp), str(mp3_final))

    voice, _ = _tts_voice_and_rate()
    return (
        True,
        mp3_final,
        f"Microsoft Edge TTS ({voice}) MP3. Install ffmpeg and ensure it is on PATH for 16 kHz WAV (recommended for Teams playPrompt).",
    )


def _brain_for_room(room_id: str) -> LLMBrain:
    with ROOM_BRAINS_LOCK:
        brain = ROOM_BRAINS.get(room_id)
        if brain is None:
            brain = LLMBrain(AgentState())
            ROOM_BRAINS[room_id] = brain
        return brain


def _load_reply_text(room_id: str, transcript: str, history: List[str]) -> str:
    """Same interview stack as `main.py` / LLMBrain (system prompt, documents, persona, multi-turn)."""
    del history  # C# sends last reply only; full context lives on the Python brain per room_id.

    transcript = (transcript or "").strip()
    if not transcript:
        return "I could not hear you clearly. Could you repeat your answer in one sentence?"

    brain = _brain_for_room(room_id)
    brain.conversation_history.append({"role": "user", "content": transcript})
    if len(brain.conversation_history) > (brain.max_runtime_history_messages + 2):
        brain.conversation_history = brain.conversation_history[-brain.max_runtime_history_messages :]

    return brain.complete_turn_sync_for_bridge()


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "healthy", "service": "speechagent-ai-bridge"}


@app.post("/v1/interview/fixed-line")
def fixed_line(req: FixedLineRequest) -> Dict[str, Any]:
    """
    Phase-2 bridge contract:
    - Receives fixed phrase requests from meeting-bot callback on call established.
    - Returns audio_uri for the media runtime when available.
    """
    base = f"fixed-line-{uuid.uuid4().hex}"
    generated, out_path, note = _synthesize_meeting_audio(req.phrase, base)

    public_base = _resolve_public_base_url()
    audio_uri = f"{public_base}/generated-audio/{out_path.name}" if generated and out_path and public_base else None

    return {
        "ok": True,
        "room_id": req.room_id,
        "call_id": req.call_id,
        "phrase": req.phrase,
        "audio_uri": audio_uri,
        "note": note if generated else "Failed to synthesize greeting audio.",
    }


@app.post("/v1/interview/respond")
def respond(req: TurnRequest) -> Dict[str, Any]:
    start = time.perf_counter()

    reply_text = _load_reply_text(req.room_id, req.transcript, req.history)
    base = f"turn-{req.turn_id}-{uuid.uuid4().hex}"
    generated, out_path, note = _synthesize_meeting_audio(reply_text, base)

    public_base = _resolve_public_base_url()
    audio_uri = f"{public_base}/generated-audio/{out_path.name}" if generated and out_path and public_base else None
    latency_ms = int((time.perf_counter() - start) * 1000)

    return {
        "ok": True,
        "room_id": req.room_id,
        "call_id": req.call_id,
        "turn_id": req.turn_id,
        "reply_text": reply_text,
        "audio_uri": audio_uri,
        "latency_ms": latency_ms,
        "trace_id": req.turn_id,
        "note": note if generated else "Failed to synthesize turn response audio.",
    }


if __name__ == "__main__":
    import uvicorn

    print("[Mode] Meeting-bot bridge mode: HTTP API only (no local mic loop).")
    uvicorn.run("ai_bridge_server:app", host="0.0.0.0", port=8010, reload=False)
