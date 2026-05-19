from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

_HERE = Path(__file__).resolve().parent
load_dotenv(_HERE / ".env", override=False)
load_dotenv(_HERE.parent / ".env", override=False)


def _env_str(key: str, default: str = "") -> str:
    v = os.getenv(key)
    if v is None:
        return default
    v = v.strip()
    return default if v == "" else v


def _env_int(key: str, default: int | None) -> int | None:
    raw = os.getenv(key)
    if raw is None or not str(raw).strip():
        return default
    try:
        return int(str(raw).strip())
    except ValueError:
        return default


@dataclass(frozen=True)
class LiveSpeechSettings:
    google_api_key: str
    live_model: str
    smoke_model: str
    language_code: str
    voice_name: str
    input_device: int | None
    output_device: int | None


def load_settings() -> LiveSpeechSettings:
    key = _env_str("GOOGLE_API_KEY") or _env_str("GEMINI_API_KEY")
    if not key:
        raise RuntimeError(
            "Missing GOOGLE_API_KEY (or GEMINI_API_KEY). Copy .env.example to .env in this folder "
            "or set keys in backend/.env."
        )

    return LiveSpeechSettings(
        google_api_key=key,
        live_model=_env_str(
            "GEMINI_LIVE_MODEL",
            "gemini-2.5-flash-native-audio-preview-12-2025",
        ),
        smoke_model=_env_str("GEMINI_LIVE_SMOKE_MODEL", "gemini-live-2.5-flash-preview"),
        language_code=_env_str("GEMINI_LANGUAGE_CODE", "en-US"),
        voice_name=_env_str("GEMINI_VOICE_NAME", "Puck"),
        input_device=_env_int("INPUT_AUDIO_DEVICE", None),
        output_device=_env_int("OUTPUT_AUDIO_DEVICE", None),
    )
