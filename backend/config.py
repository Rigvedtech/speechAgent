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
SILENCE_DURATION = _env_float("SILENCE_DURATION", 0.8)

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
COMPUTE_TYPE = "float16" if torch.cuda.is_available() else "int8"

# STT: "whisper" (local faster-whisper) or "assemblyai" (cloud).
# If STT_PROVIDER is unset, AssemblyAI is used when an API key is present; otherwise Whisper.
_raw_stt = os.getenv("STT_PROVIDER")
if _raw_stt is None or not str(_raw_stt).strip():
    _aa_key = (os.getenv("ASSEMBLYAI_API_KEY") or os.getenv("AssemblyAI_API_KEY") or "").strip()
    STT_PROVIDER = "assemblyai" if _aa_key else "whisper"
else:
    STT_PROVIDER = str(_raw_stt).strip().lower()

ASSEMBLYAI_API_KEY = (
    os.getenv("ASSEMBLYAI_API_KEY") or os.getenv("AssemblyAI_API_KEY") or ""
).strip()
ASSEMBLYAI_SPEECH_MODELS = _env_str(
    "ASSEMBLYAI_SPEECH_MODELS",
    "universal-2",
)  # comma-separated, e.g. "universal-2" or "universal-3-pro"
ASSEMBLYAI_LANGUAGE_CODE = _env_str("ASSEMBLYAI_LANGUAGE_CODE", "en")

# STT (faster-whisper; used when STT_PROVIDER == "whisper")
MODEL_SIZE = _env_str("MODEL_SIZE", "small.en")

if STT_PROVIDER == "assemblyai":
    print(f"[STT] Backend: AssemblyAI (speech_models={ASSEMBLYAI_SPEECH_MODELS})")
else:
    print(f"[STT] Backend: faster-whisper ({MODEL_SIZE} on {DEVICE})")

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
TTS_RATE = _env_str("TTS_RATE", "+0%")

# First spoken line after mic is ready (override in .env)
_STARTUP_GREETING_DEFAULT = (
    "Hello, I’m Prabhat, and I’ll be your interviewer today. "
    "Let’s begin when you’re ready. Please introduce yourself briefly."
)
STARTUP_GREETING = _env_str("STARTUP_GREETING", _STARTUP_GREETING_DEFAULT)

# Structured interview (JD → 15 questions, phase gate, scorecard). See interview_plan.py / LLMBrain.
def _env_bool(key: str, default: bool) -> bool:
    raw = os.getenv(key)
    if raw is None or not str(raw).strip():
        return default
    return str(raw).strip().lower() in ("1", "true", "yes", "on")


INTERVIEW_STRUCTURED = _env_bool("INTERVIEW_STRUCTURED", True)
INTERVIEW_GATE_FIRST_N = _env_int("INTERVIEW_GATE_FIRST_N", 5)
INTERVIEW_STRIKES_TO_END = _env_int("INTERVIEW_STRIKES_TO_END", 3)
# Extra LLM call per answered scripted question to print Qk/15 relevance in the terminal.
INTERVIEW_TERMINAL_SCORES = _env_bool("INTERVIEW_TERMINAL_SCORES", True)
