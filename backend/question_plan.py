"""Resolve interview question counts from env (MAX_QUESTIONS + difficulty buckets).

Generation and QuestionSelector share the same plan so Groq JSON shape and
live asking stay in sync.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

_ASK_CYCLE = ("Low", "Hard", "Intermediate")


@dataclass(frozen=True)
class QuestionPlan:
    total: int
    beginner: int
    intermediate: int
    hard: int
    adjusted: bool
    difficulty_pattern: tuple[str, ...]

    @property
    def jd_count(self) -> int:
        return self.beginner + self.intermediate

    @property
    def resume_count(self) -> int:
        return self.hard

    def id_range(self, kind: str) -> tuple[int, int]:
        """Inclusive 1-based id range. (0, 0) if that bucket is empty."""
        if kind == "beginner":
            n, start = self.beginner, 1
        elif kind == "intermediate":
            n, start = self.intermediate, self.beginner + 1
        elif kind == "hard":
            n, start = self.hard, self.beginner + self.intermediate + 1
        else:
            raise ValueError(kind)
        if n <= 0:
            return (0, 0)
        return (start, start + n - 1)


def resolve_question_plan(
    max_questions: int,
    beginner: int,
    intermediate: int,
    hard: int,
    *,
    min_total: int = 3,
) -> QuestionPlan:
    """Fit beginner/intermediate/hard into MAX_QUESTIONS.

    If the three counts already sum to max_questions, use them as-is (then
    enforce min-1 per bucket when total >= 3). Otherwise scale by ratio and
    put leftover on intermediate.
    """
    total = max(int(max_questions or 0), min_total)
    raw_b = max(int(beginner or 0), 0)
    raw_i = max(int(intermediate or 0), 0)
    raw_h = max(int(hard or 0), 0)
    raw_sum = raw_b + raw_i + raw_h
    if raw_sum <= 0:
        raw_b, raw_i, raw_h = 5, 5, 5
        raw_sum = 15

    adjusted = raw_sum != total
    if adjusted:
        b, i, h = _largest_remainder(raw_b, raw_i, raw_h, total)
        logger.info(
            "[QUESTION-PLAN] counts %s+%s+%s=%s != MAX_QUESTIONS=%s → %s+%s+%s",
            raw_b,
            raw_i,
            raw_h,
            raw_sum,
            total,
            b,
            i,
            h,
        )
    else:
        b, i, h = raw_b, raw_i, raw_h

    b, i, h = _ensure_min_buckets(b, i, h, total)
    b, i, h = _force_sum(b, i, h, total)
    if (b, i, h) != (raw_b, raw_i, raw_h):
        adjusted = True

    pattern = _ask_pattern(b, i, h)
    if len(pattern) != total:
        raise RuntimeError(
            f"question plan pattern length {len(pattern)} != total {total}"
        )
    return QuestionPlan(
        total=total,
        beginner=b,
        intermediate=i,
        hard=h,
        adjusted=adjusted,
        difficulty_pattern=pattern,
    )


def _largest_remainder(b: int, i: int, h: int, total: int) -> tuple[int, int, int]:
    s = b + i + h
    weights = (b, i, h)
    exact = [w * total / s for w in weights]
    floors = [int(x) for x in exact]
    rem = total - sum(floors)
    order = sorted(range(3), key=lambda k: (exact[k] - floors[k], k), reverse=True)
    idx = 0
    while rem > 0 and order:
        floors[order[idx % 3]] += 1
        rem -= 1
        idx += 1
    while sum(floors) > total:
        k = max(range(3), key=lambda idx: floors[idx])
        if floors[k] <= 0:
            break
        floors[k] -= 1
    return floors[0], floors[1], floors[2]


def _ensure_min_buckets(b: int, i: int, h: int, total: int) -> tuple[int, int, int]:
    if total < 3:
        return b, i, h
    counts = [b, i, h]
    for idx in range(3):
        if counts[idx] < 1:
            donor = max(range(3), key=lambda k: counts[k] if k != idx else -1)
            if counts[donor] > 1:
                counts[donor] -= 1
                counts[idx] = 1
    return counts[0], counts[1], counts[2]


def _force_sum(b: int, i: int, h: int, total: int) -> tuple[int, int, int]:
    counts = [b, i, h]
    while sum(counts) < total:
        counts[1] += 1
    while sum(counts) > total:
        donor = max(range(3), key=lambda k: counts[k])
        if counts[donor] <= (1 if total >= 3 else 0):
            break
        counts[donor] -= 1
    return counts[0], counts[1], counts[2]


def _ask_pattern(b: int, i: int, h: int) -> tuple[str, ...]:
    left = {"Low": b, "Hard": h, "Intermediate": i}
    out: list[str] = []
    while any(v > 0 for v in left.values()):
        stepped = False
        for diff in _ASK_CYCLE:
            if left[diff] > 0:
                out.append(diff)
                left[diff] -= 1
                stepped = True
        if not stepped:
            break
    return tuple(out)


def format_id_span(start: int, end: int) -> str:
    if start <= 0 or end <= 0:
        return ""
    if start == end:
        return f"Question {start}"
    return f"Questions {start}-{end}"
