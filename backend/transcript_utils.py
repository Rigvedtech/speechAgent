"""
Transcript normalization helpers for voice interview STT output.
"""

from __future__ import annotations

import re
from typing import Optional


def _first_name(canonical: str) -> str:
    parts = (canonical or "").strip().split()
    return parts[0] if parts else ""


def _edit_distance(a: str, b: str) -> int:
    if len(a) < len(b):
        return _edit_distance(b, a)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        curr = [i]
        for j, cb in enumerate(b, 1):
            cost = 0 if ca == cb else 1
            curr.append(min(prev[j] + 1, curr[j - 1] + 1, prev[j - 1] + cost))
        prev = curr
    return prev[-1]


def _name_variants(first: str) -> set[str]:
    """Common ASR mishearings within edit distance 2."""
    if not first or len(first) < 2:
        return set()
    variants = {first.lower()}
    # Hand-tuned phonetic neighbors for Indian English names
    suffix_swaps = {
        "ay": ["av", "ai", "ey"],
        "av": ["ay", "ai"],
        "ai": ["ay", "av"],
        "ey": ["ay", "ee"],
    }
    lower = first.lower()
    for suffix, replacements in suffix_swaps.items():
        if lower.endswith(suffix) and len(lower) > len(suffix) + 1:
            stem = lower[: -len(suffix)]
            for rep in replacements:
                variants.add(stem + rep)
    return variants


def normalize_candidate_name(text: str, canonical: str) -> str:
    """
    Replace ASR name drift with the canonical candidate first name.
    Whole-word, case-insensitive; output uses canonical casing.
    """
    if not text or not canonical:
        return text or ""

    first = _first_name(canonical)
    if not first:
        return text

    variants = _name_variants(first)
    # Include edit-distance-1 neighbors of plausible length
    for word in re.findall(r"\b[A-Za-z]{3,20}\b", text):
        wl = word.lower()
        if wl == first.lower():
            continue
        if _edit_distance(wl, first.lower()) <= 2:
            variants.add(wl)

    if not variants:
        return text

    pattern = re.compile(
        r"\b(" + "|".join(re.escape(v) for v in sorted(variants, key=len, reverse=True)) + r")\b",
        re.IGNORECASE,
    )

    def _replace(m: re.Match) -> str:
        matched = m.group(0)
        if matched[0].isupper():
            return first[0].upper() + first[1:] if len(first) > 1 else first.upper()
        return first.lower()

    return pattern.sub(_replace, text)
