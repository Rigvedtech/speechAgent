from __future__ import annotations

import re
from typing import Tuple

import numpy as np

INPUT_RATE = 16_000


def float32_to_pcm16le_mono(chunk: np.ndarray) -> bytes:
    """sounddevice float32 [-1,1] -> little-endian int16 mono bytes."""
    if chunk.ndim > 1:
        chunk = chunk.mean(axis=1)
    clipped = np.clip(chunk, -1.0, 1.0)
    pcm = (clipped * 32767.0).astype(np.int16)
    return pcm.tobytes()


def parse_rate_from_mime(mime_type: str | None, default: int = 24_000) -> int:
    if not mime_type:
        return default
    m = re.search(r"rate=(\d+)", mime_type, flags=re.IGNORECASE)
    if not m:
        return default
    try:
        return int(m.group(1))
    except ValueError:
        return default


def pcm16le_to_float32(pcm: bytes) -> np.ndarray:
    if not pcm:
        return np.zeros(0, dtype=np.float32)
    i16 = np.frombuffer(pcm, dtype=np.int16)
    return (i16.astype(np.float32) / 32768.0).clip(-1.0, 1.0)


def mime_pcm_to_float32(mime_type: str | None, pcm: bytes) -> Tuple[np.ndarray, int]:
    """Decode common Live API PCM blobs (16-bit LE) using sample rate from mime."""
    rate = parse_rate_from_mime(mime_type, 24_000)
    return pcm16le_to_float32(pcm), rate
