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

# TTS (Edge - Fallback)
TTS_VOICE = _env_str("TTS_VOICE", "en-IN-PrabhatNeural")
TTS_RATE = _env_str("TTS_RATE", "+35%")  # Speech rate: +0% to +100% (faster) or -0% to -50% (slower)
TTS_REDUCE_PAUSES = _env_str("TTS_REDUCE_PAUSES", "true").lower() == "true"  # Reduce pauses at full stops

# === SARVAM AI CONFIGURATION ===
# API Key
SARVAM_API_KEY = _env_str("SARVAM_API_KEY", "")

# STT Configuration (Saaras V3)
SARVAM_STT_MODEL = _env_str("SARVAM_STT_MODEL", "saaras:v3")
SARVAM_STT_LANGUAGE = _env_str("SARVAM_STT_LANGUAGE", "en-IN")
SARVAM_STT_MODE = _env_str("SARVAM_STT_MODE", "transcribe")  # transcribe, translate, verbatim, translit, codemix
SARVAM_STT_HIGH_VAD = _env_str("SARVAM_STT_HIGH_VAD", "true").lower() == "true"
SARVAM_STT_ENABLED = _env_str("SARVAM_STT_ENABLED", "true").lower() == "true"

# TTS Configuration (Bulbul V3)
SARVAM_TTS_MODEL = _env_str("SARVAM_TTS_MODEL", "bulbul:v3")
SARVAM_TTS_SPEAKER = _env_str("SARVAM_TTS_SPEAKER", "shubh")  # Default to shubh as requested
SARVAM_TTS_LANGUAGE = _env_str("SARVAM_TTS_LANGUAGE", "en-IN")
SARVAM_TTS_SAMPLE_RATE = _env_int("SARVAM_TTS_SAMPLE_RATE", 24000)  # bulbul:v3 default: 24000
SARVAM_TTS_PACE = _env_float("SARVAM_TTS_PACE", 1.2)  # 0.5 to 2.0, higher = faster
SARVAM_TTS_TEMPERATURE = _env_float("SARVAM_TTS_TEMPERATURE", 0.6)  # 0.01 to 1.0, higher = more variation
SARVAM_TTS_ENABLED = _env_str("SARVAM_TTS_ENABLED", "true").lower() == "true"

# Recall.ai output mode (WebRTC requires media_url from API; file upload is more reliable)
RECALL_USE_OUTPUT_MEDIA = _env_str("RECALL_USE_OUTPUT_MEDIA", "false").lower() == "true"

# Fallback Configuration
STT_FALLBACK_ENABLED = _env_str("STT_FALLBACK_ENABLED", "true").lower() == "true"
TTS_FALLBACK_ENABLED = _env_str("TTS_FALLBACK_ENABLED", "true").lower() == "true"

# Retry Configuration
SARVAM_MAX_RETRIES = _env_int("SARVAM_MAX_RETRIES", 3)
SARVAM_RETRY_BASE_SECONDS = _env_float("SARVAM_RETRY_BASE_SECONDS", 1.0)

# Log Sarvam status
if SARVAM_API_KEY and SARVAM_API_KEY != "your_api_key_here" and SARVAM_API_KEY != "":
    if SARVAM_STT_ENABLED:
        print(f"[STT] Backend: Sarvam AI Saaras V3 (primary) + Faster Whisper (fallback)")
    else:
        print(f"[STT] Backend: Faster Whisper (Sarvam disabled)")
    
    if SARVAM_TTS_ENABLED:
        print(f"[TTS] Backend: Sarvam AI Bulbul V3 - Speaker: {SARVAM_TTS_SPEAKER} (primary) + Edge-TTS (fallback)")
    else:
        print(f"[TTS] Backend: Edge-TTS (Sarvam disabled)")
else:
    print("[Sarvam AI] API key not configured - using fallback engines only")
    SARVAM_STT_ENABLED = False
    SARVAM_TTS_ENABLED = False

# First spoken line after mic is ready (override in .env)
_STARTUP_GREETING_DEFAULT = (
    "Hello, I'm Prabhat, and I'll be your interviewer today. "
    "Let's begin when you're ready. Please introduce yourself briefly."
)
STARTUP_GREETING = _env_str("STARTUP_GREETING", _STARTUP_GREETING_DEFAULT)

# Main asyncio event loop — set once by api_server.py's startup hook.
# Stored here (not in api_server.py) so all modules share the same reference
# regardless of whether api_server is run as __main__ or imported as a module.
main_event_loop = None
