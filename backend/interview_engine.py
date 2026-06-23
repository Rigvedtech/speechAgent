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
    r"\b(and|so|because|but|like|um|uh|or|if|when|that|then|also|with|for)$",
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
    ]),
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
        r"\bhaven'?t\s+(used|worked)\b",
        r"\bnahi\s+pata\b",
        r"\bpata\s+nahi\b",
        r"\b(nahi|na)\s+yaad\b",
        r"\bmalum\s+nahi\b",
        r"\bjawab\s+nahi\b",
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


@dataclass
class ProgressCheckPayload:
    """Mid-answer progress gate input — queued from STT to LLM worker."""
    full_partial: str
    recent_segment: str
    speech_sec: float
    check_num: int


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


def detect_inability_answer(text: str) -> bool:
    """Short honest 'I don't know' — complete thought, not a cut-off fragment."""
    t = (text or "").strip()
    if not t or len(t) > 80:
        return False
    return bool(_INABILITY_PATTERNS.search(t))


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
    if not t or len(t) > 60:
        return False
    if _CONTINUATION_CHECKIN.search(t):
        return True
    if _SHORT_IMMEDIATE_TURN.search(t) and len(t.split()) <= 4:
        return True
    return False


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


def detect_presence_confirm(text: str) -> bool:
    """Candidate confirms they can hear the bot after a presence check."""
    t = (text or "").strip()
    if not t or len(t) > 80:
        return False
    if detect_continuation_checkin(t):
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
    if detect_short_complete_answer(t):
        return False
    words = [w for w in re.split(r"\s+", t) if w]
    if len(words) < config.MIN_ANSWER_WORDS:
        return True
    trimmed = t.rstrip(".,!?…")
    if _INCOMPLETE_TRAILING.search(trimmed):
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
    progress_checks: List[dict] = field(default_factory=list)
    force_completed: bool = False

    answer_records: List[AnswerRecord] = field(default_factory=list)
    _rolling: RollingScoreTracker = field(default_factory=lambda: RollingScoreTracker(
        config.ROLLING_WINDOW
    ))
    _lock: threading.Lock = field(default_factory=threading.Lock)

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
    ) -> "InterviewOrchestrator":
        planned = QuestionSelector.select(bank, config.MAX_QUESTIONS)
        orch = cls(
            bot_id=bot_id,
            candidate_name=candidate_name.strip(),
            jd_text=jd_text.strip(),
            cv_text=cv_text.strip(),
            planned_questions=planned,
            language_mode=language_mode,
        )
        orch._log_injection()
        return orch

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
            self.awaiting_clarifier_reply = False
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

            spoken = self._ui().continue_after_clarifier
            return TurnDecision(
                action=TurnAction.SPEAK,
                spoken_text=spoken,
                should_continue=True,
                spoken_kind="prompt",
            )

    def mark_clarifier_asked(self, partial_text: str, clarifier_q: str = "") -> None:
        with self._lock:
            self.awaiting_clarifier_reply = True
            self.clarifier_count_this_question += 1
            self._last_clarifier_partial = (partial_text or "").strip()
            self._last_clarifier_question = (clarifier_q or "").strip()
            if self._last_clarifier_question:
                self.record_spoken(self._last_clarifier_question, "clarifier")
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
        """True when max clarifiers for this question have been used."""
        return self.clarifier_count_this_question >= config.BOT_INTERRUPT_MAX_CLARIFIERS_PER_Q

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
        if self.force_completed or self.drag_strikes >= config.BOT_INTERRUPT_DRAG_STRIKES_MAX:
            lines.append("Force-completed: yes (candidate went off-topic after repeated drag)")
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

            self._reset_clarifier_state()

            if not can_continue:
                return self._build_stop(
                    self._ui().closing_low_average,
                    StoppedReason.LOW_ROLLING_AVERAGE,
                    record,
                    rolling_avg,
                )

            self.current_index += 1
            next_q = self.get_current_question()

            if next_q is None:
                return self._complete_all(record, rolling_avg)

            spoken = f"Okay, thank you. Let's continue. {next_q.question}"
            if self.language_mode == "hinglish":
                return TurnDecision(
                    action=TurnAction.REPHRASE,
                    spoken_text=next_q.question,
                    score_record=record,
                    rolling_average=rolling_avg,
                    should_continue=True,
                    spoken_kind="main",
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
        self.progress_checks = []
        self.force_completed = False
        self._reset_question_meta_state()

    def _reset_question_meta_state(self) -> None:
        self.question_repeat_count = 0
        self.question_rephrase_count = 0
        self.answer_continuation_count = 0

    def try_handle_continuation_checkin(self, answer_text: str) -> Optional[TurnDecision]:
        """Respond to hello/check-in while waiting for a continued answer — do not score."""
        if self.answer_continuation_count <= 0:
            return None
        if self.phase != InterviewPhase.CORE:
            return None
        if not detect_continuation_checkin(answer_text):
            return None
        logger.info(
            "[CONTINUATION CHECKIN] bot=%s Q%d text=%r",
            self.bot_id[:8] if self.bot_id else "?",
            self.current_index + 1,
            (answer_text or "")[:80],
        )
        return TurnDecision(
            action=TurnAction.SPEAK,
            spoken_text=self._ui().please_continue_when_ready,
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
            if clarifier_count:
                logger.info(
                    "[SCORE] bot=%s Q%d scored with %d clarifier exchange(s) included",
                    self.bot_id[:8] if self.bot_id else "?",
                    self.current_index + 1,
                    clarifier_count,
                )

            # Reset clarifier state before advancing
            self._reset_clarifier_state()

            if not can_continue:
                return self._build_stop(
                    self._ui().closing_low_average,
                    StoppedReason.LOW_ROLLING_AVERAGE,
                    record,
                    rolling_avg,
                )

            self.current_index += 1
            next_q = self.get_current_question()

            if next_q is None:
                return self._complete_all(record, rolling_avg)

            spoken = f"{self._next_bridge()} {next_q.question}"
            if self.language_mode == "hinglish":
                return TurnDecision(
                    action=TurnAction.REPHRASE,
                    spoken_text=next_q.question,
                    score_record=record,
                    rolling_average=rolling_avg,
                    should_continue=True,
                    spoken_kind="main",
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


EVALUATOR_SYSTEM_PROMPT = (
    "You are an interview answer evaluator. Return ONLY valid JSON, no markdown. "
    "Score the candidate answer 0-10 for a technical screening interview. "
    "Fields: score (int 0-10), confident (bool), relevant (bool), "
    "strengths (short string), develop (area to improve), fix (actionable tip). "
    "Be fair: partial answers can be 5-7; strong specific answers 8-10; "
    "off-topic or empty 0-4. confident=false if vague, unsure, or filler-heavy. "
    "If progress_notes are present: note off-topic drift in develop/fix; "
    "score based on substantive content, not filler or repeated generalities."
)
