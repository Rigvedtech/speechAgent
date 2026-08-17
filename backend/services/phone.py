"""National phone length by country calling code. Keep in sync with frontend/src/lib/phone.ts."""

from __future__ import annotations

import re

# iso, name, dial (no plus), national digit length min/max
PHONE_COUNTRIES: tuple[tuple[str, str, str, int, int], ...] = (
    ("IN", "India", "91", 10, 10),
    ("US", "United States", "1", 10, 10),
    ("GB", "United Kingdom", "44", 10, 10),
    ("AE", "United Arab Emirates", "971", 9, 9),
    ("SG", "Singapore", "65", 8, 8),
    ("AU", "Australia", "61", 9, 9),
    ("DE", "Germany", "49", 10, 11),
    ("FR", "France", "33", 9, 9),
    ("SA", "Saudi Arabia", "966", 9, 9),
    ("PK", "Pakistan", "92", 10, 10),
    ("BD", "Bangladesh", "880", 10, 10),
    ("NP", "Nepal", "977", 10, 10),
    ("LK", "Sri Lanka", "94", 9, 9),
    ("MY", "Malaysia", "60", 9, 10),
    ("PH", "Philippines", "63", 10, 10),
    ("ID", "Indonesia", "62", 9, 11),
    ("NL", "Netherlands", "31", 9, 9),
    ("ZA", "South Africa", "27", 9, 9),
    ("CA", "Canada", "1", 10, 10),
)

_BY_DIAL: dict[str, list[tuple[str, str, int, int]]] = {}
for iso, name, dial, lo, hi in PHONE_COUNTRIES:
    _BY_DIAL.setdefault(dial, []).append((iso, name, lo, hi))

_DIGITS = re.compile(r"\D+")


def _digits(value: str) -> str:
    return _DIGITS.sub("", value or "")


def validate_e164_phone(raw: str) -> str:
    """Return +<dial><national> or raise ValueError with a user-facing sentence."""
    compact = (raw or "").strip().replace(" ", "")
    if not compact:
        raise ValueError("Enter your phone number.")

    if not compact.startswith("+"):
        raise ValueError("Select a country code and enter your phone number.")

    digits = _digits(compact)
    if not digits:
        raise ValueError("Enter digits only.")

    # Longest dial match (1, 44, 91, 971, …)
    match: tuple[str, str, int, int] | None = None
    matched_dial = ""
    for size in (3, 2, 1):
        prefix = digits[:size]
        options = _BY_DIAL.get(prefix)
        if options:
            match = options[0]
            matched_dial = prefix
            break
    if match is None:
        raise ValueError("Select a valid country code.")

    _iso, name, lo, hi = match
    national = digits[len(matched_dial) :]
    if national.startswith("0"):
        national = national.lstrip("0")
    if not national.isdigit() or not national:
        raise ValueError("Enter digits only.")
    n = len(national)
    if n < lo or n > hi:
        if lo == hi:
            raise ValueError(f"{name} numbers must be {lo} digits.")
        raise ValueError(f"{name} numbers must be {lo}–{hi} digits.")
    return f"+{matched_dial}{national}"
