"""
Interview language profiles — English (default) and full Hinglish mode.

Selected at POST /api/join via language_mode; stored on session.state.
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
    rephrase_intro_short: str
    presence_confirm_ack: str
    intro_thanks: str
    stt_retry_prompt: str
    closing_low_average: str
    closing_completed: str
    closing_abuse: str
    abuse_warning: str
    greeting_template: str
    nudge: str
    topic_redirect: str
    presence_phrases: Tuple[str, ...]
    presence_not_audible: str
    presence_final_warning: str
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
    rephrase_intro_short="Let me ask it more simply: ",
    presence_confirm_ack="Great, please go ahead with your answer when you're ready.",
    intro_thanks="Thank you for introducing yourself, {name}. {question}",
    stt_retry_prompt="Sorry, I didn't catch that clearly. Could you please say that again?",
    closing_low_average=(
        "Thank you for sharing your answers today — we really appreciate your time. "
        "We'll wrap up the interview here. Our team will review your responses and "
        "get back to you with next steps soon. Have a great day."
    ),
    closing_completed=(
        "That brings us to the end of the interview. Thank you for your thoughtful "
        "answers today — we appreciate the time you spent with us. We'll review "
        "everything and be in touch with next steps. Take care."
    ),
    closing_abuse="I need to end our session here. Thank you for your time.",
    abuse_warning=(
        "I need us to keep this professional. Let's stay focused on the interview. {question}"
    ),
    greeting_template=(
        "Hello {name}, welcome. I'm {bot_name}, your interviewer today. "
        "Before we begin, could you please introduce yourself briefly?"
    ),
    nudge="Let's bring the focus back to the question whenever you're ready.",
    topic_redirect=(
        "Let's come back to the question — please focus your answer on what was asked."
    ),
    presence_phrases=(
        "Can you hear me clearly?",
        "Just checking — are you still there?",
        "Take your time. Can you hear me okay?",
    ),
    presence_not_audible=(
        "I'm not hearing you clearly. Are you able to speak?"
    ),
    presence_final_warning=(
        "If I don't hear from you in the next few seconds, we'll move to the next question."
    ),
    bridge_phrases=("Okay.", "So,", "Alright.", "Got it.", "Sure.", "Right."),
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
    rephrase_intro_short="Main ise thoda simple tareeke se puchta hoon: ",
    presence_confirm_ack="Theek hai, jab aap ready hon tab apna jawab dijiye.",
    intro_thanks="Intro dene ke liye dhanyavaad, {name}. {question}",
    stt_retry_prompt="Sorry, awaaz clear nahi aayi. Kya aap dobara bol sakte hain?",
    closing_low_average=(
        "Aaj ke answers share karne ke liye bahut dhanyavaad — aapka time valuable hai. "
        "Yahan interview wrap up karte hain. Team aapke responses review karke "
        "jaldi next steps ke saath contact karegi. Aapka din shubh ho."
    ),
    closing_completed=(
        "Yeh interview ka ant hai. Aapke thoughtful answers ke liye dhanyavaad — "
        "hum aapka time appreciate karte hain. Sab review karke next steps ke saath "
        "jald contact karenge. Take care."
    ),
    closing_abuse="Mujhe yahan session end karna hoga. Aaj ke liye dhanyavaad.",
    abuse_warning=(
        "Interview professional rakhna zaroori hai. Focus interview par rakhte hain. {question}"
    ),
    greeting_template=(
        "Namaste {name}, welcome. Main {bot_name} hoon, aaj aapka interviewer. "
        "Shuru karne se pehle, kripya apna brief introduction dijiye."
    ),
    nudge="Koi baat nahi — jab ready hon, sawal par wapas aate hain.",
    topic_redirect=(
        "Chaliye sawal par wapas aate hain — kripya jo pucha gaya hai usi par focus karke jawab dijiye."
    ),
    presence_phrases=(
        "Kya aap mujhe clearly sun pa rahe hain?",
        "Bas check kar raha hoon — kya aap abhi bhi hain?",
        "Apna time lijiye. Kya aap mujhe sun pa rahe hain?",
    ),
    presence_not_audible=(
        "Mujhe aapki awaaz clearly nahi aa rahi. Kya aap bol sakte hain?"
    ),
    presence_final_warning=(
        "Agar agle kuch seconds mein jawab nahi aaya, to hum agle sawal par chalenge."
    ),
    bridge_phrases=("Okay.", "So,", "Theek hai.", "Samajh gaya.", "Achha.", "Right."),
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
        whisper_fallback=config.HINGLISH_WHISPER_FALLBACK,
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
