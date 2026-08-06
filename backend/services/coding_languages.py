"""Shared coding language registry (domains, editor, runner, AI)."""

from __future__ import annotations

from typing import Any

# id -> metadata used across API, runner, and AI prompts
CODING_LANGUAGES: dict[str, dict[str, Any]] = {
    "python": {
        "label": "Python",
        "extension": "py",
        "entry": "main.py",
        "monaco": "python",
        "runnable": True,
    },
    "javascript": {
        "label": "JavaScript",
        "extension": "js",
        "entry": "main.js",
        "monaco": "javascript",
        "runnable": True,
    },
    "typescript": {
        "label": "TypeScript",
        "extension": "ts",
        "entry": "main.ts",
        "monaco": "typescript",
        "runnable": True,
    },
    "java": {
        "label": "Java",
        "extension": "java",
        "entry": "Solution.java",
        "monaco": "java",
        "runnable": True,
    },
    "cpp": {
        "label": "C++",
        "extension": "cpp",
        "entry": "main.cpp",
        "monaco": "cpp",
        "runnable": True,
    },
    "csharp": {
        "label": "C#",
        "extension": "cs",
        "entry": "Solution.cs",
        "monaco": "csharp",
        "runnable": False,
    },
    "go": {
        "label": "Go",
        "extension": "go",
        "entry": "main.go",
        "monaco": "go",
        "runnable": True,
    },
    "ruby": {
        "label": "Ruby",
        "extension": "rb",
        "entry": "main.rb",
        "monaco": "ruby",
        "runnable": True,
    },
    "php": {
        "label": "PHP",
        "extension": "php",
        "entry": "main.php",
        "monaco": "php",
        "runnable": True,
    },
    "kotlin": {
        "label": "Kotlin",
        "extension": "kt",
        "entry": "Solution.kt",
        "monaco": "kotlin",
        "runnable": False,
    },
    "rust": {
        "label": "Rust",
        "extension": "rs",
        "entry": "main.rs",
        "monaco": "rust",
        "runnable": False,
    },
    "swift": {
        "label": "Swift",
        "extension": "swift",
        "entry": "main.swift",
        "monaco": "swift",
        "runnable": False,
    },
}

SUPPORTED_LANGUAGES = frozenset(CODING_LANGUAGES.keys())


def language_label(lang: str) -> str:
    meta = CODING_LANGUAGES.get((lang or "").strip().lower())
    return meta["label"] if meta else lang


def language_entry(lang: str) -> str:
    meta = CODING_LANGUAGES.get((lang or "").strip().lower())
    return meta["entry"] if meta else "main.py"


def language_extension(lang: str) -> str:
    meta = CODING_LANGUAGES.get((lang or "").strip().lower())
    return meta["extension"] if meta else "txt"


def languages_for_api() -> list[dict[str, Any]]:
    return [
        {
            "id": key,
            "label": meta["label"],
            "extension": meta["extension"],
            "runnable": bool(meta.get("runnable")),
        }
        for key, meta in CODING_LANGUAGES.items()
    ]
