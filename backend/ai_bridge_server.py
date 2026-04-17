from __future__ import annotations

import os
import subprocess
import uuid
from pathlib import Path
from typing import Any, Dict

from fastapi import FastAPI
from pydantic import BaseModel


class FixedLineRequest(BaseModel):
    room_id: str
    call_id: str
    phrase: str


app = FastAPI(title="SpeechAgent AI Bridge", version="1.0.0")

BACKEND_DIR = Path(__file__).resolve().parent
MEETING_BOT_DIR = BACKEND_DIR / "meeting-bot"
DOTENV_PATH = MEETING_BOT_DIR / ".env"
PUBLIC_AUDIO_DIR = MEETING_BOT_DIR / "wwwroot" / "generated-audio"


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


def _synthesize_speech_wav(text: str, destination: Path) -> bool:
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


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "healthy", "service": "speechagent-ai-bridge"}


@app.post("/v1/interview/fixed-line")
def fixed_line(req: FixedLineRequest) -> Dict[str, Any]:
    """
    Phase-2 bridge contract:
    - Receives fixed phrase requests from meeting-bot callback on call established.
    - Returns audio_uri for the media runtime when available.
    For now this keeps orchestration and AI service API aligned.
    """
    PUBLIC_AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"fixed-line-{uuid.uuid4().hex}.wav"
    file_path = PUBLIC_AUDIO_DIR / filename
    generated = _synthesize_speech_wav(req.phrase, file_path)

    public_base = _resolve_public_base_url()
    audio_uri = f"{public_base}/generated-audio/{filename}" if generated and public_base else None

    return {
        "ok": True,
        "room_id": req.room_id,
        "call_id": req.call_id,
        "phrase": req.phrase,
        "audio_uri": audio_uri,
        "note": "Generated with local Windows SpeechSynthesizer." if generated else "Failed to synthesize greeting audio.",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("ai_bridge_server:app", host="0.0.0.0", port=8010, reload=False)
