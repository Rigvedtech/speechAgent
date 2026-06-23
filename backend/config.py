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


def _env_bool(key: str, default: bool) -> bool:
    raw = os.getenv(key)
    if raw is None or not str(raw).strip():
        return default
    return str(raw).strip().lower() in ("1", "true", "yes", "on")


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
GROQ_TEMPERATURE = _env_float("GROQ_TEMPERATURE", 0.3)
GROQ_MAX_TOKENS = _env_int("GROQ_MAX_TOKENS", 90)
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

# Sarvam STT collector tuning (production defaults for fuller turns)
SARVAM_STT_COLLECT_DEADLINE_SEC = _env_float("SARVAM_STT_COLLECT_DEADLINE_SEC", 10.0)
SARVAM_STT_TRAILING_SILENCE_SEC = _env_float("SARVAM_STT_TRAILING_SILENCE_SEC", 0.9)
SARVAM_STT_WAIT_AFTER_END_SEC = _env_float("SARVAM_STT_WAIT_AFTER_END_SEC", 0.6)

# Endpointing split by engine (keeps Whisper behavior stable)
SARVAM_LOCAL_SILENCE_SEC = _env_float("SARVAM_LOCAL_SILENCE_SEC", 1.4)
WHISPER_LOCAL_SILENCE_SEC = _env_float("WHISPER_LOCAL_SILENCE_SEC", 1.0)

# Quality gate: for long utterances, reject ultra-short Sarvam finals and fallback
SARVAM_QUALITY_MIN_UTTERANCE_SEC = _env_float("SARVAM_QUALITY_MIN_UTTERANCE_SEC", 2.5)
SARVAM_QUALITY_MIN_CHARS = _env_int("SARVAM_QUALITY_MIN_CHARS", 12)

# Turn commit / merge guard (split VAD endpoints → single scored turn)
TURN_MERGE_ENABLED = _env_bool("TURN_MERGE_ENABLED", True)
TURN_MERGE_WINDOW_SEC = _env_float("TURN_MERGE_WINDOW_SEC", 3.0)
TURN_MERGE_MIN_AUDIO_SEC = _env_float("TURN_MERGE_MIN_AUDIO_SEC", 2.5)
TURN_MERGE_MIN_CHARS = _env_int("TURN_MERGE_MIN_CHARS", 20)
TURN_MERGE_MIN_HOLD_SEC = _env_float("TURN_MERGE_MIN_HOLD_SEC", 1.5)
TURN_MERGE_MAX_SHORT_HOLD_SEC = _env_float("TURN_MERGE_MAX_SHORT_HOLD_SEC", 4.0)

# Progress gate: rule-layer thresholds for long off-topic answers
PROGRESS_GATE_LONG_ANSWER_SEC = _env_float("PROGRESS_GATE_LONG_ANSWER_SEC", 25.0)
PROGRESS_GATE_MIN_TOPIC_OVERLAP = _env_int("PROGRESS_GATE_MIN_TOPIC_OVERLAP", 2)
PROGRESS_GATE_UNCLEAR_ESCALATION_CHECKS = _env_int("PROGRESS_GATE_UNCLEAR_ESCALATION_CHECKS", 2)

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

# Interview language (POST /api/start language_mode; default when omitted)
DEFAULT_INTERVIEW_LANGUAGE = _env_str("DEFAULT_INTERVIEW_LANGUAGE", "english").lower()
LANG_ENGLISH_STT_LANGUAGE = _env_str("LANG_ENGLISH_STT_LANGUAGE", "en-IN")
LANG_ENGLISH_STT_MODE = _env_str("LANG_ENGLISH_STT_MODE", "transcribe")
LANG_ENGLISH_TTS_LANGUAGE = _env_str("LANG_ENGLISH_TTS_LANGUAGE", "en-IN")
LANG_HINGLISH_STT_LANGUAGE = _env_str("LANG_HINGLISH_STT_LANGUAGE", "hi-IN")
LANG_HINGLISH_STT_MODE = _env_str("LANG_HINGLISH_STT_MODE", "codemix")
LANG_HINGLISH_TTS_LANGUAGE = _env_str("LANG_HINGLISH_TTS_LANGUAGE", "hi-IN")

# Log Sarvam status
if SARVAM_API_KEY and SARVAM_API_KEY != "your_api_key_here" and SARVAM_API_KEY != "":
    if SARVAM_STT_ENABLED:
        if STT_FALLBACK_ENABLED:
            print(f"[STT] Backend: Sarvam AI Saaras V3 (primary) + Faster Whisper (lazy fallback)")
        else:
            print(f"[STT] Backend: Sarvam AI Saaras V3 only (fallback disabled)")
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

# Interview orchestration
MAX_QUESTIONS = _env_int("MAX_QUESTIONS", 10)
MAX_ANSWER_SEC = _env_int("MAX_ANSWER_SEC", 120)
MAX_OFF_TOPIC_REDIRECTS = _env_int("MAX_OFF_TOPIC_REDIRECTS", 2)
MAX_STRIKES = _env_int("MAX_STRIKES", 3)
MAX_INTERVIEW_MINUTES = _env_int("MAX_INTERVIEW_MINUTES", 30)
CONTINUE_AVG_THRESHOLD = _env_float("CONTINUE_AVG_THRESHOLD", 7.0)
ROLLING_WINDOW = _env_int("ROLLING_WINDOW", 4)
ABUSE_MAX_WARNINGS = _env_int("ABUSE_MAX_WARNINGS", 1)

# Turn-taking: user cannot interrupt bot; bot may ask mid-answer clarifiers
USER_BARGE_IN_ENABLED = _env_str("USER_BARGE_IN_ENABLED", "false").lower() == "true"
BOT_INTERRUPT_ENABLED = _env_bool("BOT_INTERRUPT_ENABLED", True)
BOT_INTERRUPT_MIN_SPEECH_SEC = _env_float("BOT_INTERRUPT_MIN_SPEECH_SEC", 15.0)
BOT_INTERRUPT_CHECK_INTERVAL_SEC = _env_float("BOT_INTERRUPT_CHECK_INTERVAL_SEC", 10.0)
BOT_INTERRUPT_SHORT_ANSWER_MAX_SEC = _env_float("BOT_INTERRUPT_SHORT_ANSWER_MAX_SEC", 13.0)
BOT_INTERRUPT_MIN_PARTIAL_SEC = _env_float("BOT_INTERRUPT_MIN_PARTIAL_SEC", 2.5)
BOT_INTERRUPT_DRAG_STRIKES_MAX = _env_int("BOT_INTERRUPT_DRAG_STRIKES_MAX", 2)
BOT_INTERRUPT_GATE_MIN_CONFIDENCE = _env_float("BOT_INTERRUPT_GATE_MIN_CONFIDENCE", 0.75)
BOT_INTERRUPT_MAX_CLARIFIERS_PER_Q = _env_int("BOT_INTERRUPT_MAX_CLARIFIERS_PER_Q", 2)

# Meta-requests during Q&A (repeat / rephrase question — not scored)
MAX_QUESTION_REPEATS = _env_int("MAX_QUESTION_REPEATS", 2)
MAX_QUESTION_REPHRASES = _env_int("MAX_QUESTION_REPHRASES", 1)

# Interview quality: name normalization and incomplete-answer guard
NAME_NORMALIZE_ENABLED = _env_bool("NAME_NORMALIZE_ENABLED", True)
MIN_ANSWER_WORDS = _env_int("MIN_ANSWER_WORDS", 8)
MIN_SHORT_COMPLETE_WORDS = _env_int("MIN_SHORT_COMPLETE_WORDS", 5)
MAX_ANSWER_CONTINUATIONS = _env_int("MAX_ANSWER_CONTINUATIONS", 1)
INCOMPLETE_ANSWER_CHECK_ENABLED = _env_bool("INCOMPLETE_ANSWER_CHECK_ENABLED", True)

# Post-TTS silence: confirm candidate can hear after bot finishes speaking
POST_TTS_SILENCE_CHECK_ENABLED = _env_bool("POST_TTS_SILENCE_CHECK_ENABLED", True)
POST_TTS_SILENCE_CHECK_SEC = _env_float("POST_TTS_SILENCE_CHECK_SEC", 5.0)
MAX_PRESENCE_CHECKS_PER_QUESTION = _env_int("MAX_PRESENCE_CHECKS_PER_QUESTION", 1)

# Latency: preload Whisper at session start (avoids ~2s first-fallback delay)
WHISPER_PRELOAD_ENABLED = _env_bool("WHISPER_PRELOAD_ENABLED", True)

# Turn intent classifier (repeat/rephrase vs actual answer — LLM-based)
TURN_INTENT_CLASSIFIER_ENABLED = _env_bool("TURN_INTENT_CLASSIFIER_ENABLED", True)
TURN_INTENT_MAX_CHARS = _env_int("TURN_INTENT_MAX_CHARS", 150)
TURN_INTENT_MIN_CONFIDENCE = _env_float("TURN_INTENT_MIN_CONFIDENCE", 0.65)

# Main asyncio event loop — set once by api_server.py's startup hook.
# Stored here (not in api_server.py) so all modules share the same reference
# regardless of whether api_server is run as __main__ or imported as a module.
main_event_loop = None
