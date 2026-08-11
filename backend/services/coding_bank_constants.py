"""Shared DSA bank limits (org-scoped, language-agnostic problems)."""

from __future__ import annotations

from services.coding_languages import CODING_LANGUAGES

# Org-wide active problem bank
MAX_PROBLEMS_PER_ORG = 100
# Initial curated seed target
SEED_TARGET_COUNT = 90
# Each Generate click adds up to this many (or fewer if near max)
GENERATE_BATCH_SIZE = 10
# Max problems assigned to one interview
MAX_ASSIGNED_PER_INTERVIEW = 5

# Languages that get starter stubs on shared-bank problems
BANK_STARTER_LANGUAGES: tuple[str, ...] = tuple(
    lang
    for lang, meta in CODING_LANGUAGES.items()
    if meta.get("runnable")
)
