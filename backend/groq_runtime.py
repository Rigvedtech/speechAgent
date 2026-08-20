"""Groq chat kwargs for models after the Aug 2026 Llama shutdown.

GPT-OSS / Qwen reasoning models spend completion tokens on hidden thinking.
Llama 3.1 8B / 3.3 70B did not. Without extra budget + hidden reasoning:
- JSON mode returns empty `failed_generation`
- Spoken interview lines get truncated or leak chain-of-thought into TTS
"""

from __future__ import annotations

from typing import Any, Optional


def is_gpt_oss(model: str) -> bool:
    return "gpt-oss" in (model or "").lower()


def is_qwen_reasoning(model: str) -> bool:
    m = (model or "").lower()
    return "qwen3.6" in m or m.startswith("qwen/qwen3")


def is_reasoning_model(model: str) -> bool:
    return is_gpt_oss(model) or is_qwen_reasoning(model)


def effective_max_tokens(model: str, requested: int, *, json_mode: bool) -> int:
    if not is_reasoning_model(model):
        return requested
    if json_mode:
        # Groq on-demand TPM is 8000 for gpt-oss-20b. Request size =
        # input tokens + max_tokens, so never reserve 8192 completions.
        bumped = max(requested, 1024)
        return min(bumped, 4096)
    # Live TTS / short spoken lines: keep answers short but leave room for thinking.
    return max(requested, 384)


def groq_kwargs(
    model: str,
    *,
    messages: list[dict[str, Any]],
    max_tokens: int,
    temperature: float = 0.3,
    json_mode: bool = False,
    stream: bool = False,
    timeout: Optional[float] = None,
) -> dict[str, Any]:
    """Build chat.completions.create kwargs safe for GPT-OSS replacements."""
    m = (model or "").strip()
    out: dict[str, Any] = {
        "model": m,
        "messages": messages,
        "max_tokens": effective_max_tokens(m, max_tokens, json_mode=json_mode),
        "temperature": temperature,
        "stream": stream,
    }
    if json_mode:
        out["response_format"] = {"type": "json_object"}
    if timeout is not None:
        out["timeout"] = timeout
    extra_body: dict[str, Any] = {}
    if is_gpt_oss(m):
        # reasoning_format is not supported on GPT-OSS; hide thinking instead.
        extra_body["include_reasoning"] = False
        extra_body["reasoning_effort"] = "low"
    elif is_qwen_reasoning(m):
        extra_body["reasoning_format"] = "hidden"
        extra_body["reasoning_effort"] = "none"
    if extra_body:
        out["extra_body"] = extra_body
    return out
