import os
import torch
from dotenv import load_dotenv

load_dotenv()


def _env_str(key: str, default: str) -> str:
    v = os.getenv(key)
    if v is None:
        return default
    v = v.strip()
    return default if v == "" else v


def _env_int(key: str, default: int) -> int:
    raw = os.getenv(key)
    if raw is None or not str(raw).strip():
        return default
    try:
        return int(str(raw).strip())
    except ValueError:
        return default


def _env_float(key: str, default: float) -> float:
    raw = os.getenv(key)
    if raw is None or not str(raw).strip():
        return default
    try:
        return float(str(raw).strip())
    except ValueError:
        return default


# Audio (STT / VAD)
SAMPLE_RATE = _env_int("SAMPLE_RATE", 16000)
CHANNELS = _env_int("CHANNELS", 1)
SILENCE_DURATION = _env_float("SILENCE_DURATION", 1.2)  # Increased from 0.8s to 1.2s to avoid splitting speech

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
COMPUTE_TYPE = "float16" if torch.cuda.is_available() else "int8"

# STT (faster-whisper)
MODEL_SIZE = _env_str("MODEL_SIZE", "small.en")

# LLM
OLLAMA_MODEL = _env_str("OLLAMA_MODEL", "llama3.2:3b")
GROQ_MODEL = _env_str("GROQ_MODEL", "llama-3.1-8b-instant")
GROQ_API_KEY = _env_str("GROQ_API_KEY", "")

if GROQ_API_KEY and GROQ_API_KEY != "your_api_key_here":
    print("[LLM] Backend: Groq API (ultra-low latency)")
else:
    print("[LLM] Backend: Local Ollama (set GROQ_API_KEY in .env for faster responses)")
    GROQ_API_KEY = ""

# TTS (Edge)
TTS_VOICE = _env_str("TTS_VOICE", "en-IN-PrabhatNeural")
TTS_RATE = _env_str("TTS_RATE", "+35%")  # Speech rate: +0% to +100% (faster) or -0% to -50% (slower)
TTS_REDUCE_PAUSES = _env_str("TTS_REDUCE_PAUSES", "true").lower() == "true"  # Reduce pauses at full stops

# First spoken line after mic is ready (override in .env)
_STARTUP_GREETING_DEFAULT = (
    "Hello, I’m Prabhat, and I’ll be your interviewer today. "
    "Let’s begin when you’re ready. Please introduce yourself briefly."
)
STARTUP_GREETING = _env_str("STARTUP_GREETING", _STARTUP_GREETING_DEFAULT)
