"""
AssemblyAI pre-recorded transcription for float32 mono PCM (used by stt_engine + stt_server).

Requires: pip install assemblyai
Env: ASSEMBLYAI_API_KEY or AssemblyAI_API_KEY (see config.py)
"""
from __future__ import annotations

import io
import logging
import wave
from typing import TYPE_CHECKING, Optional

import numpy as np

if TYPE_CHECKING:
    import assemblyai as aai

logger = logging.getLogger(__name__)

_transcriber: Optional[object] = None


def float32_to_wav_bytes(samples: np.ndarray, sample_rate: int) -> bytes:
    """Mono float32 [-1, 1] -> 16-bit PCM WAV bytes."""
    flat = np.asarray(samples, dtype=np.float32).flatten()
    flat = np.clip(flat, -1.0, 1.0)
    pcm16 = (flat * 32767.0).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(int(sample_rate))
        wf.writeframes(pcm16.tobytes())
    return buf.getvalue()


def _get_transcriber():
    global _transcriber
    if _transcriber is not None:
        return _transcriber

    import assemblyai as aai

    from config import ASSEMBLYAI_API_KEY, ASSEMBLYAI_SPEECH_MODELS

    if not ASSEMBLYAI_API_KEY:
        raise ValueError(
            "AssemblyAI API key missing. Set ASSEMBLYAI_API_KEY or AssemblyAI_API_KEY in .env."
        )

    aai.settings.api_key = ASSEMBLYAI_API_KEY
    _transcriber = aai.Transcriber()
    logger.info(
        "AssemblyAI Transcriber ready (speech_models=%s).",
        ASSEMBLYAI_SPEECH_MODELS,
    )
    return _transcriber


def build_transcription_config():
    import assemblyai as aai

    from config import ASSEMBLYAI_LANGUAGE_CODE, ASSEMBLYAI_SPEECH_MODELS

    models = [m.strip() for m in ASSEMBLYAI_SPEECH_MODELS.split(",") if m.strip()]
    if not models:
        models = ["universal-2"]
    return aai.TranscriptionConfig(
        speech_models=models,
        language_code=ASSEMBLYAI_LANGUAGE_CODE or None,
    )


def transcribe_float32_mono(
    audio_f32: np.ndarray,
    sample_rate: int,
) -> str:
    """
    Upload WAV derived from float32 mono PCM and return plain transcript text.
    Blocks until AssemblyAI completes (network + queue latency).
    """
    import assemblyai as aai

    wav = float32_to_wav_bytes(audio_f32, sample_rate)
    bio = io.BytesIO(wav)
    bio.seek(0)

    transcriber = _get_transcriber()
    config = build_transcription_config()
    transcript = transcriber.transcribe(bio, config=config)

    if transcript.status == aai.TranscriptStatus.error:
        err = getattr(transcript, "error", None) or "unknown error"
        logger.error("AssemblyAI transcription failed: %s", err)
        return ""

    text = (transcript.text or "").strip()
    return text
