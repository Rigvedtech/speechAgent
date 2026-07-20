"""
Structured interview orchestration: question selection, per-answer scoring,
rolling-average gate, abuse handling, and report-card generation.

Uses deque-based rolling window and bucketed question queues (DSA-style).
"""

from __future__ import annotations

import json
import logging
import re
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Deque, Dict, List, Optional, Tuple

import config
from language_profiles import LanguageMode, get_ui_strings

logger = logging.getLogger(__name__)

# Fixed difficulty mix: Low → Hard → Intermediate (repeating).
DIFFICULTY_PATTERN: Tuple[str, ...] = (
    "Low",
    "Hard",
    "Intermediate",
    "Low",
    "Hard",
    "Intermediate",
    "Low",
    "Hard",
    "Intermediate",
    "Low",
    "Hard",
    "Intermediate",
    "Low",
    "Hard",
    "Intermediate",
)

_DIFFICULTY_ALIASES: Dict[str, str] = {
    "low": "Low",
    "easy": "Low",
    "beginner": "Low",
    "intermediate": "Intermediate",
    "medium": "Intermediate",
    "mid": "Intermediate",
    "hard": "Hard",
    "difficult": "Hard",
    "advanced": "Hard",
}

_ABUSE_PATTERNS = re.compile(
    r"|".join([
        r"\b(f+u+c+k+|sh+i+t+|b+i+t+c+h+|asshole|bastard|damn\s+you)\b",
        r"\b(idiot|stupid|dumbass|moron)\b",
        r"\b(shut\s+up|go\s+to\s+hell)\b",
    ]),
    re.IGNORECASE,
)

GROUNDING_RULES = (
    "Grounding rules for this interview:\n"
    "- Base job-fit questions only on the JOB DESCRIPTION (JD).\n"
    "- Base experience and project questions only on facts in the CANDIDATE RESUME.\n"
    "- Do not invent employers, titles, dates, technologies, or projects.\n"
    "- Voice/STT tolerance: treat near-sounding names as ASR noise."
)


class InterviewPhase(str, Enum):
    GREETING = "greeting"
    AWAIT_INTRO = "await_intro"
    CORE = "core"
    CLOSING = "closing"
    ENDED = "ended"


class StoppedReason(str, Enum):
    NONE = "none"
    COMPLETED = "completed_all_questions"
    LOW_ROLLING_AVERAGE = "low_recent_average"
    ABUSE = "abuse"
    MANUAL = "manual"


class TurnAction(str, Enum):
    SPEAK = "speak"
    REASK_SAME = "reask_same"
    REPHRASE = "rephrase"
    WARN_ABUSE = "warn_abuse"
    STOP = "stop"


class TurnIntent(str, Enum):
    """Classifier output for candidate short utterances during Q&A."""
    ACTUAL_ANSWER = "actual_answer"
    REPEAT_LAST = "repeat_last"
    REPHRASE_LAST = "rephrase_last"
    REPEAT_MAIN = "repeat_main"
    CONTINUE_ANSWER = "continue_answer"


_BRIDGE_PHRASES: Tuple[str, ...] = (
    "Alright.",
    "Got it.",
    "Okay.",
    "Sure.",
    "Understood.",
    "Right.",
)

_REPEAT_INTENT = re.compile(
    r"|".join([
        r"\b(repeat|say\s+again|come\s+again|pardon)\b",
        r"\bcan\s+you\s+repeat\b",
        r"\brepeat\s+(the|that)\s+question\b",
        r"\bwhat\s+was\s+the\s+question\b",
        r"\bsay\s+the\s+question\s+again\b",
        r"\b(dobara|phir\s+se)\b",
        r"\bquestion\s+repeat\b",
        r"\bsawal\s+(dobara|repeat)\b",
        r"\bkya\s+aap\b.*\brepeat\b",
        r"\bdobara\s+bata\b",
        r"\bdobara\s+bol\b",
    ]),
    re.IGNORECASE,
)

_EXPLICIT_QUESTION_REPEAT = re.compile(
    r"|".join([
        r"\brepeat\s+(the|that)\s+question\b",
        r"\bwhat\s+was\s+the\s+question\b",
        r"\bsay\s+the\s+question\s+again\b",
        r"\bcan\s+you\s+repeat\s+(the|that)\s+question\b",
        r"\b(didn'?t|don'?t)\s+(get|catch)\s+(it|that)\b",
        r"\bmissed\s+(the\s+)?question\b",
    ]),
    re.IGNORECASE,
)

_REPHRASE_INTENT = re.compile(
    r"|".join([
        r"\b(didn'?t|don'?t)\s+understand\b",
        r"\bnot\s+understand(ing)?\b",
        r"\bcan\s+you\s+explain\s+the\s+question\b",
        r"\bexplain\s+the\s+question\b",
        r"\bsimpler\s+(version|way|words)\b",
        r"\brephrase\s+the\s+question\b",
        r"\bwhat\s+do\s+you\s+mean\b",
        r"\bcan\s+you\s+clarify\s+the\s+question\b",
        r"\bsamajh\s+nahi\b",
        r"\bsimple\s+(tareeke|words)\s+se\b",
        r"\bdobara\s+samjha\b",
    ]),
    re.IGNORECASE,
)

_INCOMPLETE_TRAILING = re.compile(
    r"\b(and|so|because|but|like|um|uh|or|if|when|that|then|also|with|for|"
    r"to|the|a|an|of|in|on|at|by|from|into|about|factors?|objective|identify|"
    r"could|would|should|will|can|my|our|their|this|these|those)$",
    re.IGNORECASE,
)

# Short but complete answers — must not trigger "Please continue your answer."
_SHORT_COMPLETE_ANSWER = re.compile(
    r"|".join([
        r"\bno\b.*\bnot\b",
        r"\bit'?s\s+not\b",
        r"\bnot\s+(difficult|hard|easy|simple|complex)\b",
        r"\b(yes|yeah|yep|yup|correct|right|sure|absolutely)\b",
        r"\bi\s+(can|do|have|would|will)\b",
        r"\bthat'?s\s+(correct|right|fine|okay|ok)\b",
        r"\bthat'?s\s+(it|all)\b",
        r"^\s*bas\s*[\.\!\?]*$",
        r"^\s*ठीक\s+है\s*[\.\!\?]*$",
    ]),
    re.IGNORECASE,
)

# Standalone or trailing answer-completion cues (STT + LLM scoring path)
_ANSWER_DONE_PHRASE = re.compile(
    r"(?:that'?s\s+(?:it|all)|^\s*done\s*[\.\!\?]*$|^\s*bas\s*[\.\!\?]*$|"
    r"^\s*ठीक\s+है\s*[\.\!\?]*$|that'?s\s+it\s*[\.\!\?]*\s*$)",
    re.IGNORECASE,
)

_CONTINUATION_CHECKIN = re.compile(
    r"|".join([
        r"^(hello|hi|hey)[\.!\?]?$",
        r"^(okay|ok|sure)[\.!\?]?$",
        r"\bcan\s+you\s+hear\s+me\b",
        r"\bare\s+you\s+there\b",
        r"\bexcuse\s+me\b",
        r"^(sorry|thank\s*(you|u)|thanks)[\.!\?]?$",
    ]),
    re.IGNORECASE,
)

# After "please continue" — candidate asks permission / confirms scope (not an answer).
_CONTINUATION_PERMISSION = re.compile(
    r"|".join([
        r"\bshould\s+i\b",
        r"\bshall\s+i\b",
        r"\bdo\s+you\s+want\s+me\s+to\b",
        r"\bwould\s+you\s+like\s+me\s+to\b",
        r"\bcan\s+i\s+(just\s+)?(explain|continue|tell|describe|share|walk)\b",
        r"\bmay\s+i\s+(just\s+)?(explain|continue|tell|describe)\b",
        r"\byou\s+want\s+me\s+to\b",
        r"\bkya\s+(main|mein)\s+(batau|explain|continue)\b",
        r"\bmujhe\s+(explain|bataana)\s+chahiye\b",
    ]),
    re.IGNORECASE,
)

_CLARIFIER_CONFUSION = re.compile(
    r"|".join([
        r"\bsorry\b",
        r"\b(didn'?t|don'?t)\s+(understand|get)\b",
        r"\bnot\s+understand(ing)?\b",
        r"\bwhat\s+(did\s+you\s+say|was\s+that)\b",
        r"\bcan\s+you\s+repeat\s+(that|it)\b",
        r"\bsay\s+that\s+again\b",
        r"\bpardon\b",
        r"\bcome\s+again\b",
    ]),
    re.IGNORECASE,
)

_INABILITY_PATTERNS = re.compile(
    r"|".join([
        r"\b(don'?t|do\s+not)\s+(know|remember)\b",
        r"\bno\s+idea\b",
        r"\bnot\s+sure\b",
        r"\bcan'?t\s+(remember|recall)\b",
        r"\b(don'?t|do\s+not)\s+have\s+(an?\s+)?answer\b",
        r"\bno\s+answer\b",
        r"\bnot\s+able\s+to\s+answer\b",
        r"\bhaven'?t\s+(used|worked|done)\b",
        r"\b(have|has)\s+not\s+(yet\s+)?(used|worked|done)\b",
        r"\b(did\s+not|didn'?t)\s+(work|use|get\s+to\s+work)\b",
        r"\bno\s+(hands[-\s]?on\s+)?experience\b",
        r"\b(don'?t|do\s+not)\s+have\s+(any\s+)?(experience|exposure)\b",
        r"\bnot\s+(yet\s+)?worked\s+on\b",
        r"\bnever\s+worked\s+(on|with)\b",
        r"\bsorry[,\s]+i\s+(don'?t|do\s+not|haven'?t|have\s+not)\b",
        r"\bnahi\s+pata\b",
        r"\bpata\s+nahi\b",
        r"\b(nahi|na)\s+yaad\b",
        r"\bmalum\s+nahi\b",
        r"\bjawab\s+nahi\b",
        r"\bexperience\s+nahi\b",
        r"\bkaam\s+nahi\s+kiya\b",
    ]),
    re.IGNORECASE,
)

_EXPLICIT_MAIN_QUESTION = re.compile(
    r"|".join([
        r"\b(main|original|full)\s+question\b",
        r"\binterview\s+question\b",
        r"\bwhat\s+was\s+the\s+(main\s+)?question\b",
        r"\bgo\s+back\s+to\s+the\s+question\b",
    ]),
    re.IGNORECASE,
)


@dataclass(frozen=True)
class BankQuestion:
    id: str
    difficulty: str
    source: str
    question: str

    @property
    def normalized_difficulty(self) -> str:
        return normalize_difficulty(self.difficulty)


@dataclass
class AnswerRecord:
    question_index: int
    question_id: str
    difficulty: str
    source: str
    question_text: str
    answer_text: str
    score: int
    confident: bool
    relevant: bool
    strengths: str = ""
    develop: str = ""
    fix: str = ""
    abuse_flag: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class EvaluationResult:
    score: int = 5
    confident: bool = False
    relevant: bool = True
    strengths: str = ""
    develop: str = ""
    fix: str = ""

    @classmethod
    def from_dict(cls, data: dict) -> "EvaluationResult":
        score = int(data.get("score", 5))
        score = max(0, min(10, score))
        return cls(
            score=score,
            confident=bool(data.get("confident", False)),
            relevant=bool(data.get("relevant", True)),
            strengths=str(data.get("strengths", "") or "").strip(),
            develop=str(data.get("develop", "") or "").strip(),
            fix=str(data.get("fix", "") or "").strip(),
        )


@dataclass
class TurnDecision:
    action: TurnAction
    spoken_text: str
    score_record: Optional[AnswerRecord] = None
    rolling_average: Optional[float] = None
    should_continue: bool = True
    stopped_reason: StoppedReason = StoppedReason.NONE
    # main | clarifier | prompt — used to track last spoken question for repeat
    spoken_kind: Optional[str] = None
    # Hinglish: short bridge only (good score); False = full rephrase intro
    use_simple_bridge: bool = False
    # True when orchestrator routed through REPHRASE (Hinglish TTS line split)
    rephrase_flow: bool = False
    # After depth clarifier: score merged answer instead of "continue kijiye"
    score_clarifier_merged: bool = False
    # Low-latency: next Q spoken; score previous answer in background
    pending_background_score: bool = False
    # Last planned Q answered — close after background score
    defer_close: bool = False


@dataclass
class ProgressCheckSchedule:
    """Resolved mid-answer check — scheduled slot beats background poll."""
    kind: str  # "slot" | "poll"
    slot: int = 0
    poll_index: int = 0


@dataclass
class ProgressCheckPayload:
    """Mid-answer progress gate input — queued from STT to LLM worker."""
    full_partial: str
    recent_segment: str
    speech_sec: float
    check_num: int
    check_kind: str = "slot"  # "slot" | "poll"
    check_slot: int = 0
    poll_index: int = 0
    window_text: str = ""
    force_time_cap: bool = False


_TOPIC_STOPWORDS = frozenset({
    "what", "when", "where", "which", "with", "from", "that", "this", "have",
    "your", "about", "would", "could", "should", "their", "there", "been",
    "were", "will", "does", "using", "used", "explain", "describe", "tell",
})


def _question_topic_tokens(question_text: str) -> set:
    words = re.findall(r"\b\w{4,}\b", (question_text or "").lower())
    return {w for w in words if w not in _TOPIC_STOPWORDS}


def normalize_difficulty(raw: str) -> str:
    key = (raw or "").strip().lower()
    return _DIFFICULTY_ALIASES.get(key, raw.strip().title() if raw else "Low")


def _source_bucket(source: str) -> str:
    s = (source or "").strip().lower()
    if "resume" in s or "cv" in s:
        return "resume"
    if "jd" in s or "job" in s:
        return "jd"
    return "other"


def _normalize_question_text(text: str) -> str:
    """Normalize question text for duplicate detection in the question plan."""
    t = (text or "").strip().lower()
    t = re.sub(r"[^\w\s]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def detect_explicit_question_repeat(text: str) -> bool:
    """True when the candidate wants the current interview question repeated."""
    t = (text or "").strip()
    if not t or len(t) > 120:
        return False
    if detect_inability_answer(t):
        return False
    return bool(_EXPLICIT_QUESTION_REPEAT.search(t))


_SHORT_IMMEDIATE_TURN = re.compile(
    r"|".join([
        r"\bsorry\b",
        r"\bthank\s*(you|u)\b",
        r"\bthanks\b",
        r"\bcan\s+you\s+hear\s+me\b",
        r"\bare\s+you\s+there\b",
        r"\bexcuse\s+me\b",
        r"\bhello\b",
        r"\bhi\b",
    ]),
    re.IGNORECASE,
)


def should_commit_short_turn_immediately(text: str) -> bool:
    """
    Short complete utterances that must reach the LLM without TURN MERGE hold.
    Covers meta-requests, inability, and social/check-in phrases.
    """
    t = (text or "").strip()
    if not t or len(t) > 120:
        return False
    if detect_inability_answer(t):
        return True
    if detect_explicit_question_repeat(t):
        return True
    if detect_meta_intent(t):
        return True
    if _SHORT_IMMEDIATE_TURN.search(t):
        return True
    return False


def detect_abuse(text: str) -> bool:
    return bool(_ABUSE_PATTERNS.search(text or ""))


def detect_meta_intent(text: str) -> Optional[str]:
    """
    Detect candidate meta-requests (not answers).
    Returns 'rephrase', 'repeat', or None.
    """
    t = (text or "").strip()
    if not t:
        return None
    # Meta intents are usually short; long answers are treated as normal turns.
    if len(t) > 120:
        return None
    if detect_inability_answer(t):
        return None
    if _REPHRASE_INTENT.search(t):
        return "rephrase"
    if _REPEAT_INTENT.search(t):
        return "repeat"
    return None


def detect_clarifier_confusion(text: str) -> bool:
    """Candidate did not understand the mid-answer clarifier (not a real answer)."""
    t = (text or "").strip()
    if not t or len(t) > 120:
        return False
    if detect_meta_intent(t):
        return True
    return bool(_CLARIFIER_CONFUSION.search(t))


def detect_turn_intent_fallback(text: str, awaiting_clarifier: bool) -> str:
    """
    Regex fallback when LLM classifier is unavailable.
    Returns a TurnIntent value string.
    """
    t = (text or "").strip()
    if not t:
        return TurnIntent.ACTUAL_ANSWER.value
    if len(t) > config.TURN_INTENT_MAX_CHARS:
        return TurnIntent.ACTUAL_ANSWER.value
    if detect_inability_answer(t):
        return TurnIntent.ACTUAL_ANSWER.value
    if detect_explicit_question_repeat(t) or _EXPLICIT_MAIN_QUESTION.search(t):
        return TurnIntent.REPEAT_MAIN.value
    meta = detect_meta_intent(t)
    if meta == "rephrase":
        return TurnIntent.REPHRASE_LAST.value
    if meta == "repeat":
        return TurnIntent.REPEAT_LAST.value
    if awaiting_clarifier and detect_clarifier_confusion(t):
        return TurnIntent.REPHRASE_LAST.value
    return TurnIntent.ACTUAL_ANSWER.value


def detect_answer_done_phrase(text: str) -> bool:
    """True when the utterance signals the candidate is done (possibly alone)."""
    t = (text or "").strip()
    if not t:
        return False
    if len(t) <= 40 and re.match(
        r"^(?:that'?s\s+(?:it|all)|done|bas|ठीक\s+है)\s*[\.\!\?]*$",
        t,
        re.IGNORECASE,
    ):
        return True
    return bool(_ANSWER_DONE_PHRASE.search(t))


def detect_short_complete_answer(text: str) -> bool:
    """True when a short utterance is a complete thought, not a cut-off fragment."""
    t = (text or "").strip()
    if not t:
        return False
    if _SHORT_COMPLETE_ANSWER.search(t):
        return True
    words = [w for w in re.split(r"\s+", t) if w]
    if len(words) >= config.MIN_SHORT_COMPLETE_WORDS and re.search(
        r'[.!?]["\']?\s*$', t
    ):
        return True
    return False


def detect_continuation_checkin(text: str) -> bool:
    """Social / check-in phrase after we asked the candidate to continue."""
    t = (text or "").strip()
    if not t or len(t) > 80:
        return False
    if _CONTINUATION_CHECKIN.search(t):
        return True
    if _SHORT_IMMEDIATE_TURN.search(t) and len(t.split()) <= 4:
        return True
    return False


def detect_continuation_permission(text: str) -> bool:
    """
    Candidate asking permission / confirming scope after 'please continue'
    (e.g. 'Should I just explain…?') — not a scored answer.
    """
    t = (text or "").strip()
    if not t or len(t) > 160:
        return False
    if detect_inability_answer(t):
        return False
    return bool(_CONTINUATION_PERMISSION.search(t))


def detect_inability_answer(text: str) -> bool:
    """Short honest 'I don't know / haven't worked on it' — complete thought."""
    t = (text or "").strip()
    if not t or len(t) > 120:
        return False
    return bool(_INABILITY_PATTERNS.search(t))


_PRESENCE_CONFIRM = re.compile(
    r"|".join([
        r"\b(yes|yeah|yep|yup|sure|okay|ok|correct|right|audible)\b",
        r"\b(i\s+can\s+hear|can\s+hear\s+you|hear\s+you\s+(fine|clearly|okay))\b",
        r"\b(loud\s+and\s+clear|all\s+good)\b",
        r"\b(haan|ha|ji)\b",
        r"\bsun\s*(pa\s+raha|sakta|sakti|rahi|rahe)\b",
        r"\bsunai\s+de\s+raha\b",
        r"\btheek\s+hai\b",
    ]),
    re.IGNORECASE,
)


def detect_bot_alive_check(text: str) -> bool:
    """Candidate asking if the bot can hear them / is still there."""
    t = (text or "").strip()
    if not t or len(t) > 80:
        return False
    return bool(
        re.search(
            r"|".join([
                r"\b(are\s+you\s+there|can\s+you\s+hear\s+me|hello\s+\w+)\b",
                r"\b(kya\s+aap\s+(sun|wahan)|sun\s+rahe\s+ho)\b",
            ]),
            t,
            re.IGNORECASE,
        )
    )


def detect_presence_confirm(text: str) -> bool:
    """Candidate confirms they can hear the bot after a presence check."""
    t = (text or "").strip()
    if not t or len(t) > 80:
        return False
    if detect_continuation_checkin(t):
        return True
    if detect_bot_alive_check(t):
        return True
    return bool(_PRESENCE_CONFIRM.search(t))


def detect_incomplete_answer(text: str) -> bool:
    """True when a CORE-phase answer looks cut off or too short to score."""
    if not config.INCOMPLETE_ANSWER_CHECK_ENABLED:
        return False
    t = (text or "").strip()
    if not t:
        return True
    if detect_inability_answer(t):
        return False
    if detect_answer_done_phrase(t):
        return False
    if detect_short_complete_answer(t):
        return False
    words = [w for w in re.split(r"\s+", t) if w]
    if len(words) < config.MIN_ANSWER_WORDS:
        return True
    trimmed = t.rstrip(".,!?…")
    if _INCOMPLETE_TRAILING.search(trimmed):
        return True
    # Repeated last word ("Factors. Factors") — mid-thought stutter / cut
    if len(words) >= 2:
        a = re.sub(r"[^a-z0-9]", "", words[-1].lower())
        b = re.sub(r"[^a-z0-9]", "", words[-2].lower())
        if a and a == b and len(a) >= 3:
            return True
    # No sentence-ending punctuation and still relatively short → likely mid-answer
    if not re.search(r"[.!?…]\s*$", t) and len(words) < max(int(config.MIN_ANSWER_WORDS) * 4, 24):
        return True
    return False


class RollingScoreTracker:
    """Fixed-size deque — O(1) push, O(k) average where k = window size."""

    def __init__(self, window: int):
        self._window = max(1, window)
        self._scores: Deque[int] = deque(maxlen=self._window)

    def push(self, score: int) -> None:
        self._scores.append(max(0, min(10, score)))

    def average(self) -> Optional[float]:
        if not self._scores:
            return None
        return sum(self._scores) / len(self._scores)

    def is_full(self) -> bool:
        return len(self._scores) >= self._window

    def can_continue(self, threshold: float) -> bool:
        if not self.is_full():
            return True
        avg = self.average()
        return avg is not None and avg >= threshold

    def snapshot(self) -> List[int]:
        return list(self._scores)


class QuestionSelector:
    """
    Picks N questions using a fixed difficulty pattern.
    Within each difficulty, alternates JD vs resume via round-robin deques.
    """

    @staticmethod
    def select(bank: List[BankQuestion], max_questions: int) -> List[BankQuestion]:
        pattern = DIFFICULTY_PATTERN[:max_questions]
        buckets: Dict[str, Dict[str, Deque[BankQuestion]]] = defaultdict(
            lambda: {"jd": deque(), "resume": deque(), "other": deque()}
        )

        for q in sorted(bank, key=lambda x: (x.normalized_difficulty, x.id)):
            diff = q.normalized_difficulty
            src = _source_bucket(q.source)
            buckets[diff][src].append(q)

        selected: List[BankQuestion] = []
        source_toggle = 0
        used_question_texts: set = set()

        for slot_diff in pattern:
            if slot_diff not in buckets:
                raise ValueError(
                    f"Question bank missing difficulty '{slot_diff}'."
                )
            picked = QuestionSelector._pop_from_bucket(
                buckets[slot_diff], source_toggle, used_question_texts
            )
            if picked is None:
                raise ValueError(
                    f"Not enough unique '{slot_diff}' questions to fill "
                    f"{max_questions} planned slots."
                )
            selected.append(picked)
            used_question_texts.add(_normalize_question_text(picked.question))
            source_toggle ^= 1

        return selected

    @staticmethod
    def _pop_from_bucket(
        bucket: Dict[str, Deque[BankQuestion]],
        source_toggle: int,
        used_question_texts: set,
    ) -> Optional[BankQuestion]:
        order = ("jd", "resume", "other") if source_toggle % 2 == 0 else (
            "resume", "jd", "other"
        )
        for src in order:
            if not bucket[src]:
                continue
            remaining: Deque[BankQuestion] = deque()
            picked: Optional[BankQuestion] = None
            while bucket[src]:
                candidate = bucket[src].popleft()
                if picked is not None:
                    remaining.append(candidate)
                    continue
                norm = _normalize_question_text(candidate.question)
                if norm in used_question_texts:
                    remaining.append(candidate)
                    continue
                picked = candidate
            bucket[src] = remaining
            if picked is not None:
                return picked
        return None


@dataclass
class InterviewOrchestrator:
    """
    Per-session interview state machine.
    Thread-safe for reads/writes from LLM worker thread.
    """

    candidate_name: str
    jd_text: str
    cv_text: str
    planned_questions: List[BankQuestion]
    bot_id: str = ""
    language_mode: LanguageMode = "english"

    phase: InterviewPhase = InterviewPhase.GREETING
    current_index: int = 0
    abuse_warnings: int = 0
    stopped_reason: StoppedReason = StoppedReason.NONE

    # ── Clarifier state (reset each new main question) ──────────────────────
    awaiting_clarifier_reply: bool = False
    clarifier_count_this_question: int = 0
    _last_clarifier_partial: str = ""
    _last_clarifier_question: str = ""
    _last_spoken_question: str = ""
    _last_spoken_kind: str = ""  # main | clarifier
    # Each entry: {"bot_q": str, "candidate_a": str}
    _clarifier_thread: List[dict] = field(default_factory=list)
    # Accumulated partial answer text before clarifiers (initial chunk)
    _answer_initial_partial: str = ""

    # Meta-request counters (reset each new main question)
    question_repeat_count: int = 0
    question_rephrase_count: int = 0
    answer_continuation_count: int = 0
    _bridge_index: int = 0

    # Progress gate (depth vs drag) — reset each new main question
    drag_strikes: int = 0
    drag_rephrase_count: int = 0
    drag_depth_count: int = 0
    _last_clarifier_at_speech_sec: float = 0.0
    progress_checks: List[dict] = field(default_factory=list)
    force_completed: bool = False
    last_drag_rephrase_at: float = 0.0
    last_main_question_playback_at: float = 0.0
    last_mid_answer_bot_speech_at: float = 0.0
    question_advanced_at: float = 0.0
    _previous_question_text: str = ""

    # Turn-taking: presence vs answer-in-progress (see config ANSWER_* / PRESENCE_*)
    awaiting_answer_start: bool = False
    answer_in_progress: bool = False
    answer_speech_started_at: float = 0.0
    answer_budget_sec: float = 0.0
    answer_timed_check_1_done: bool = False
    answer_timed_check_2_done: bool = False
    spoken_interrupt_count: int = 0
    topic_poll_count: int = 0
    _mid_answer_clarifier: bool = False
    # Background score stash (parallel scoring while next Q is spoken)
    _pending_score_answer: str = ""
    _pending_score_q_index: int = 0

    answer_records: List[AnswerRecord] = field(default_factory=list)
    _rolling: RollingScoreTracker = field(default_factory=lambda: RollingScoreTracker(
        config.ROLLING_WINDOW
    ))
    # RLock: mark_clarifier_asked and other methods nest lock acquisition safely.
    _lock: threading.RLock = field(default_factory=threading.RLock)
    # Hinglish: id -> spoken question (pre-localized at join); English uses bank text
    _spoken_question_cache: Dict[str, str] = field(default_factory=dict)
    # not_needed | pending | ready | failed
    localization_status: str = "not_needed"
    localization_error: str = ""
    # Postgres interview_sessions.id when persistence is enabled
    db_interview_id: Optional[str] = None

    def is_localization_ready(self) -> bool:
        if self.language_mode != "hinglish":
            return True
        return self.localization_status == "ready"

    def get_spoken_question(self, q: Optional["BankQuestion"]) -> str:
        if not q:
            return ""
        if self.language_mode != "hinglish":
            return q.question
        return self._spoken_question_cache.get(q.id, q.question)

    def planned_questions_summary(self) -> List[dict]:
        """Interview plan for API responses (slot order, bank + spoken text)."""
        return [
            {
                "slot": i + 1,
                "id": q.id,
                "difficulty": q.normalized_difficulty,
                "source": q.source,
                "question": q.question,
                "spoken_question": self.get_spoken_question(q),
            }
            for i, q in enumerate(self.planned_questions)
        ]

    def apply_spoken_cache(self, cache: Dict[str, str], *, status: str = "ready") -> None:
        with self._lock:
            self._spoken_question_cache.update(cache)
            self.localization_status = status
            self.localization_error = ""
        if self.db_interview_id and cache:
            try:
                from interview_persist import update_spoken_questions

                update_spoken_questions(self.db_interview_id, dict(cache))
            except Exception as ex:
                logger.warning("[interview] spoken cache persist failed: %s", ex)

    def mark_localization_failed(self, error: str) -> None:
        with self._lock:
            self.localization_status = "failed"
            self.localization_error = (error or "unknown")[:500]

    @classmethod
    def create(
        cls,
        *,
        bot_id: str,
        candidate_name: str,
        jd_text: str,
        cv_text: str,
        bank: List[BankQuestion],
        language_mode: LanguageMode = "english",
        planned: Optional[List[BankQuestion]] = None,
        db_interview_id: Optional[str] = None,
    ) -> "InterviewOrchestrator":
        planned_qs = planned if planned is not None else QuestionSelector.select(
            bank, config.MAX_QUESTIONS
        )
        orch = cls(
            bot_id=bot_id,
            candidate_name=candidate_name.strip(),
            jd_text=jd_text.strip(),
            cv_text=cv_text.strip(),
            planned_questions=planned_qs,
            language_mode=language_mode,
            db_interview_id=db_interview_id,
        )
        orch._log_injection()
        return orch

    def _persist_answer_record(self, record: AnswerRecord) -> None:
        if not self.db_interview_id:
            return
        try:
            from interview_persist import persist_answer

            persist_answer(self.db_interview_id, record)
        except Exception as ex:
            logger.warning(
                "[interview] persist answer failed bot=%s: %s",
                self.bot_id[:8] if self.bot_id else "?",
                ex,
            )

    def _ui(self):
        return get_ui_strings(self.language_mode)

    def _log_injection(self) -> None:
        plan_summary = [
            {
                "slot": i + 1,
                "id": q.id,
                "difficulty": q.normalized_difficulty,
                "source": q.source,
                "question": q.question[:80] + ("..." if len(q.question) > 80 else ""),
            }
            for i, q in enumerate(self.planned_questions)
        ]
        logger.info(
            "[INTERVIEW INJECT] bot=%s candidate=%s jd_len=%d cv_len=%d "
            "bank_selected=%d/%d threshold=%.1f window=%d",
            self.bot_id[:8] if self.bot_id else "?",
            self.candidate_name,
            len(self.jd_text),
            len(self.cv_text),
            len(self.planned_questions),
            config.MAX_QUESTIONS,
            config.CONTINUE_AVG_THRESHOLD,
            config.ROLLING_WINDOW,
        )
        logger.info(
            "[INTERVIEW PLAN] bot=%s %s",
            self.bot_id[:8] if self.bot_id else "?",
            json.dumps(plan_summary, ensure_ascii=False),
        )

    @property
    def is_active(self) -> bool:
        return self.phase not in (InterviewPhase.ENDED, InterviewPhase.CLOSING)

    @property
    def is_ended(self) -> bool:
        return self.phase == InterviewPhase.ENDED

    def is_bootstrap_message(self, text: str) -> bool:
        return (text or "").strip().startswith("You are an AI interviewer named")

    def get_current_question(self) -> Optional[BankQuestion]:
        if self.current_index >= len(self.planned_questions):
            return None
        return self.planned_questions[self.current_index]

    def record_spoken(self, text: str, kind: str) -> None:
        """Track the most recent question the bot spoke (main or clarifier)."""
        spoken = (text or "").strip()
        if not spoken or kind not in ("main", "clarifier"):
            return
        with self._lock:
            self._last_spoken_question = spoken
            self._last_spoken_kind = kind
            logger.debug(
                "[SPOKEN] bot=%s kind=%s text=%r",
                self.bot_id[:8] if self.bot_id else "?",
                kind,
                spoken[:80],
            )

    def classification_context(self) -> dict:
        """Context block for the turn-intent LLM classifier."""
        main_q = self.get_current_question()
        return {
            "awaiting_clarifier_reply": self.awaiting_clarifier_reply,
            "main_question": main_q.question if main_q else "",
            "last_spoken_question": self._last_spoken_question,
            "last_spoken_kind": self._last_spoken_kind or "main",
            "last_clarifier_question": self._last_clarifier_question,
        }

    def decision_for_turn_intent(self, intent: str) -> Optional[TurnDecision]:
        """Map classified intent to an orchestrator action."""
        with self._lock:
            if intent == TurnIntent.REPEAT_LAST.value:
                return self._decision_repeat_last()
            if intent == TurnIntent.REPHRASE_LAST.value:
                return self._decision_rephrase_last()
            if intent == TurnIntent.REPEAT_MAIN.value:
                return self._decision_repeat_main()
            if intent == TurnIntent.CONTINUE_ANSWER.value:
                return TurnDecision(
                    action=TurnAction.SPEAK,
                    spoken_text=self._ui().please_continue,
                    should_continue=True,
                    spoken_kind="prompt",
                )
            return None

    def _decision_repeat_last(self) -> TurnDecision:
        kind = self._last_spoken_kind or "main"
        if self.awaiting_clarifier_reply or kind == "clarifier":
            target = self._last_clarifier_question or self._last_spoken_question
            if not target:
                target = self._last_spoken_question
            if not target:
                q = self.get_current_question()
                return self._on_repeat_question() if q else TurnDecision(
                    action=TurnAction.STOP, spoken_text="", should_continue=False
                )
            logger.info(
                "[INTENT] bot=%s Q%d repeat_last clarifier",
                self.bot_id[:8] if self.bot_id else "?",
                self.current_index + 1,
            )
            spoken = self._ui().repeat_last_clarifier.format(target=target)
            return TurnDecision(
                action=TurnAction.SPEAK,
                spoken_text=spoken,
                should_continue=True,
                spoken_kind="clarifier",
            )

        # Repeat the current planned question — never the greeting, nudge, or Q1 by mistake.
        return self._on_repeat_question()

    def _decision_rephrase_last(self) -> TurnDecision:
        target = self._last_spoken_question
        kind = self._last_spoken_kind or "main"
        if not target:
            if self.awaiting_clarifier_reply and self._last_clarifier_question:
                target = self._last_clarifier_question
                kind = "clarifier"
            else:
                q = self.get_current_question()
                target = q.question if q else ""
                kind = "main"
        if kind == "clarifier":
            logger.info(
                "[INTENT] bot=%s Q%d rephrase_last clarifier",
                self.bot_id[:8] if self.bot_id else "?",
                self.current_index + 1,
            )
            return TurnDecision(
                action=TurnAction.REPHRASE,
                spoken_text=target,
                should_continue=True,
                spoken_kind="clarifier",
                rephrase_flow=True,
            )
        return self._on_rephrase_question()

    def _decision_repeat_main(self) -> TurnDecision:
        self.awaiting_clarifier_reply = False
        logger.info(
            "[INTENT] bot=%s Q%d repeat_main (explicit)",
            self.bot_id[:8] if self.bot_id else "?",
            self.current_index + 1,
        )
        return self._on_repeat_question()

    def _next_bridge(self) -> str:
        bridges = self._ui().bridge_phrases
        phrase = bridges[self._bridge_index % len(bridges)]
        self._bridge_index += 1
        return phrase

    def try_handle_meta_intent(self, answer_text: str) -> Optional[TurnDecision]:
        """Handle repeat/rephrase requests before scoring. Returns None if not meta."""
        with self._lock:
            if self.phase != InterviewPhase.CORE:
                return None
            if self.awaiting_clarifier_reply:
                return None

            meta = detect_meta_intent(answer_text)
            if meta == "repeat":
                if detect_inability_answer(answer_text):
                    return None
                return self._on_repeat_question()
            if meta == "rephrase":
                return self._on_rephrase_question()
            return None

    def _on_repeat_question(self) -> TurnDecision:
        q = self.get_current_question()
        if not q:
            return TurnDecision(action=TurnAction.STOP, spoken_text="", should_continue=False)

        if self.question_repeat_count >= config.MAX_QUESTION_REPEATS:
            logger.info(
                "[META] bot=%s Q%d repeat limit reached (%d) — prompt only, no re-read",
                self.bot_id[:8] if self.bot_id else "?",
                self.current_index + 1,
                config.MAX_QUESTION_REPEATS,
            )
            spoken = self._ui().repeat_limit
            return TurnDecision(
                action=TurnAction.SPEAK,
                spoken_text=spoken,
                should_continue=True,
                spoken_kind="prompt",
            )

        self.question_repeat_count += 1
        logger.info(
            "[META] bot=%s Q%d repeat %d/%d",
            self.bot_id[:8] if self.bot_id else "?",
            self.current_index + 1,
            self.question_repeat_count,
            config.MAX_QUESTION_REPEATS,
        )
        if self.language_mode == "hinglish":
            spoken = self._ui().repeat_intro.format(question=q.question)
            return TurnDecision(
                action=TurnAction.SPEAK,
                spoken_text=spoken,
                should_continue=True,
                spoken_kind="main",
            )
        spoken = self._ui().repeat_intro.format(question=q.question)
        return TurnDecision(
            action=TurnAction.SPEAK,
            spoken_text=spoken,
            should_continue=True,
            spoken_kind="main",
        )

    def _on_rephrase_question(self) -> TurnDecision:
        q = self.get_current_question()
        if not q:
            return TurnDecision(action=TurnAction.STOP, spoken_text="", should_continue=False)

        if self.question_rephrase_count >= config.MAX_QUESTION_REPHRASES:
            logger.info(
                "[META] bot=%s Q%d rephrase limit reached (%d) — prompt only, no re-read",
                self.bot_id[:8] if self.bot_id else "?",
                self.current_index + 1,
                config.MAX_QUESTION_REPHRASES,
            )
            spoken = self._ui().rephrase_limit
            return TurnDecision(
                action=TurnAction.SPEAK,
                spoken_text=spoken,
                should_continue=True,
                spoken_kind="prompt",
            )

        self.question_rephrase_count += 1
        logger.info(
            "[META] bot=%s Q%d rephrase %d/%d — LLM will simplify",
            self.bot_id[:8] if self.bot_id else "?",
            self.current_index + 1,
            self.question_rephrase_count,
            config.MAX_QUESTION_REPHRASES,
        )
        return TurnDecision(
            action=TurnAction.REPHRASE,
            spoken_text=q.question,
            should_continue=True,
            spoken_kind="main",
            rephrase_flow=True,
        )

    def on_greeting_sent(self) -> None:
        with self._lock:
            self.phase = InterviewPhase.AWAIT_INTRO
            logger.info(
                "[INTERVIEW PHASE] bot=%s → await_intro",
                self.bot_id[:8] if self.bot_id else "?",
            )

    def on_intro_answer(self) -> TurnDecision:
        """First candidate response after greeting — not scored; ask Q1."""
        with self._lock:
            self.phase = InterviewPhase.CORE
            self.current_index = 0
            q = self.get_current_question()
            if not q:
                return self._build_stop(
                    "Thank you for introducing yourself. We'll wrap up here for today.",
                    StoppedReason.COMPLETED,
                )
            spoken = self._ui().intro_thanks.format(
                name=self.candidate_name,
                question=q.question,
            )
            logger.info(
                "[INTERVIEW PHASE] bot=%s → core | asking Q1/%d id=%s",
                self.bot_id[:8] if self.bot_id else "?",
                len(self.planned_questions),
                q.id,
            )
            return TurnDecision(
                action=TurnAction.SPEAK,
                spoken_text=spoken,
                spoken_kind="main",
            )

    def on_clarifier_reply(self, answer_text: str, clarifier_q: str = "") -> TurnDecision:
        """Short reply after bot mid-answer clarifier — not scored individually."""
        with self._lock:
            was_mid_answer = self._mid_answer_clarifier
            self.awaiting_clarifier_reply = False
            self._mid_answer_clarifier = False
            q = self.get_current_question()

            bot_q = clarifier_q or self._last_clarifier_question or self._last_clarifier_partial[:120]
            entry = {
                "bot_q": bot_q,
                "candidate_a": (answer_text or "").strip(),
            }
            self._clarifier_thread.append(entry)

            logger.info(
                "[CLARIFIER REPLY] bot=%s Q%d clarifier=%d/%d bot_q=%r candidate_a=%r",
                self.bot_id[:8] if self.bot_id else "?",
                self.current_index + 1,
                self.clarifier_count_this_question,
                config.BOT_INTERRUPT_MAX_CLARIFIERS_PER_Q,
                entry["bot_q"][:60],
                entry["candidate_a"][:60],
            )
            self._last_clarifier_partial = ""

            # After clarifier exchange, repeat requests should target the main question
            if q:
                self._last_spoken_question = q.question
                self._last_spoken_kind = "main"

            if self.should_score_after_clarifier_reply(
                answer_text, mid_answer=was_mid_answer
            ):
                logger.info(
                    "[CLARIFIER REPLY] Q%d substantive — scoring merged answer (skip continue prompt)",
                    self.current_index + 1,
                )
                return TurnDecision(
                    action=TurnAction.SPEAK,
                    spoken_text="",
                    should_continue=True,
                    spoken_kind="prompt",
                    score_clarifier_merged=True,
                )

            spoken = self._ui().continue_after_clarifier
            self.answer_in_progress = True
            self.awaiting_answer_start = False
            return TurnDecision(
                action=TurnAction.SPEAK,
                spoken_text=spoken,
                should_continue=True,
                spoken_kind="prompt",
            )

    def mark_clarifier_asked(
        self,
        partial_text: str,
        clarifier_q: str = "",
        speech_sec: float = 0.0,
        *,
        mid_answer: bool = True,
    ) -> None:
        with self._lock:
            self.awaiting_clarifier_reply = True
            self._mid_answer_clarifier = mid_answer
            self.clarifier_count_this_question += 1
            self._last_clarifier_at_speech_sec = max(0.0, speech_sec)
            self._last_clarifier_partial = (partial_text or "").strip()
            self._last_clarifier_question = (clarifier_q or "").strip()
            if self._last_clarifier_question:
                self._last_spoken_question = self._last_clarifier_question
                self._last_spoken_kind = "clarifier"
            if not self._answer_initial_partial:
                self._answer_initial_partial = (partial_text or "").strip()
            logger.info(
                "[CLARIFIER ASKED] bot=%s Q%d clarifier=%d/%d",
                self.bot_id[:8] if self.bot_id else "?",
                self.current_index + 1,
                self.clarifier_count_this_question,
                config.BOT_INTERRUPT_MAX_CLARIFIERS_PER_Q,
            )

    def clarifier_limit_reached(self) -> bool:
        """True when max ON_TRACK depth clarifiers for this question have been used."""
        return (
            self.clarifier_count_this_question
            >= config.BOT_INTERRUPT_MAX_DEPTH_CLARIFIERS_PER_Q
        )

    def mark_drag_rephrase(self) -> None:
        """Record a DRAG-focused rephrase — grace before scoring done-only turns."""
        self.last_drag_rephrase_at = time.monotonic()
        self.drag_rephrase_count += 1
        self.answer_continuation_count = 0

    def drag_rephrase_limit_reached(self) -> bool:
        return self.drag_rephrase_count >= config.BOT_INTERRUPT_DRAG_REPHRASE_MAX

    def drag_depth_limit_reached(self) -> bool:
        return self.drag_depth_count >= config.BOT_INTERRUPT_MAX_DRAG_DEPTH_PER_Q

    def mark_drag_depth_asked(
        self, partial_text: str, depth_q: str = "", speech_sec: float = 0.0
    ) -> None:
        """Record a mid-answer depth probe on in-context DRAG tangent."""
        with self._lock:
            self.drag_depth_count += 1
            self.awaiting_clarifier_reply = True
            self._last_clarifier_at_speech_sec = max(0.0, speech_sec)
            self._last_clarifier_partial = (partial_text or "").strip()
            self._last_clarifier_question = (depth_q or "").strip()
            if self._last_clarifier_question:
                self._last_spoken_question = self._last_clarifier_question
                self._last_spoken_kind = "clarifier"
            if not self._answer_initial_partial:
                self._answer_initial_partial = (partial_text or "").strip()
            logger.info(
                "[DRAG DEPTH ASKED] bot=%s Q%d depth=%d/%d",
                self.bot_id[:8] if self.bot_id else "?",
                self.current_index + 1,
                self.drag_depth_count,
                config.BOT_INTERRUPT_MAX_DRAG_DEPTH_PER_Q,
            )

    def within_drag_rephrase_grace(self) -> bool:
        if self.last_drag_rephrase_at <= 0:
            return False
        return (
            time.monotonic() - self.last_drag_rephrase_at
            < config.ANSWER_DRAG_GRACE_SEC
        )

    def has_active_answer_progress(self) -> bool:
        """True when mid-answer progress checks or partial context indicate an in-flight answer."""
        if self.awaiting_clarifier_reply:
            return True
        if self.progress_checks:
            return True
        if len(self._answer_initial_partial or "") >= config.TURN_FLUSH_GUARD_MIN_CHARS:
            return True
        if self.answer_continuation_count > 0:
            return True
        return False

    def mark_question_advanced(self, previous_question_text: str) -> None:
        """Record when we move to the next bank question — enables stale-tail guard."""
        self._previous_question_text = (previous_question_text or "").strip()
        self.question_advanced_at = time.monotonic()

    def mark_main_question_playback_done(self) -> None:
        self.last_main_question_playback_at = time.monotonic()

    def mark_bot_question_asked(self, kind: str) -> None:
        """Enable presence ladder; reset answer timers only for a new main question."""
        if kind not in ("main", "clarifier", "drag"):
            return
        with self._lock:
            self.awaiting_answer_start = True
            self.answer_in_progress = False
            if kind == "main":
                self.answer_speech_started_at = 0.0
                self.answer_budget_sec = float(config.ANSWER_INITIAL_LISTEN_SEC)
                self.answer_timed_check_1_done = False
                self.answer_timed_check_2_done = False
                self.spoken_interrupt_count = 0
                self.topic_poll_count = 0
                # Clear leftover mid-answer state so next Q cannot get stuck
                self.progress_checks = []
                self._answer_initial_partial = ""
                self.awaiting_clarifier_reply = False
                self._mid_answer_clarifier = False
                self.drag_strikes = 0
                self.drag_rephrase_count = 0
                self.drag_depth_count = 0
                self.force_completed = False
                self.last_drag_rephrase_at = 0.0
                self._reset_question_meta_state()

    def mark_answer_speech_started(self) -> None:
        with self._lock:
            self.awaiting_answer_start = False
            self.answer_in_progress = True
            if self.answer_speech_started_at <= 0:
                self.answer_speech_started_at = time.monotonic()

    def mark_answer_turn_committed(self) -> None:
        with self._lock:
            self.answer_in_progress = False
            self.awaiting_answer_start = False
            self.answer_speech_started_at = 0.0

    def should_schedule_presence(self) -> bool:
        if not config.PRESENCE_ONLY_AFTER_QUESTION:
            return True
        if config.PRESENCE_SKIP_DURING_ANSWER and self.answer_in_progress:
            return False
        return self.awaiting_answer_start and not self.answer_in_progress

    def get_answer_speech_sec(self) -> float:
        if self.answer_speech_started_at <= 0:
            return 0.0
        return max(0.0, time.monotonic() - self.answer_speech_started_at)

    def extend_answer_budget(self, speech_sec: float) -> None:
        cap = float(config.ANSWER_MAX_TOTAL_SEC)
        budget = max(self.answer_budget_sec, float(config.ANSWER_INITIAL_LISTEN_SEC))
        while speech_sec > budget and budget < cap:
            budget = min(budget + float(config.ANSWER_EXTEND_STEP_SEC), cap)
        self.answer_budget_sec = budget

    def answer_time_cap_reached(self, speech_sec: float) -> bool:
        self.extend_answer_budget(speech_sec)
        return speech_sec >= float(config.ANSWER_MAX_TOTAL_SEC)

    def spoken_interrupt_limit_reached(self) -> bool:
        """Topic redirects count as spoken interrupts (legacy slots disabled)."""
        return self.spoken_interrupt_count >= int(config.MAX_TOPIC_REDIRECTS_PER_QUESTION)

    def record_spoken_interrupt(self) -> None:
        self.spoken_interrupt_count += 1

    def sync_topic_polls_through(self, speech_sec: float) -> None:
        """Mark background polls up to speech_sec consumed (e.g. when slot wins at 90s)."""
        interval = float(config.ANSWER_TOPIC_POLL_INTERVAL_SEC)
        if interval <= 0 or speech_sec <= 0:
            return
        self.topic_poll_count = max(
            self.topic_poll_count, int(speech_sec // interval)
        )

    def _poll_collides_with_interrupt_slot(self, poll_at_sec: float) -> bool:
        tolerance = float(config.ANSWER_INTERRUPT_SLOT_TOLERANCE_SEC)
        for slot_time in (
            float(config.ANSWER_FIRST_CHECK_SEC),
            float(config.ANSWER_SECOND_CHECK_SEC),
        ):
            if abs(poll_at_sec - slot_time) <= tolerance:
                return True
        return False

    def should_run_timed_interrupt_check(self, speech_sec: float) -> Optional[int]:
        """Return 1 or 2 for scheduled check slots, or None."""
        if self.spoken_interrupt_limit_reached():
            return None
        if (
            speech_sec >= float(config.ANSWER_FIRST_CHECK_SEC)
            and not self.answer_timed_check_1_done
        ):
            return 1
        if (
            speech_sec >= float(config.ANSWER_SECOND_CHECK_SEC)
            and self.answer_timed_check_1_done
            and not self.answer_timed_check_2_done
        ):
            return 2
        return None

    def should_run_topic_poll(self, speech_sec: float) -> Optional[int]:
        """Background poll every ANSWER_TOPIC_POLL_INTERVAL_SEC; silent if on-track."""
        interval = float(config.ANSWER_TOPIC_POLL_INTERVAL_SEC)
        if interval <= 0 or speech_sec < interval:
            return None
        poll_index = int(speech_sec // interval)
        if poll_index <= self.topic_poll_count:
            return None
        poll_at = poll_index * interval
        if self._poll_collides_with_interrupt_slot(poll_at):
            self.topic_poll_count = poll_index
            return None
        return poll_index

    def resolve_progress_check(self, speech_sec: float) -> Optional[ProgressCheckSchedule]:
        """Topic poll only — legacy interrupt slots disabled."""
        poll_index = self.should_run_topic_poll(speech_sec)
        if poll_index is not None:
            return ProgressCheckSchedule(kind="poll", poll_index=poll_index)
        return None

    def stage1_scores_ready(self) -> bool:
        n = int(config.STAGE1_QUESTION_COUNT)
        scored = {
            r.question_index
            for r in self.answer_records
            if 1 <= r.question_index <= n
        }
        return all(i in scored for i in range(1, n + 1))

    def stage1_average(self) -> Optional[float]:
        n = int(config.STAGE1_QUESTION_COUNT)
        scores = [
            r.score for r in self.answer_records
            if 1 <= r.question_index <= n
        ]
        if len(scores) < n:
            return None
        return sum(scores) / len(scores)

    def should_gate_after_bridge(self) -> bool:
        """True while current question is the bridge (Q6) — gate after it is scored."""
        return (self.current_index + 1) == int(config.STAGE1_BRIDGE_QUESTION)

    def topic_redirect_limit_reached(self) -> bool:
        return self.spoken_interrupt_count >= int(config.MAX_TOPIC_REDIRECTS_PER_QUESTION)

    def advance_without_score(
        self,
        answer_text: str,
        *,
        bridge: Optional[str] = None,
    ) -> TurnDecision:
        """Speak next question immediately; score previous answer in background."""
        with self._lock:
            if self.phase == InterviewPhase.ENDED:
                return TurnDecision(
                    action=TurnAction.STOP,
                    spoken_text="",
                    should_continue=False,
                    stopped_reason=self.stopped_reason,
                )
            if detect_abuse(answer_text):
                return self._handle_abuse()

            q = self.get_current_question()
            if not q:
                return self._complete_all()

            self._pending_score_answer = (answer_text or "").strip()
            self._pending_score_q_index = self.current_index + 1

            # Peek next question before mutating index
            if self.current_index + 1 >= len(self.planned_questions):
                # Last question — caller scores sync and closes (do not advance yet)
                return TurnDecision(
                    action=TurnAction.SPEAK,
                    spoken_text="",
                    should_continue=True,
                    spoken_kind="prompt",
                    defer_close=True,
                    pending_background_score=True,
                )

            self._reset_clarifier_state()
            self.mark_question_advanced(q.question)
            self.current_index += 1
            next_q = self.get_current_question()
            if next_q is None:
                return self._complete_all()

            spoken_q = self.get_spoken_question(next_q)
            prefix = (bridge or "").strip() or self._next_bridge()
            spoken = f"{prefix} {spoken_q}".strip()
            # Custom bridge (e.g. inability ack) — speak directly in both languages
            if bridge and (bridge or "").strip():
                return TurnDecision(
                    action=TurnAction.SPEAK,
                    spoken_text=spoken,
                    should_continue=True,
                    spoken_kind="main",
                    pending_background_score=True,
                )
            if self.language_mode == "hinglish":
                return TurnDecision(
                    action=TurnAction.REPHRASE,
                    spoken_text=spoken_q,
                    should_continue=True,
                    spoken_kind="main",
                    use_simple_bridge=True,
                    rephrase_flow=True,
                    pending_background_score=True,
                )
            return TurnDecision(
                action=TurnAction.SPEAK,
                spoken_text=spoken,
                should_continue=True,
                spoken_kind="main",
                pending_background_score=True,
            )

    def apply_background_score(
        self,
        question_index: int,
        answer_text: str,
        evaluation: EvaluationResult,
    ) -> None:
        """Record draft score while next question is already being asked."""
        with self._lock:
            if any(r.question_index == question_index for r in self.answer_records):
                return
            if not (1 <= question_index <= len(self.planned_questions)):
                return
            q = self.planned_questions[question_index - 1]
            record = AnswerRecord(
                question_index=question_index,
                question_id=q.id,
                difficulty=q.normalized_difficulty,
                source=q.source,
                question_text=q.question,
                answer_text=(answer_text or "").strip(),
                score=evaluation.score,
                confident=evaluation.confident,
                relevant=evaluation.relevant,
                strengths=evaluation.strengths,
                develop=evaluation.develop,
                fix=evaluation.fix,
            )
            self.answer_records.append(record)
            self.answer_records.sort(key=lambda r: r.question_index)
            self._rolling.push(evaluation.score)
            avg = (
                self.stage1_average()
                if question_index <= config.STAGE1_QUESTION_COUNT
                else self._rolling.average()
            )
            self._log_score(record, avg, True)
            logger.info(
                "[BG SCORE] bot=%s Q%d score=%d/10 stage1_avg=%s",
                self.bot_id[:8] if self.bot_id else "?",
                question_index,
                evaluation.score,
                f"{avg:.2f}" if avg is not None else "n/a",
            )
        self._persist_answer_record(record)

    def decide_after_bridge(
        self,
        answer_text: str,
        evaluation: EvaluationResult,
    ) -> TurnDecision:
        """After Q6: record score, gate on Q1–Q5 avg, then continue or wrap."""
        with self._lock:
            if detect_abuse(answer_text):
                return self._handle_abuse()

            q = self.get_current_question()
            if not q:
                return self._complete_all()

            record = AnswerRecord(
                question_index=self.current_index + 1,
                question_id=q.id,
                difficulty=q.normalized_difficulty,
                source=q.source,
                question_text=q.question,
                answer_text=(answer_text or "").strip(),
                score=evaluation.score,
                confident=evaluation.confident,
                relevant=evaluation.relevant,
                strengths=evaluation.strengths,
                develop=evaluation.develop,
                fix=evaluation.fix,
            )
            if not any(r.question_index == record.question_index for r in self.answer_records):
                self.answer_records.append(record)
                self.answer_records.sort(key=lambda r: r.question_index)
                self._persist_answer_record(record)

            stage_avg = self.stage1_average()
            if stage_avg is None:
                scored = [
                    r.score for r in self.answer_records
                    if r.question_index <= config.STAGE1_QUESTION_COUNT
                ]
                stage_avg = (sum(scored) / len(scored)) if scored else 0.0
                logger.warning(
                    "[STAGE1 GATE] bot=%s incomplete Q1–Q5 scores — using partial avg=%.2f",
                    self.bot_id[:8] if self.bot_id else "?",
                    stage_avg,
                )

            can_continue = stage_avg >= float(config.CONTINUE_AVG_THRESHOLD)
            self._log_score(record, stage_avg, can_continue)
            self._reset_clarifier_state()

            logger.info(
                "[STAGE1 GATE] bot=%s after Q%d stage1_avg=%.2f threshold=%.1f continue=%s",
                self.bot_id[:8] if self.bot_id else "?",
                config.STAGE1_BRIDGE_QUESTION,
                stage_avg,
                config.CONTINUE_AVG_THRESHOLD,
                can_continue,
            )

            if not can_continue:
                closing = f"{self._next_bridge()} {self._ui().closing_low_average}"
                return self._build_stop(
                    closing,
                    StoppedReason.LOW_ROLLING_AVERAGE,
                    record,
                    stage_avg,
                )

            self.mark_question_advanced(q.question)
            self.current_index += 1
            next_q = self.get_current_question()
            if next_q is None:
                return self._complete_all(record, stage_avg)

            spoken_q = self.get_spoken_question(next_q)
            spoken = f"{self._next_bridge()} {spoken_q}"
            if self.language_mode == "hinglish":
                return TurnDecision(
                    action=TurnAction.REPHRASE,
                    spoken_text=spoken_q,
                    score_record=record,
                    rolling_average=stage_avg,
                    should_continue=True,
                    spoken_kind="main",
                    use_simple_bridge=True,
                    rephrase_flow=True,
                )
            return TurnDecision(
                action=TurnAction.SPEAK,
                spoken_text=spoken,
                score_record=record,
                rolling_average=stage_avg,
                should_continue=True,
                spoken_kind="main",
            )

    def mark_topic_poll_done(self, poll_index: int) -> None:
        self.topic_poll_count = max(self.topic_poll_count, poll_index)

    def mark_timed_check_done(self, slot: int, speech_sec: float = 0.0) -> None:
        if slot == 1:
            self.answer_timed_check_1_done = True
        elif slot == 2:
            self.answer_timed_check_2_done = True
        if speech_sec > 0:
            self.sync_topic_polls_through(speech_sec)

    def skip_question_no_response(self) -> TurnDecision:
        """Presence ladder exhausted — score empty answer and advance."""
        with self._lock:
            q = self.get_current_question()
            if not q:
                return self._build_stop(
                    self._ui().closing_completed,
                    StoppedReason.COMPLETED,
                )
            evaluation = EvaluationResult(
                score=0,
                confident=False,
                relevant=False,
                strengths="",
                develop="No audible response after multiple presence checks.",
                fix="Ensure microphone is unmuted and you are in a quiet environment.",
            )
            self.mark_answer_turn_committed()
            return self.force_complete_question("", evaluation)

    def mark_mid_answer_bot_playback_done(self) -> None:
        self.last_mid_answer_bot_speech_at = time.monotonic()

    def within_main_question_interrupt_cooldown(self) -> bool:
        """Block depth/DRAG probes right after a new main question (think time)."""
        if self.last_main_question_playback_at <= 0:
            return False
        if self.progress_checks:
            return False
        if len(self._answer_initial_partial or "") >= config.TURN_FLUSH_GUARD_MIN_CHARS:
            return False
        elapsed = time.monotonic() - self.last_main_question_playback_at
        return elapsed < config.MAIN_QUESTION_INTERRUPT_COOLDOWN_SEC

    def within_mid_answer_bot_cooldown(self) -> bool:
        if self.last_mid_answer_bot_speech_at <= 0:
            return False
        return (
            time.monotonic() - self.last_mid_answer_bot_speech_at
            < config.MID_ANSWER_BOT_COOLDOWN_SEC
        )

    def within_stale_answer_guard(self) -> bool:
        if self.question_advanced_at <= 0:
            return False
        return (
            time.monotonic() - self.question_advanced_at
            < config.STALE_ANSWER_GUARD_SEC
        )

    def is_stale_previous_question_tail(self, text: str) -> bool:
        """Drop short tail commits that still match the previous question topic."""
        if not self.within_stale_answer_guard():
            return False
        t = (text or "").strip()
        if not t or len(t) >= config.STALE_ANSWER_MAX_CHARS:
            return False
        if not self._previous_question_text:
            return False
        curr = self.get_current_question()
        if not curr:
            return False
        text_tokens = set(re.findall(r"\b\w{4,}\b", t.lower()))
        prev_overlap = len(_question_topic_tokens(self._previous_question_text) & text_tokens)
        curr_overlap = len(_question_topic_tokens(curr.question) & text_tokens)
        if prev_overlap >= 2 and prev_overlap > curr_overlap:
            return True
        return False

    def should_score_after_clarifier_reply(
        self, answer_text: str, *, mid_answer: bool = False
    ) -> bool:
        """Mid-answer depth probe → continue main answer; score only on explicit done."""
        t = (answer_text or "").strip()
        if not t:
            return False
        if mid_answer or (
            self._answer_initial_partial and self.clarifier_count_this_question > 0
        ):
            return detect_answer_done_phrase(t)
        if detect_answer_done_phrase(t):
            return True
        if len(t) >= config.CLARIFIER_REPLY_SCORE_MIN_CHARS:
            return True
        if len(t.split()) >= config.MIN_ANSWER_WORDS:
            return True
        partial_len = len(self._answer_initial_partial or "")
        if partial_len >= config.TURN_FLUSH_GUARD_MIN_CHARS and len(t) >= 20:
            return True
        return False

    def can_run_progress_gate(self, *, is_ai_speaking: bool = False) -> tuple:
        """Single gate for mid-answer depth/DRAG — prevents overlapping bot speech."""
        if is_ai_speaking:
            return False, "bot_speaking"
        if self.awaiting_clarifier_reply:
            return False, "awaiting_clarifier"
        if self.within_main_question_interrupt_cooldown():
            return False, "main_q_cooldown"
        if self.within_mid_answer_bot_cooldown():
            return False, "mid_answer_cooldown"
        if self.within_drag_rephrase_grace() and self.drag_rephrase_count > 0:
            return False, "drag_rephrase_grace"
        return True, ""

    def merge_answer_if_done_phrase(self, answer_text: str) -> Optional[str]:
        """
        When the candidate says only a completion cue, merge with accumulated partial
        so scoring uses the full answer instead of 'That's it.' alone.
        """
        t = (answer_text or "").strip()
        if not detect_answer_done_phrase(t):
            return None
        partial = (self._answer_initial_partial or "").strip()
        if not partial and not self.progress_checks:
            return None
        if len(t) <= 50 and partial:
            return self.build_merged_answer_context("")
        return self.build_merged_answer_context(t)

    def build_merged_answer_context(self, final_answer: str) -> str:
        """Combine initial partial + clarifier Q&As + final continuation for scoring."""
        parts = []
        if self._answer_initial_partial:
            parts.append(f"Initial answer:\n{self._answer_initial_partial}")
        for i, entry in enumerate(self._clarifier_thread, 1):
            parts.append(
                f"[Clarifier {i}]\n"
                f"  Interviewer asked: {entry['bot_q']}\n"
                f"  Candidate replied: {entry['candidate_a']}"
            )
        if final_answer.strip():
            parts.append(f"Final continuation:\n{final_answer.strip()}")
        return "\n\n".join(parts) if parts else final_answer.strip()

    def record_progress_check(
        self,
        check_num: int,
        verdict: str,
        confidence: float,
        reason: str,
        speech_sec: float,
    ) -> int:
        """Log a mid-answer progress gate result; increment drag_strikes when confident DRAG."""
        with self._lock:
            entry = {
                "check_num": check_num,
                "verdict": verdict,
                "confidence": confidence,
                "reason": reason,
                "speech_sec": speech_sec,
            }
            self.progress_checks.append(entry)
            if (
                verdict == "DRAG"
                and confidence >= config.BOT_INTERRUPT_GATE_MIN_CONFIDENCE
            ):
                self.drag_strikes += 1
            return self.drag_strikes

    def build_drag_context(self) -> str:
        """Multi-line progress gate summary for the evaluator prompt."""
        if not self.progress_checks:
            return ""
        lines = []
        for entry in self.progress_checks:
            lines.append(
                f"Check {entry['check_num']} at {entry['speech_sec']:.0f}s: "
                f"{entry['verdict']} (confidence={entry['confidence']:.2f}) — "
                f"{entry['reason']}"
            )
        if self.force_completed or self.drag_depth_limit_reached():
            lines.append(
                "Force-completed: yes (candidate went off-topic; "
                f"{self.drag_depth_count} in-context depth probe(s))"
            )
        return "\n".join(lines)

    def force_complete_question(
        self,
        answer_text: str,
        evaluation: EvaluationResult,
    ) -> TurnDecision:
        """End current question early after repeated drag — score and advance."""
        with self._lock:
            self.force_completed = True
            if self.phase == InterviewPhase.ENDED:
                return TurnDecision(
                    action=TurnAction.STOP,
                    spoken_text="",
                    should_continue=False,
                    stopped_reason=self.stopped_reason,
                )

            q = self.get_current_question()
            if not q:
                return self._complete_all()

            merged_answer = self.build_merged_answer_context(answer_text)
            record = AnswerRecord(
                question_index=self.current_index + 1,
                question_id=q.id,
                difficulty=q.normalized_difficulty,
                source=q.source,
                question_text=q.question,
                answer_text=merged_answer.strip(),
                score=evaluation.score,
                confident=evaluation.confident,
                relevant=evaluation.relevant,
                strengths=evaluation.strengths,
                develop=evaluation.develop,
                fix=evaluation.fix,
            )
            self.answer_records.append(record)
            self._rolling.push(evaluation.score)

            rolling_avg = self._rolling.average()
            can_continue = self._rolling.can_continue(config.CONTINUE_AVG_THRESHOLD)

            logger.info(
                "[FORCE COMPLETE] bot=%s Q%d drag_strikes=%d score=%d",
                self.bot_id[:8] if self.bot_id else "?",
                self.current_index + 1,
                self.drag_strikes,
                evaluation.score,
            )
            self._log_score(record, rolling_avg, can_continue)
            self._persist_answer_record(record)

            self._reset_clarifier_state()

            # Do not apply rolling gate here — stage-1 gate runs after bridge Q only
            self.mark_question_advanced(q.question)
            self.current_index += 1
            next_q = self.get_current_question()

            if next_q is None:
                return self._complete_all(record, rolling_avg)

            spoken = f"Okay, thank you. Let's continue. {self.get_spoken_question(next_q)}"
            if self.language_mode == "hinglish":
                # Always use simple bridge for NEW questions — rephrase intro only for
                # explicit user-requested rephrases of the SAME question.
                return TurnDecision(
                    action=TurnAction.REPHRASE,
                    spoken_text=self.get_spoken_question(next_q),
                    score_record=record,
                    rolling_average=rolling_avg,
                    should_continue=True,
                    spoken_kind="main",
                    use_simple_bridge=True,
                    rephrase_flow=True,
                )
            return TurnDecision(
                action=TurnAction.SPEAK,
                spoken_text=spoken,
                score_record=record,
                rolling_average=rolling_avg,
                should_continue=True,
                spoken_kind="main",
            )

    def _reset_clarifier_state(self) -> None:
        """Called when moving to the next main question."""
        self.awaiting_clarifier_reply = False
        self.clarifier_count_this_question = 0
        self._last_clarifier_partial = ""
        self._last_clarifier_question = ""
        self._clarifier_thread = []
        self._answer_initial_partial = ""
        self.drag_strikes = 0
        self.drag_rephrase_count = 0
        self.drag_depth_count = 0
        self._last_clarifier_at_speech_sec = 0.0
        self.progress_checks = []
        self.force_completed = False
        self.last_drag_rephrase_at = 0.0
        self._reset_question_meta_state()
        self.awaiting_answer_start = False
        self.answer_in_progress = False
        self.answer_speech_started_at = 0.0
        self.answer_budget_sec = float(config.ANSWER_INITIAL_LISTEN_SEC)
        self.answer_timed_check_1_done = False
        self.answer_timed_check_2_done = False
        self.spoken_interrupt_count = 0
        self.topic_poll_count = 0
        self._mid_answer_clarifier = False

    def _reset_question_meta_state(self) -> None:
        self.question_repeat_count = 0
        self.question_rephrase_count = 0
        self.answer_continuation_count = 0

    def try_handle_continuation_checkin(self, answer_text: str) -> Optional[TurnDecision]:
        """Respond to hello/check-in/permission while waiting for a continued answer — do not score."""
        if self.answer_continuation_count <= 0:
            return None
        if self.phase != InterviewPhase.CORE:
            return None
        is_permission = detect_continuation_permission(answer_text)
        is_checkin = detect_continuation_checkin(answer_text)
        if not is_permission and not is_checkin:
            return None
        ui = self._ui()
        spoken = ui.permission_to_continue if is_permission else ui.please_continue_when_ready
        logger.info(
            "[CONTINUATION CHECKIN] bot=%s Q%d permission=%s text=%r",
            self.bot_id[:8] if self.bot_id else "?",
            self.current_index + 1,
            is_permission,
            (answer_text or "")[:80],
        )
        return TurnDecision(
            action=TurnAction.SPEAK,
            spoken_text=spoken,
            should_continue=True,
            spoken_kind="prompt",
        )

    def try_handle_incomplete_answer(self, answer_text: str) -> Optional[TurnDecision]:
        """Ask candidate to continue when answer looks cut off (not scored)."""
        if not config.INCOMPLETE_ANSWER_CHECK_ENABLED:
            return None
        if self.awaiting_clarifier_reply:
            return None
        if self.phase != InterviewPhase.CORE:
            return None
        if detect_short_complete_answer(answer_text):
            return None
        if detect_answer_done_phrase(answer_text):
            return None
        if not detect_incomplete_answer(answer_text):
            return None
        if self.answer_continuation_count >= config.MAX_ANSWER_CONTINUATIONS:
            logger.info(
                "[INCOMPLETE] bot=%s Q%d continuation limit reached — scoring anyway",
                self.bot_id[:8] if self.bot_id else "?",
                self.current_index + 1,
            )
            return None

        with self._lock:
            self.answer_continuation_count += 1
            logger.info(
                "[INCOMPLETE] bot=%s Q%d continuation %d/%d text=%r",
                self.bot_id[:8] if self.bot_id else "?",
                self.current_index + 1,
                self.answer_continuation_count,
                config.MAX_ANSWER_CONTINUATIONS,
                (answer_text or "")[:80],
            )
            return TurnDecision(
                action=TurnAction.SPEAK,
                spoken_text=self._ui().please_continue,
                should_continue=True,
            )

    def process_answer(
        self,
        answer_text: str,
        evaluation: EvaluationResult,
    ) -> TurnDecision:
        with self._lock:
            if self.awaiting_clarifier_reply:
                return self.on_clarifier_reply(answer_text)

            if self.phase == InterviewPhase.ENDED:
                return TurnDecision(
                    action=TurnAction.STOP,
                    spoken_text="",
                    should_continue=False,
                    stopped_reason=self.stopped_reason,
                )

            if detect_abuse(answer_text):
                return self._handle_abuse()

            q = self.get_current_question()
            if not q:
                return self._complete_all()

            clarifier_count = self.clarifier_count_this_question
            record = AnswerRecord(
                question_index=self.current_index + 1,
                question_id=q.id,
                difficulty=q.normalized_difficulty,
                source=q.source,
                question_text=q.question,
                answer_text=answer_text.strip(),
                score=evaluation.score,
                confident=evaluation.confident,
                relevant=evaluation.relevant,
                strengths=evaluation.strengths,
                develop=evaluation.develop,
                fix=evaluation.fix,
            )
            self.answer_records.append(record)
            self._rolling.push(evaluation.score)

            rolling_avg = self._rolling.average()
            can_continue = self._rolling.can_continue(config.CONTINUE_AVG_THRESHOLD)

            self._log_score(record, rolling_avg, can_continue)
            self._persist_answer_record(record)
            if clarifier_count:
                logger.info(
                    "[SCORE] bot=%s Q%d scored with %d clarifier exchange(s) included",
                    self.bot_id[:8] if self.bot_id else "?",
                    self.current_index + 1,
                    clarifier_count,
                )

            # Reset clarifier state before advancing
            self._reset_clarifier_state()

            # Stage-1 gate only after bridge question (Q6) — never wrap mid-Q6
            if self.should_gate_after_bridge():
                # Caller should use decide_after_bridge; keep sync path safe
                stage_avg = self.stage1_average()
                if stage_avg is None:
                    scored = [
                        r.score for r in self.answer_records
                        if r.question_index <= config.STAGE1_QUESTION_COUNT
                    ]
                    stage_avg = (sum(scored) / len(scored)) if scored else rolling_avg or 0.0
                if stage_avg < float(config.CONTINUE_AVG_THRESHOLD):
                    return self._build_stop(
                        self._ui().closing_low_average,
                        StoppedReason.LOW_ROLLING_AVERAGE,
                        record,
                        stage_avg,
                    )
            # Q1–Q5 and Q7–Q10: do not stop on rolling avg here (parallel path / stage gate)

            self.mark_question_advanced(q.question)
            self.current_index += 1
            next_q = self.get_current_question()

            if next_q is None:
                return self._complete_all(record, rolling_avg)

            spoken = f"{self._next_bridge()} {self.get_spoken_question(next_q)}"
            if self.language_mode == "hinglish":
                # Always use simple bridge for NEW questions — rephrase intro only for
                # explicit user-requested rephrases of the SAME question.
                return TurnDecision(
                    action=TurnAction.REPHRASE,
                    spoken_text=self.get_spoken_question(next_q),
                    score_record=record,
                    rolling_average=rolling_avg,
                    should_continue=True,
                    spoken_kind="main",
                    use_simple_bridge=True,
                    rephrase_flow=True,
                )
            return TurnDecision(
                action=TurnAction.SPEAK,
                spoken_text=spoken,
                score_record=record,
                rolling_average=rolling_avg,
                should_continue=True,
                spoken_kind="main",
            )

    def _handle_abuse(self) -> TurnDecision:
        q = self.get_current_question()
        if not q:
            return self._build_stop(
                self._ui().closing_abuse,
                StoppedReason.ABUSE,
            )

        if self.abuse_warnings < config.ABUSE_MAX_WARNINGS:
            self.abuse_warnings += 1
            logger.warning(
                "[INTERVIEW ABUSE] bot=%s warning=%d/%d re-asking Q%d id=%s",
                self.bot_id[:8] if self.bot_id else "?",
                self.abuse_warnings,
                config.ABUSE_MAX_WARNINGS,
                self.current_index + 1,
                q.id,
            )
            spoken = self._ui().abuse_warning.format(question=q.question)
            return TurnDecision(
                action=TurnAction.WARN_ABUSE,
                spoken_text=spoken,
                should_continue=True,
            )

        logger.warning(
            "[INTERVIEW ABUSE] bot=%s second offense — stopping interview",
            self.bot_id[:8] if self.bot_id else "?",
        )
        return self._build_stop(
            self._ui().closing_abuse,
            StoppedReason.ABUSE,
        )

    def _complete_all(
        self,
        last_record: Optional[AnswerRecord] = None,
        rolling_avg: Optional[float] = None,
    ) -> TurnDecision:
        self.phase = InterviewPhase.CLOSING
        self.stopped_reason = StoppedReason.COMPLETED
        spoken = self._ui().closing_completed
        logger.info(
            "[INTERVIEW END] bot=%s reason=completed_all_questions scored=%d",
            self.bot_id[:8] if self.bot_id else "?",
            len(self.answer_records),
        )
        return TurnDecision(
            action=TurnAction.STOP,
            spoken_text=spoken,
            score_record=last_record,
            rolling_average=rolling_avg,
            should_continue=False,
            stopped_reason=StoppedReason.COMPLETED,
        )

    def _build_stop(
        self,
        spoken: str,
        reason: StoppedReason,
        record: Optional[AnswerRecord] = None,
        rolling_avg: Optional[float] = None,
    ) -> TurnDecision:
        self.phase = InterviewPhase.CLOSING
        self.stopped_reason = reason
        logger.info(
            "[INTERVIEW END] bot=%s reason=%s scored=%d rolling_avg=%s",
            self.bot_id[:8] if self.bot_id else "?",
            reason.value,
            len(self.answer_records),
            f"{rolling_avg:.2f}" if rolling_avg is not None else "n/a",
        )
        return TurnDecision(
            action=TurnAction.STOP,
            spoken_text=spoken,
            score_record=record,
            rolling_average=rolling_avg,
            should_continue=False,
            stopped_reason=reason,
        )

    def mark_ended(self) -> None:
        with self._lock:
            self.phase = InterviewPhase.ENDED

    def _log_score(
        self,
        record: AnswerRecord,
        rolling_avg: Optional[float],
        can_continue: bool,
    ) -> None:
        logger.info(
            "[SCORE] bot=%s Q%d/%d id=%s difficulty=%s score=%d/10 "
            "confident=%s relevant=%s rolling=%s avg=%.2f threshold=%.1f continue=%s",
            self.bot_id[:8] if self.bot_id else "?",
            record.question_index,
            len(self.planned_questions),
            record.question_id,
            record.difficulty,
            record.score,
            record.confident,
            record.relevant,
            self._rolling.snapshot(),
            rolling_avg if rolling_avg is not None else 0.0,
            config.CONTINUE_AVG_THRESHOLD,
            can_continue,
        )
        if record.develop or record.fix:
            logger.info(
                "[SCORE DETAIL] bot=%s Q%d develop=%r fix=%r strengths=%r",
                self.bot_id[:8] if self.bot_id else "?",
                record.question_index,
                record.develop,
                record.fix,
                record.strengths,
            )

    def build_report(self) -> dict:
        with self._lock:
            scores = [r.score for r in self.answer_records]
            overall = sum(scores) / len(scores) if scores else None
            last_4 = self._rolling.snapshot()
            last_4_avg = (
                sum(last_4) / len(last_4) if last_4 else None
            )

            develop_items = [
                r.develop for r in self.answer_records if r.develop
            ]
            fix_items = [r.fix for r in self.answer_records if r.fix]

            report = {
                "candidate_name": self.candidate_name,
                "bot_id": self.bot_id,
                "phase": self.phase.value,
                "stopped_reason": self.stopped_reason.value,
                "questions_planned": len(self.planned_questions),
                "questions_scored": len(self.answer_records),
                "abuse_warnings": self.abuse_warnings,
                "continue_threshold": config.CONTINUE_AVG_THRESHOLD,
                "rolling_window": config.ROLLING_WINDOW,
                "last_4_average": round(last_4_avg, 2) if last_4_avg is not None else None,
                "overall_average": round(overall, 2) if overall is not None else None,
                "per_question": [r.to_dict() for r in self.answer_records],
                "planned_questions": [
                    {
                        "slot": i + 1,
                        "id": q.id,
                        "difficulty": q.normalized_difficulty,
                        "source": q.source,
                        "question": q.question,
                        "asked": i < self.current_index or any(
                            r.question_id == q.id for r in self.answer_records
                        ),
                    }
                    for i, q in enumerate(self.planned_questions)
                ],
                "summary_develop": list(dict.fromkeys(develop_items)),
                "summary_fix": list(dict.fromkeys(fix_items)),
            }
            if self.bot_id:
                from transcript_log import get_session_transcript
                report["transcript"] = get_session_transcript(self.bot_id)
            return report

    def document_context_for_llm(self) -> str:
        blocks = []
        if self.candidate_name:
            blocks.append(
                f"=== CANDIDATE NAME ===\n{self.candidate_name}"
            )
        if self.jd_text:
            blocks.append(f"=== JOB DESCRIPTION ===\n{self.jd_text}")
        if self.cv_text:
            blocks.append(f"=== CANDIDATE RESUME ===\n{self.cv_text}")
        blocks.append(f"=== GROUNDING RULES ===\n{GROUNDING_RULES}")
        return "\n\n".join(blocks)

    def evaluator_context(self, question: BankQuestion, merged_answer: str = "") -> str:
        """Build evaluator prompt context, optionally with merged clarifier thread."""
        base = (
            f"Question ({question.normalized_difficulty}, {question.source}): "
            f"{question.question}\n\n"
            f"JD excerpt (for relevance):\n{self.jd_text[:1200]}\n\n"
            f"Resume excerpt (for relevance):\n{self.cv_text[:1200]}"
        )
        if merged_answer:
            base += (
                "\n\nNOTE: The candidate's answer below includes mid-answer clarifier exchanges. "
                "Extra depth from clarifiers is a positive signal, not padding. "
                "Score based on the full picture.\n"
            )
        if self.drag_strikes > 0 or self.progress_checks:
            base += (
                f"\n\nProgress gate notes:\n{self.build_drag_context()}\n"
                "If drag_strikes >= 2: candidate went off-topic; reflect in 'develop' and "
                "score the substantive content only (ignore the off-topic portion).\n"
            )
        return base


def parse_bank_questions(raw_list: List[dict]) -> List[BankQuestion]:
    """Validate and parse API question bank items."""
    if not raw_list:
        raise ValueError("questions list cannot be empty")

    bank: List[BankQuestion] = []
    for i, item in enumerate(raw_list):
        q_text = (item.get("question") or "").strip()
        if not q_text:
            raise ValueError(f"questions[{i}].question is required")
        bank.append(
            BankQuestion(
                id=str(item.get("id") or f"q{i + 1}"),
                difficulty=str(item.get("difficulty") or "Low"),
                source=str(item.get("source") or "jd"),
                question=q_text,
            )
        )
    return bank


def _evaluator_system_prompt() -> str:
    from system_prompt import STT_EVALUATOR_NOTE

    return (
        "You are an interview answer evaluator. Return ONLY valid JSON, no markdown. "
        "Score the candidate answer 0-10 for a technical screening interview. "
        "Fields: score (int 0-10), confident (bool), relevant (bool), "
        "strengths (short string), develop (area to improve), fix (actionable tip). "
        "Be fair: partial answers can be 5-7; strong specific answers 8-10; "
        "off-topic or empty 0-4. confident=false if vague, unsure, or filler-heavy. "
        "If progress_notes are present: note off-topic drift in develop/fix; "
        "score based on substantive content, not filler or repeated generalities. "
        f"{STT_EVALUATOR_NOTE}"
    )


EVALUATOR_SYSTEM_PROMPT = _evaluator_system_prompt()
