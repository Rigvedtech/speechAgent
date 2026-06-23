"""
Interview language profiles — English (default) and full Hinglish mode.

Selected at POST /api/start via language_mode; stored on session.state.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional, Tuple

import config

LanguageMode = Literal["english", "hinglish"]

VALID_LANGUAGE_MODES: Tuple[str, ...] = ("english", "hinglish")


@dataclass(frozen=True)
class SpeechProfile:
    stt_language: str
    stt_mode: str
    tts_language: str
    whisper_fallback: bool


@dataclass(frozen=True)
class UIStrings:
    please_continue: str
    please_continue_when_ready: str
    continue_after_clarifier: str
    repeat_last_clarifier: str
    repeat_intro: str
    repeat_limit: str
    rephrase_limit: str
    rephrase_prefix_main: str
    rephrase_prefix_clarifier: str
    presence_confirm_ack: str
    intro_thanks: str
    stt_retry_prompt: str
    closing_low_average: str
    closing_completed: str
    closing_abuse: str
    abuse_warning: str
    greeting_template: str
    presence_phrases: Tuple[str, ...]
    bridge_phrases: Tuple[str, ...]


@dataclass(frozen=True)
class LanguageProfile:
    mode: LanguageMode
    speech: SpeechProfile
    ui: UIStrings


_ENGLISH_UI = UIStrings(
    please_continue="Please continue your answer.",
    please_continue_when_ready="No problem. Please continue with your answer when you're ready.",
    continue_after_clarifier="Thanks for clarifying. Please continue from where you left off.",
    repeat_last_clarifier="Of course. I asked: {target}",
    repeat_intro="Sure. The question is: {question}",
    repeat_limit=(
        "I've already repeated the question a couple of times. "
        "Please try your best answer when you're ready."
    ),
    rephrase_limit=(
        "Let's stick with the question as asked. "
        "Please go ahead with your answer when you're ready."
    ),
    rephrase_prefix_main="No problem. Let me ask it more simply: ",
    rephrase_prefix_clarifier="Let me put it more simply: ",
    presence_confirm_ack="Great, please go ahead with your answer when you're ready.",
    intro_thanks="Thank you for introducing yourself, {name}. {question}",
    stt_retry_prompt="Sorry, I didn't catch that clearly. Could you please say that again?",
    closing_low_average=(
        "Thank you for your time today. We'll wrap up here. "
        "The team will be in touch with next steps."
    ),
    closing_completed=(
        "Thank you for completing the interview today. "
        "We'll review your responses and be in touch soon."
    ),
    closing_abuse="I need to end our session here. Thank you for your time.",
    abuse_warning=(
        "I need us to keep this professional. Let's stay focused on the interview. {question}"
    ),
    greeting_template=(
        "Hello {name}, welcome. I'm {bot_name}, your interviewer today. "
        "Before we begin, could you please introduce yourself briefly?"
    ),
    presence_phrases=(
        "Can you hear me clearly?",
        "Just checking — are you still there?",
        "Take your time. Can you hear me okay?",
    ),
    bridge_phrases=("Alright.", "Got it.", "Okay.", "Sure.", "Understood.", "Right."),
)

_HINGLISH_UI = UIStrings(
    please_continue="Kripya apna jawab continue kijiye.",
    please_continue_when_ready="Koi baat nahi. Jab ready hon tab apna jawab continue kijiye.",
    continue_after_clarifier="Theek hai. Jahan se chhoda tha wahan se continue kijiye.",
    repeat_last_clarifier="Bilkul. Maine pucha tha: {target}",
    repeat_intro="Bilkul. Sawal yeh hai: {question}",
    repeat_limit=(
        "Main yeh sawal do baar repeat kar chuka hoon. "
        "Jab aap ready hon tab apna best jawab dijiye."
    ),
    rephrase_limit=(
        "Chaliye sawal waise hi rakhte hain. "
        "Jab aap ready hon tab apna jawab dijiye."
    ),
    rephrase_prefix_main="Theek hai. Main ise thoda simple tareeke se puchta hoon: ",
    rephrase_prefix_clarifier="Main ise thoda simple tareeke se puchta hoon: ",
    presence_confirm_ack="Theek hai, jab aap ready hon tab apna jawab dijiye.",
    intro_thanks="Intro dene ke liye dhanyavaad, {name}. {question}",
    stt_retry_prompt="Sorry, awaaz clear nahi aayi. Kya aap dobara bol sakte hain?",
    closing_low_average=(
        "Aaj ke liye dhanyavaad. Yahan wrap up karte hain. "
        "Team aapko next steps ke saath contact karegi."
    ),
    closing_completed=(
        "Interview complete karne ke liye dhanyavaad. "
        "Hum aapke responses review karenge aur jald contact karenge."
    ),
    closing_abuse="Mujhe yahan session end karna hoga. Aaj ke liye dhanyavaad.",
    abuse_warning=(
        "Interview professional rakhna zaroori hai. Focus interview par rakhte hain. {question}"
    ),
    greeting_template=(
        "Namaste {name}, welcome. Main {bot_name} hoon, aaj aapka interviewer. "
        "Shuru karne se pehle, kripya apna brief introduction dijiye."
    ),
    presence_phrases=(
        "Kya aap mujhe clearly sun pa rahe hain?",
        "Bas check kar raha hoon — kya aap abhi bhi hain?",
        "Apna time lijiye. Kya aap mujhe sun pa rahe hain?",
    ),
    bridge_phrases=("Theek hai.", "Samajh gaya.", "Okay.", "Achha.", "Right.", "Got it."),
)


def _english_speech() -> SpeechProfile:
    return SpeechProfile(
        stt_language=config.LANG_ENGLISH_STT_LANGUAGE,
        stt_mode=config.LANG_ENGLISH_STT_MODE,
        tts_language=config.LANG_ENGLISH_TTS_LANGUAGE,
        whisper_fallback=True,
    )


def _hinglish_speech() -> SpeechProfile:
    return SpeechProfile(
        stt_language=config.LANG_HINGLISH_STT_LANGUAGE,
        stt_mode=config.LANG_HINGLISH_STT_MODE,
        tts_language=config.LANG_HINGLISH_TTS_LANGUAGE,
        whisper_fallback=False,
    )


_PROFILES = {
    "english": LanguageProfile(mode="english", speech=_english_speech(), ui=_ENGLISH_UI),
    "hinglish": LanguageProfile(mode="hinglish", speech=_hinglish_speech(), ui=_HINGLISH_UI),
}


def resolve_language_mode(raw: Optional[str]) -> LanguageMode:
    """Resolve API/env language mode; default when omitted."""
    if raw is None or not str(raw).strip():
        default = (config.DEFAULT_INTERVIEW_LANGUAGE or "english").strip().lower()
        if default not in VALID_LANGUAGE_MODES:
            return "english"
        return default  # type: ignore[return-value]
    mode = str(raw).strip().lower()
    if mode not in VALID_LANGUAGE_MODES:
        raise ValueError(
            f"Invalid language_mode {raw!r}. Allowed: {', '.join(VALID_LANGUAGE_MODES)}"
        )
    return mode  # type: ignore[return-value]


def get_profile(mode: LanguageMode) -> LanguageProfile:
    return _PROFILES.get(mode, _PROFILES["english"])


def get_ui_strings(mode: LanguageMode) -> UIStrings:
    return get_profile(mode).ui
