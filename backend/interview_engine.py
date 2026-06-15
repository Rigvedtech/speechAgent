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
    WARN_ABUSE = "warn_abuse"
    STOP = "stop"


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


def detect_abuse(text: str) -> bool:
    return bool(_ABUSE_PATTERNS.search(text or ""))


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

        for slot_diff in pattern:
            if slot_diff not in buckets:
                raise ValueError(
                    f"Question bank missing difficulty '{slot_diff}'."
                )
            picked = QuestionSelector._pop_from_bucket(
                buckets[slot_diff], source_toggle
            )
            if picked is None:
                raise ValueError(
                    f"Not enough '{slot_diff}' questions to fill "
                    f"{max_questions} planned slots."
                )
            selected.append(picked)
            source_toggle ^= 1

        return selected

    @staticmethod
    def _pop_from_bucket(
        bucket: Dict[str, Deque[BankQuestion]],
        source_toggle: int,
    ) -> Optional[BankQuestion]:
        order = ("jd", "resume", "other") if source_toggle % 2 == 0 else (
            "resume", "jd", "other"
        )
        for src in order:
            if bucket[src]:
                return bucket[src].popleft()
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

    phase: InterviewPhase = InterviewPhase.GREETING
    current_index: int = 0
    abuse_warnings: int = 0
    stopped_reason: StoppedReason = StoppedReason.NONE

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
    ) -> "InterviewOrchestrator":
        planned = QuestionSelector.select(bank, config.MAX_QUESTIONS)
        orch = cls(
            bot_id=bot_id,
            candidate_name=candidate_name.strip(),
            jd_text=jd_text.strip(),
            cv_text=cv_text.strip(),
            planned_questions=planned,
        )
        orch._log_injection()
        return orch

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
            spoken = (
                f"Thank you for introducing yourself, {self.candidate_name}. "
                f"{q.question}"
            )
            logger.info(
                "[INTERVIEW PHASE] bot=%s → core | asking Q1/%d id=%s",
                self.bot_id[:8] if self.bot_id else "?",
                len(self.planned_questions),
                q.id,
            )
            return TurnDecision(action=TurnAction.SPEAK, spoken_text=spoken)

    def process_answer(
        self,
        answer_text: str,
        evaluation: EvaluationResult,
    ) -> TurnDecision:
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

            if not can_continue:
                return self._build_stop(
                    "Thank you for your time today. We'll wrap up here. "
                    "The team will be in touch with next steps.",
                    StoppedReason.LOW_ROLLING_AVERAGE,
                    record,
                    rolling_avg,
                )

            self.current_index += 1
            next_q = self.get_current_question()

            if next_q is None:
                return self._complete_all(record, rolling_avg)

            spoken = f"Thank you. {next_q.question}"
            return TurnDecision(
                action=TurnAction.SPEAK,
                spoken_text=spoken,
                score_record=record,
                rolling_average=rolling_avg,
                should_continue=True,
            )

    def _handle_abuse(self) -> TurnDecision:
        q = self.get_current_question()
        if not q:
            return self._build_stop(
                "I need to end our session here. Thank you for your time.",
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
            spoken = (
                "I need us to keep this professional. Let's stay focused on the interview. "
                f"{q.question}"
            )
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
            "I need to end our session here. Thank you for your time.",
            StoppedReason.ABUSE,
        )

    def _complete_all(
        self,
        last_record: Optional[AnswerRecord] = None,
        rolling_avg: Optional[float] = None,
    ) -> TurnDecision:
        self.phase = InterviewPhase.CLOSING
        self.stopped_reason = StoppedReason.COMPLETED
        spoken = (
            "Thank you for completing the interview today. "
            "We'll review your responses and be in touch soon."
        )
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

            return {
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

    def evaluator_context(self, question: BankQuestion) -> str:
        return (
            f"Question ({question.normalized_difficulty}, {question.source}): "
            f"{question.question}\n\n"
            f"JD excerpt (for relevance):\n{self.jd_text[:1200]}\n\n"
            f"Resume excerpt (for relevance):\n{self.cv_text[:1200]}"
        )


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
    "off-topic or empty 0-4. confident=false if vague, unsure, or filler-heavy."
)
