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
# Faster model for answer scoring only (keeps main GROQ_MODEL for clarifiers/intent).
GROQ_EVALUATOR_MODEL = _env_str("GROQ_EVALUATOR_MODEL", GROQ_MODEL)
GROQ_EVALUATOR_MAX_TOKENS = _env_int("GROQ_EVALUATOR_MAX_TOKENS", 250)
GROQ_TEMPERATURE = _env_float("GROQ_TEMPERATURE", 0.3)
GROQ_MAX_TOKENS = _env_int("GROQ_MAX_TOKENS", 90)
GROQ_REQUEST_TIMEOUT_SEC = _env_float("GROQ_REQUEST_TIMEOUT_SEC", 45.0)
GROQ_API_KEY = _env_str("GROQ_API_KEY", "")
# Ollama fallback for evaluator can block 60s+ if Ollama is down — off by default in production.
OLLAMA_EVALUATOR_FALLBACK = _env_bool("OLLAMA_EVALUATOR_FALLBACK", False)

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
SARVAM_STT_COLLECT_DEADLINE_MAX_SEC = _env_float("SARVAM_STT_COLLECT_DEADLINE_MAX_SEC", 60.0)
SARVAM_STT_TRANSCRIBE_TIMEOUT_SEC = _env_float("SARVAM_STT_TRANSCRIBE_TIMEOUT_SEC", 12.0)
SARVAM_STT_TRANSCRIBE_TIMEOUT_MAX_SEC = _env_float("SARVAM_STT_TRANSCRIBE_TIMEOUT_MAX_SEC", 90.0)
SARVAM_STT_TRAILING_SILENCE_SEC = _env_float("SARVAM_STT_TRAILING_SILENCE_SEC", 0.55)
SARVAM_STT_WAIT_AFTER_END_SEC = _env_float("SARVAM_STT_WAIT_AFTER_END_SEC", 0.35)


def sarvam_collect_deadline_sec(utterance_duration: float) -> float:
    """Scale Sarvam transcript collection window with answer length."""
    base = SARVAM_STT_COLLECT_DEADLINE_SEC
    scaled = utterance_duration * 0.35 + 8.0
    return min(max(base, scaled), SARVAM_STT_COLLECT_DEADLINE_MAX_SEC)


def sarvam_transcribe_timeout_sec(utterance_duration: float) -> float:
    """Scale blocking transcribe_sync timeout with answer length."""
    base = SARVAM_STT_TRANSCRIBE_TIMEOUT_SEC
    scaled = utterance_duration * 0.45 + 10.0
    return min(max(base, scaled), SARVAM_STT_TRANSCRIBE_TIMEOUT_MAX_SEC)

# Endpointing split by engine (keeps Whisper behavior stable)
SARVAM_LOCAL_SILENCE_SEC = _env_float("SARVAM_LOCAL_SILENCE_SEC", 2.0)

# Hinglish: short bridge ("Theek hai.") when score >= threshold; full rephrase intro below
HINGLISH_SIMPLE_BRIDGE_MIN_SCORE = _env_int("HINGLISH_SIMPLE_BRIDGE_MIN_SCORE", 7)
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

# TTS Configuration (Bulbul V3)
SARVAM_TTS_MODEL = _env_str("SARVAM_TTS_MODEL", "bulbul:v3")
SARVAM_TTS_SPEAKER = _env_str("SARVAM_TTS_SPEAKER", "shubh")  # Default to shubh as requested
SARVAM_TTS_LANGUAGE = _env_str("SARVAM_TTS_LANGUAGE", "en-IN")
SARVAM_TTS_SAMPLE_RATE = _env_int("SARVAM_TTS_SAMPLE_RATE", 24000)  # bulbul:v3 default: 24000
SARVAM_TTS_PACE = _env_float("SARVAM_TTS_PACE", 0.9)  # 0.5 to 2.0, higher = faster
SARVAM_TTS_TEMPERATURE = _env_float("SARVAM_TTS_TEMPERATURE", 0.35)  # lower = cleaner voice
SARVAM_TTS_ENABLED = _env_str("SARVAM_TTS_ENABLED", "true").lower() == "true"
# Partial MP3 streaming decode causes hiss/clicks — batch decode is cleaner.
TTS_STREAMING_ENABLED = _env_bool("TTS_STREAMING_ENABLED", False)

# Recall.ai output mode (WebRTC requires media_url from API; file upload is more reliable)
RECALL_USE_OUTPUT_MEDIA = _env_str("RECALL_USE_OUTPUT_MEDIA", "false").lower() == "true"
# Include bot TTS audio in Recall dashboard recording (same $0.50/hr; video not supported)
RECALL_INCLUDE_BOT_AUDIO_IN_RECORDING = _env_bool(
    "RECALL_INCLUDE_BOT_AUDIO_IN_RECORDING", True
)

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
MAX_ANSWER_SEC = _env_int("MAX_ANSWER_SEC", 420)
MAX_OFF_TOPIC_REDIRECTS = _env_int("MAX_OFF_TOPIC_REDIRECTS", 2)
MAX_STRIKES = _env_int("MAX_STRIKES", 3)
MAX_INTERVIEW_MINUTES = _env_int("MAX_INTERVIEW_MINUTES", 30)
# Stage-1 gate: after Q6, continue to Q7–Q10 only if Q1–Q5 avg >= threshold
CONTINUE_AVG_THRESHOLD = _env_float("CONTINUE_AVG_THRESHOLD", 7.0)
STAGE1_QUESTION_COUNT = _env_int("STAGE1_QUESTION_COUNT", 5)
STAGE1_BRIDGE_QUESTION = _env_int("STAGE1_BRIDGE_QUESTION", 6)  # always ask; decide after
ROLLING_WINDOW = _env_int("ROLLING_WINDOW", STAGE1_QUESTION_COUNT)
ABUSE_MAX_WARNINGS = _env_int("ABUSE_MAX_WARNINGS", 1)

# --- Turn-taking (production) ---
# Soft silence (~2s) ends an utterance capture; merge window keeps listening.
# If speech resumes → same answer. If quiet through merge → hard end → next Q.
USER_BARGE_IN_ENABLED = _env_str("USER_BARGE_IN_ENABLED", "false").lower() == "true"
# Soft endpoint silence (VAD). ~2.5s then merge window → hard end ≈ 3.0s.
CORE_ANSWER_SOFT_SILENCE_SEC = _env_float("CORE_ANSWER_SOFT_SILENCE_SEC", 2.0)
# Extra listen-after-soft-end before committing (speech resume → same answer)
CORE_ANSWER_MERGE_WINDOW_SEC = _env_float("CORE_ANSWER_MERGE_WINDOW_SEC", 0.5)
# Alias used by STT long-answer path (same as soft silence)
CORE_LONG_ANSWER_SILENCE_SEC = _env_float(
    "CORE_LONG_ANSWER_SILENCE_SEC", CORE_ANSWER_SOFT_SILENCE_SEC
)
CORE_LONG_ANSWER_SPEECH_SEC = _env_float("CORE_LONG_ANSWER_SPEECH_SEC", 8.0)
CORE_ANSWER_MAX_HOLD_SEC = _env_float("CORE_ANSWER_MAX_HOLD_SEC", 420.0)

# Live Sarvam STT while speaking (avoids end-of-answer full rebatch latency)
STREAM_STT_ENABLED = _env_bool("STREAM_STT_ENABLED", True)
# Short flush/collect after silence — audio already streamed
STREAM_STT_FINALIZE_SEC = _env_float("STREAM_STT_FINALIZE_SEC", 0.8)
# Min live chars to trust streaming path (else fall back to batch)
STREAM_STT_MIN_CHARS = _env_int("STREAM_STT_MIN_CHARS", 8)
INCOMPLETE_MERGE_WINDOW_SEC = _env_float("INCOMPLETE_MERGE_WINDOW_SEC", 3.5)
# Short utterances (repeat/rephrase): faster endpoint so total stays <= ~4s
SHORT_UTTERANCE_MAX_SEC = _env_float("SHORT_UTTERANCE_MAX_SEC", 5.0)
SHORT_UTTERANCE_SILENCE_SEC = _env_float("SHORT_UTTERANCE_SILENCE_SEC", 1.5)

# Mid-answer: ONLY topic polls (no depth clarifiers / interrupt slots)
BOT_INTERRUPT_ENABLED = _env_bool("BOT_INTERRUPT_ENABLED", True)
BOT_INTERRUPT_MIN_PARTIAL_SEC = _env_float("BOT_INTERRUPT_MIN_PARTIAL_SEC", 3.0)
BOT_INTERRUPT_GATE_MIN_CONFIDENCE = _env_float("BOT_INTERRUPT_GATE_MIN_CONFIDENCE", 0.75)
# Disabled legacy interrupt stack (kept for import compatibility; unused in live path)
BOT_INTERRUPT_CLARIFIER_ON_TRACK = _env_bool("BOT_INTERRUPT_CLARIFIER_ON_TRACK", False)
BOT_INTERRUPT_MAX_DEPTH_CLARIFIERS_PER_Q = _env_int(
    "BOT_INTERRUPT_MAX_DEPTH_CLARIFIERS_PER_Q", 0
)
BOT_INTERRUPT_MIN_DEPTH_CLARIFIERS_PER_Q = 0
BOT_INTERRUPT_MAX_CLARIFIERS_PER_Q = _env_int("BOT_INTERRUPT_MAX_CLARIFIERS_PER_Q", 0)
BOT_INTERRUPT_DRAG_REPHRASE_MIN = _env_int("BOT_INTERRUPT_DRAG_REPHRASE_MIN", 0)
BOT_INTERRUPT_DRAG_REPHRASE_MAX = _env_int("BOT_INTERRUPT_DRAG_REPHRASE_MAX", 0)
BOT_INTERRUPT_DRAG_STRIKES_MAX = _env_int("BOT_INTERRUPT_DRAG_STRIKES_MAX", 0)
BOT_INTERRUPT_MAX_DRAG_DEPTH_PER_Q = _env_int("BOT_INTERRUPT_MAX_DRAG_DEPTH_PER_Q", 0)
BOT_INTERRUPT_MIN_SPEECH_SEC = _env_float("BOT_INTERRUPT_MIN_SPEECH_SEC", 30.0)
BOT_INTERRUPT_CHECK_INTERVAL_SEC = _env_float("BOT_INTERRUPT_CHECK_INTERVAL_SEC", 30.0)
BOT_INTERRUPT_SHORT_ANSWER_MAX_SEC = _env_float("BOT_INTERRUPT_SHORT_ANSWER_MAX_SEC", 13.0)
CLARIFIER_MIN_SPEECH_SEC = _env_float("CLARIFIER_MIN_SPEECH_SEC", 999.0)
CLARIFIER_ON_TRACK_MIN_SPEECH_SEC = _env_float("CLARIFIER_ON_TRACK_MIN_SPEECH_SEC", 999.0)
CLARIFIER_MIN_INTERVAL_SEC = _env_float("CLARIFIER_MIN_INTERVAL_SEC", 999.0)
CLARIFIER_REPLY_SCORE_MIN_CHARS = _env_int("CLARIFIER_REPLY_SCORE_MIN_CHARS", 120)
CLARIFIER_REPLY_SILENCE_SEC = _env_float("CLARIFIER_REPLY_SILENCE_SEC", 1.5)
DRAG_REPHRASE_SCORE_GRACE_SEC = _env_float("DRAG_REPHRASE_SCORE_GRACE_SEC", 0.0)
DRAG_SKIP_SCORE = _env_int("DRAG_SKIP_SCORE", 2)
DRAG_CONTEXT_MIN_OVERLAP = _env_int("DRAG_CONTEXT_MIN_OVERLAP", 1)
MAIN_QUESTION_INTERRUPT_COOLDOWN_SEC = _env_float(
    "MAIN_QUESTION_INTERRUPT_COOLDOWN_SEC", 5.0
)
MID_ANSWER_BOT_COOLDOWN_SEC = _env_float("MID_ANSWER_BOT_COOLDOWN_SEC", 8.0)

# Topic poll every N seconds of speech (clock starts when candidate starts talking)
ANSWER_TOPIC_POLL_INTERVAL_SEC = _env_float("ANSWER_TOPIC_POLL_INTERVAL_SEC", 30.0)
ANSWER_TOPIC_POLL_WINDOW_SEC = _env_float("ANSWER_TOPIC_POLL_WINDOW_SEC", 30.0)
MAX_TOPIC_REDIRECTS_PER_QUESTION = _env_int("MAX_TOPIC_REDIRECTS_PER_QUESTION", 2)
# Legacy slot interrupts — disabled (0 / unreachable)
ANSWER_FIRST_CHECK_SEC = _env_float("ANSWER_FIRST_CHECK_SEC", 9999.0)
ANSWER_INTERRUPT_2_AFTER_SEC = _env_float("ANSWER_INTERRUPT_2_AFTER_SEC", 9999.0)
ANSWER_SECOND_CHECK_SEC = _env_float("ANSWER_SECOND_CHECK_SEC", 9999.0)
ANSWER_MAX_INTERRUPTS = _env_int("ANSWER_MAX_INTERRUPTS", 0)
ANSWER_INTERRUPT_SLOT_TOLERANCE_SEC = _env_float("ANSWER_INTERRUPT_SLOT_TOLERANCE_SEC", 3.0)
ANSWER_DEPTH_CHECK_WINDOW_SEC = _env_float("ANSWER_DEPTH_CHECK_WINDOW_SEC", 30.0)
ANSWER_DRAG_GRACE_SEC = _env_float("ANSWER_DRAG_GRACE_SEC", 0.0)
PROGRESS_GATE_LONG_ANSWER_SEC = _env_float("PROGRESS_GATE_LONG_ANSWER_SEC", 45.0)
PROGRESS_GATE_MIN_TOPIC_OVERLAP = _env_int("PROGRESS_GATE_MIN_TOPIC_OVERLAP", 1)
PROGRESS_GATE_UNCLEAR_ESCALATION_CHECKS = _env_int(
    "PROGRESS_GATE_UNCLEAR_ESCALATION_CHECKS", 2
)
# Rule DRAG only when overlap is zero for this long (avoids false positives)
PROGRESS_GATE_RULE_DRAG_MIN_SEC = _env_float("PROGRESS_GATE_RULE_DRAG_MIN_SEC", 45.0)
PROGRESS_GATE_RULE_DRAG_MIN_WORDS = _env_int("PROGRESS_GATE_RULE_DRAG_MIN_WORDS", 40)

# Allow Whisper fallback when Sarvam fails in Hinglish (final answers only)
HINGLISH_WHISPER_FALLBACK = _env_bool("HINGLISH_WHISPER_FALLBACK", True)

# Meta-requests during Q&A (repeat / rephrase question — not scored)
MAX_QUESTION_REPEATS = _env_int("MAX_QUESTION_REPEATS", 2)
MAX_QUESTION_REPHRASES = _env_int("MAX_QUESTION_REPHRASES", 1)

# Interview quality: name normalization and incomplete-answer guard
NAME_NORMALIZE_ENABLED = _env_bool("NAME_NORMALIZE_ENABLED", True)
MIN_ANSWER_WORDS = _env_int("MIN_ANSWER_WORDS", 8)
MIN_SHORT_COMPLETE_WORDS = _env_int("MIN_SHORT_COMPLETE_WORDS", 5)
MAX_ANSWER_CONTINUATIONS = _env_int("MAX_ANSWER_CONTINUATIONS", 2)
INCOMPLETE_ANSWER_CHECK_ENABLED = _env_bool("INCOMPLETE_ANSWER_CHECK_ENABLED", True)

# After wrap-up TTS finishes, auto-leave the meeting (seconds)
INTERVIEW_AUTO_LEAVE_AFTER_WRAPUP_SEC = _env_float(
    "INTERVIEW_AUTO_LEAVE_AFTER_WRAPUP_SEC", 2.5
)

# Presence: only before answer starts; never mid-answer
POST_TTS_SILENCE_CHECK_ENABLED = _env_bool("POST_TTS_SILENCE_CHECK_ENABLED", True)
POST_TTS_SILENCE_CHECK_SEC = _env_float("POST_TTS_SILENCE_CHECK_SEC", 22.0)
POST_TTS_SILENCE_MIN_AFTER_QUESTION_SEC = _env_float(
    "POST_TTS_SILENCE_MIN_AFTER_QUESTION_SEC", 22.0
)
MAX_PRESENCE_CHECKS_PER_QUESTION = _env_int("MAX_PRESENCE_CHECKS_PER_QUESTION", 1)
POST_QUESTION_SILENCE_STEP1_SEC = _env_float("POST_QUESTION_SILENCE_STEP1_SEC", 22.0)
POST_QUESTION_SILENCE_STEP2_SEC = _env_float("POST_QUESTION_SILENCE_STEP2_SEC", 12.0)
POST_QUESTION_FINAL_WRAP_SEC = _env_float("POST_QUESTION_FINAL_WRAP_SEC", 15.0)
PRESENCE_ONLY_AFTER_QUESTION = _env_bool("PRESENCE_ONLY_AFTER_QUESTION", True)
PRESENCE_SKIP_DURING_ANSWER = _env_bool("PRESENCE_SKIP_DURING_ANSWER", True)

# STT: do not flush/score tiny held turns while a long answer is in progress
TURN_FLUSH_GUARD_MIN_CHARS = _env_int("TURN_FLUSH_GUARD_MIN_CHARS", 30)
TURN_FLUSH_DEFER_SEC = _env_float("TURN_FLUSH_DEFER_SEC", 8.0)

# Reject tail fragments from the previous question shortly after advancing
STALE_ANSWER_GUARD_SEC = _env_float("STALE_ANSWER_GUARD_SEC", 12.0)
STALE_ANSWER_MAX_CHARS = _env_int("STALE_ANSWER_MAX_CHARS", 220)

# Latency: speak next question immediately; score in background
ANSWER_ACK_BEFORE_EVAL = _env_bool("ANSWER_ACK_BEFORE_EVAL", False)
PARALLEL_SCORE_ENABLED = _env_bool("PARALLEL_SCORE_ENABLED", True)
STAGE1_GATE_WAIT_SEC = _env_float("STAGE1_GATE_WAIT_SEC", 8.0)

# Intro phase: do not advance to Q1 on a short greeting-only pause
INTRO_MIN_CHARS = _env_int("INTRO_MIN_CHARS", 80)
INTRO_MIN_SPEECH_SEC = _env_float("INTRO_MIN_SPEECH_SEC", 20.0)
INTRO_MERGE_WINDOW_SEC = _env_float("INTRO_MERGE_WINDOW_SEC", 10.0)

# Latency: preload Whisper at session start (avoids ~2s first-fallback delay)
WHISPER_PRELOAD_ENABLED = _env_bool("WHISPER_PRELOAD_ENABLED", True)

# Turn intent classifier (repeat/rephrase vs actual answer — LLM-based)
TURN_INTENT_CLASSIFIER_ENABLED = _env_bool("TURN_INTENT_CLASSIFIER_ENABLED", True)
TURN_INTENT_MAX_CHARS = _env_int("TURN_INTENT_MAX_CHARS", 150)
TURN_INTENT_MIN_CONFIDENCE = _env_float("TURN_INTENT_MIN_CONFIDENCE", 0.65)

# Answer time budget (1 min initial → +30s extensions → hard cap)
ANSWER_INITIAL_LISTEN_SEC = _env_float("ANSWER_INITIAL_LISTEN_SEC", 60.0)
ANSWER_EXTEND_STEP_SEC = _env_float("ANSWER_EXTEND_STEP_SEC", 30.0)
ANSWER_MAX_TOTAL_SEC = _env_float("ANSWER_MAX_TOTAL_SEC", float(MAX_ANSWER_SEC))

# Sentinel queued when presence ladder exhausts without candidate speech
PRESENCE_TIMEOUT_TOKEN = "__PRESENCE_TIMEOUT__"

# Main asyncio event loop — set once by api_server.py's startup hook.
# Stored here (not in api_server.py) so all modules share the same reference
# regardless of whether api_server is run as __main__ or imported as a module.
main_event_loop = None

# --- PostgreSQL + JWT auth (Phase 0) ---
DATABASE_URL = _env_str("DATABASE_URL", "")
APP_ENV = _env_str("APP_ENV", "development").lower()  # development | production
JWT_SECRET = _env_str("JWT_SECRET", "dev-change-me-speechagent-jwt-secret")
JWT_ALGORITHM = _env_str("JWT_ALGORITHM", "HS256")
# Shorter sessions in production by default
JWT_EXPIRE_MINUTES = _env_int(
    "JWT_EXPIRE_MINUTES",
    60 * 8 if APP_ENV == "production" else 60 * 24 * 7,
)
JWT_ISSUER = _env_str("JWT_ISSUER", "speechagent")
JWT_AUDIENCE = _env_str("JWT_AUDIENCE", "speechagent-api")

# Master key for encrypting per-org ATS API keys in organization.ats_api_key_encrypted.
# Prefer a Fernet key (python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
# or any long passphrase (SHA-256 derived). Falls back to JWT_SECRET in development only.
ATS_SECRET_ENCRYPTION_KEY = _env_str("ATS_SECRET_ENCRYPTION_KEY", "")

# --- Document uploads (CV/JD files on disk + documents table) ---
# Relative paths resolve under backend/; absolute paths used as-is.
DOCUMENT_UPLOAD_DIR = _env_str("DOCUMENT_UPLOAD_DIR", "uploads")
DOCUMENT_MAX_BYTES = _env_int("DOCUMENT_MAX_BYTES", 15 * 1024 * 1024)  # 15 MB

# --- Camera integrity (interview + local test) ---
# false = current interview flow (no Recall face tracking / camera presence phrases)
CAMERA_INTEGRITY_ENABLED = _env_bool("CAMERA_INTEGRITY_ENABLED", False)
# production = eye-first labels; interview = soft screen look (default live); strict = QA
CAMERA_GAZE_MODE = _env_str("CAMERA_GAZE_MODE", "interview")
CAMERA_GAZE_DEBUG = _env_bool("CAMERA_GAZE_DEBUG", True)
CAMERA_WARN_TTS_ENABLED = _env_bool("CAMERA_WARN_TTS_ENABLED", True)
CAMERA_WARN_AFTER_SEC = _env_float("CAMERA_WARN_AFTER_SEC", 5.0)
# Live interview: two faces must persist this long before TTS warn
CAMERA_WARN_AFTER_MULTI_FACE_SEC = _env_float("CAMERA_WARN_AFTER_MULTI_FACE_SEC", 5.0)
# Off-screen (away / down) hold before warn — longer than thinking glances
CAMERA_WARN_AFTER_AWAY_SEC = _env_float("CAMERA_WARN_AFTER_AWAY_SEC", 12.0)
CAMERA_WARN_COOLDOWN_SEC = _env_float("CAMERA_WARN_COOLDOWN_SEC", 15.0)
# Live path analyzes ~2 fps — fewer consecutive hits than local 30fps test
CAMERA_WARN_HOLD_FRAMES_LIVE = _env_int("CAMERA_WARN_HOLD_FRAMES_LIVE", 2)
# Brief drop in multi-face / no_face before clearing the risk timer
CAMERA_WARN_RISK_GRACE_SEC = _env_float("CAMERA_WARN_RISK_GRACE_SEC", 2.0)
# false = ignore left/right iris for TTS (thinking glances); looking_up never warns
CAMERA_WARN_INCLUDE_SIDE_LOOK = _env_bool("CAMERA_WARN_INCLUDE_SIDE_LOOK", False)
# looking_down = hard head nod (desk/phone); mild screen look stays center
CAMERA_WARN_ON_LOOKING_DOWN = _env_bool("CAMERA_WARN_ON_LOOKING_DOWN", True)
CAMERA_WARN_ON_NO_FACE = _env_bool("CAMERA_WARN_ON_NO_FACE", True)
CAMERA_WARN_ON_MULTI_FACE = _env_bool("CAMERA_WARN_ON_MULTI_FACE", True)
CAMERA_WARN_ON_LOOKING_AWAY = _env_bool("CAMERA_WARN_ON_LOOKING_AWAY", True)
# true = skip away/down warn while lips move (answering / thinking aloud)
CAMERA_WARN_IGNORE_AWAY_WHILE_SPEAKING = _env_bool(
    "CAMERA_WARN_IGNORE_AWAY_WHILE_SPEAKING", True
)
# Extra face must be this fraction of primary area to count as multi_face
CAMERA_WARN_MULTI_FACE_MIN_AREA_RATIO = _env_float(
    "CAMERA_WARN_MULTI_FACE_MIN_AREA_RATIO", 0.10
)
# Consecutive risk frames before the warn timer starts (~8 @ 30fps ≈ 0.25s)
CAMERA_WARN_HOLD_FRAMES = _env_int("CAMERA_WARN_HOLD_FRAMES", 8)
# Proactive lips+silence unmute warn (off by default — use silence presence ladder instead)
CAMERA_WARN_ON_MUTED_MIC = _env_bool("CAMERA_WARN_ON_MUTED_MIC", False)
CAMERA_WARN_MUTED_MIC_AFTER_SEC = _env_float("CAMERA_WARN_MUTED_MIC_AFTER_SEC", 4.0)
# Audio older than this counts as silence for mute detection
CAMERA_WARN_MUTED_MIC_SILENCE_SEC = _env_float("CAMERA_WARN_MUTED_MIC_SILENCE_SEC", 2.0)
