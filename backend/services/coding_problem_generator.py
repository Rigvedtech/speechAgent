"""AI coding-problem generator — one Groq call + local verification.

Flow (rate-limit friendly):
1) Single Groq JSON draft
2) Lenient normalize / fill missing pieces locally
3) Run Python reference on examples and lock expected outputs
4) For swap-to-sort problems, use a canonical local reference
"""

from __future__ import annotations

import json
import logging
import random
import re
from typing import Any, Optional

from services.coding_languages import language_label
from groq_runtime import groq_kwargs

logger = logging.getLogger(__name__)

# Legacy name — org shared bank cap lives in coding_bank_constants.
MAX_PROBLEMS_PER_DOMAIN = 100
# Each attempt = exactly one Groq call (no dual-verify/rewrite), so a few
# retries here is cheap and mostly protects against local-verify rejections
# (buggy reference code), not Groq rate limits.
_MAX_GENERATE_ATTEMPTS = 4

_TOPIC_BANK = [
    "hash map / frequency counting",
    "two pointers on a sorted array",
    "sliding window (variable size)",
    "stack (next greater / valid parentheses style)",
    "prefix sums",
    "string parsing or anagrams",
    "binary search on answer or on sorted array",
    "greedy with sorting",
    "simple BFS on a grid or graph",
    "simple DFS / recursion on a tree-like structure",
    "queue / monotonic queue lite",
    "bit manipulation basics",
    "interval merge or meeting-rooms style",
    "matrix traversal",
    "linked-list simulation with arrays",
]

_FN_STYLE = {
    "python": "snake_case Python function (e.g. two_sum)",
    "javascript": "camelCase JavaScript function (e.g. twoSum)",
    "typescript": "camelCase TypeScript function (e.g. twoSum)",
    "java": "camelCase Java method inside class Solution (e.g. twoSum)",
    "cpp": "snake_case or camelCase C++ free function (e.g. twoSum)",
    "csharp": "PascalCase C# method inside class Solution (e.g. TwoSum)",
    "go": "PascalCase Go function (e.g. TwoSum)",
    "ruby": "snake_case Ruby method (e.g. two_sum)",
    "php": "camelCase PHP function (e.g. twoSum)",
    "kotlin": "camelCase Kotlin function (e.g. twoSum)",
    "rust": "snake_case Rust function (e.g. two_sum)",
    "swift": "camelCase Swift function (e.g. twoSum)",
}


def _title_key(title: str) -> str:
    text = (title or "").strip().lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _pick_forced_topic(
    *,
    existing_titles: list[str],
    existing_tags: list[str],
    attempt: int,
) -> str:
    """Rotate a concrete topic so repeated Generate clicks don't collapse to one idea."""
    used = " ".join(existing_titles + existing_tags).lower()
    ranked = sorted(
        _TOPIC_BANK,
        key=lambda t: sum(1 for w in t.replace("/", " ").split() if w and w in used),
    )
    # Prefer unused topics; shuffle the least-used bucket for variety
    least = ranked[: max(3, len(ranked) // 2)]
    random.shuffle(least)
    return least[(attempt - 1) % len(least)]


def generate_dsa_problem(
    *,
    language: str,
    domain_name: str,
    existing_titles: list[str],
    existing_tags: Optional[list[str]] = None,
) -> Optional[dict[str, Any]]:
    """Generate one DSA problem with a single Groq call + local verify."""
    try:
        import config as app_config
        from groq import Groq
    except Exception as exc:  # noqa: BLE001
        logger.warning("[coding_gen] Groq import failed: %s", exc)
        return None

    api_key = getattr(app_config, "GROQ_API_KEY", "")
    if not api_key:
        logger.warning("[coding_gen] GROQ_API_KEY missing")
        return None

    model = getattr(app_config, "GROQ_EVALUATOR_MODEL", "openai/gpt-oss-20b")
    lang = (language or "python").strip().lower()
    label = language_label(lang)
    fn_style = _FN_STYLE.get(lang, f"idiomatic {label} function name")
    tags = [str(t) for t in (existing_tags or []) if str(t).strip()]
    blocked = {_title_key(t) for t in existing_titles if _title_key(t)}
    avoid = ", ".join(existing_titles[:20]) or "(none)"

    client = Groq(api_key=api_key)
    last_err = ""
    for attempt in range(1, _MAX_GENERATE_ATTEMPTS + 1):
        topic = _pick_forced_topic(
            existing_titles=existing_titles,
            existing_tags=tags,
            attempt=attempt,
        )
        prompt = f"""Create ONE original easy/medium DSA interview problem for "{domain_name}" ({label}).
Solvable in 20–30 minutes.

HARD uniqueness rules:
- Do NOT reuse or lightly rename any of these existing titles: {avoid}
- Title must be clearly different from every title above (new idea, not "Second Maximum Product" variants)
- REQUIRED primary technique for this problem: {topic}
- Do not generate product-of-array / max-product style problems if any existing title mentions product

Allowed topics (must center on the required technique above): arrays, hashing, two pointers,
sliding window, strings, stack, prefix sums, sorting, min-swaps (only with clear swap_mode),
simple BFS/DFS, binary search, intervals, matrix.

If swaps-to-sort: set swap_mode to "adjacent" (inversions) OR "any" (cycles). Never leave it ambiguous.
Otherwise swap_mode = null.

Return STRICT JSON only with keys:
title, difficulty ("easy"|"medium"), statement,
entry_function ({fn_style}),
swap_mode ("adjacent"|"any"|null),
constraints_text, skill_tags (1-4 strings),
examples (exactly 2 objects: input, output, explanation as Python-literal strings),
starter_code ({label} stub matching entry_function — use a normal JSON string with \\n, NEVER triple quotes),
reference_solution (Python 3; MUST be `def solution(data):` where `data` is a single dict argument
whose keys are EXACTLY the same field names used inside each example's `input` JSON object —
read fields as data["field_name"], do not declare separate positional parameters;
use a normal JSON string with \\n, NEVER \"\"\" triple quotes),
estimated_minutes (integer 15-60; realistic time for a mid-level engineer to solve this)

Critical JSON rules:
- Valid JSON only (no Python triple-quoted strings)
- Escape newlines in code as \\n
- Escape quotes inside strings

Critical correctness rules:
- REQUIRED: non-empty reference_solution key (Python). Omitting it makes the JSON invalid.
- reference_solution's parameter names/keys MUST match the example input JSON keys exactly
- Examples must be correct for the statement — recompute them yourself before writing them
- Never write a reference_solution that just returns its input unchanged
- starter_code is {label}; reference_solution is ALWAYS Python — never omit it for non-Python domains

No markdown.
"""

        data: Optional[dict[str, Any]] = None
        try:
            resp = client.chat.completions.create(
                **groq_kwargs(
                    model,
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                "You generate one clear DSA interview problem as STRICT valid JSON. "
                                "Never repeat an existing title. Never use Python triple-quoted strings. "
                                "Put code in JSON strings with \\n escapes. "
                                "You MUST always include a non-empty reference_solution string key — "
                                "never omit it. reference_solution must be Python "
                                "`def solution(data):` (or a Python def matching entry_function) "
                                "reading fields via data['key'] using the exact same keys as the "
                                "example input JSON objects — never JS/Java/C++, never separate "
                                "positional params, never an identity/no-op return. "
                                "Include exactly 2 correct examples."
                            ),
                        },
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.55,
                    max_tokens=2000,
                    timeout=60,
                    json_mode=True,
                )
            )
            raw = resp.choices[0].message.content or ""
            data = _loads_problem_json(raw)
        except Exception as exc:  # noqa: BLE001
            last_err = str(exc)
            logger.warning("[coding_gen] generate failed attempt=%s: %s", attempt, exc)
            # Salvage almost-valid JSON from Groq json_validate_failed payloads
            salvaged = _extract_failed_generation(exc)
            if salvaged:
                data = salvaged
                logger.info("[coding_gen] salvaged failed_generation on attempt=%s", attempt)
            elif _is_rate_limited(last_err):
                break
            else:
                continue

        if not data:
            continue

        # Model often omits reference_solution on non-Python domains — fill it.
        if not _reference_text(data):
            filled = _fill_missing_reference_solution(client, model, data)
            if filled:
                data["reference_solution"] = filled
                logger.info(
                    "[coding_gen] filled missing reference_solution attempt=%s",
                    attempt,
                )

        normalized, reason = _normalize_problem(data, language=lang)
        if not normalized:
            last_err = reason
            logger.warning(
                "[coding_gen] normalize failed attempt=%s reason=%s",
                attempt,
                reason,
            )
            continue

        key = _title_key(str(normalized.get("title") or ""))
        if key and key in blocked:
            last_err = "duplicate_title"
            logger.warning(
                "[coding_gen] duplicate title rejected attempt=%s title=%r topic=%r",
                attempt,
                normalized.get("title"),
                topic,
            )
            continue

        verified = _finalize_local(normalized)
        if verified:
            logger.info(
                "[coding_gen] accepted attempt=%s title=%r topic=%r",
                attempt,
                verified.get("title"),
                topic,
            )
            verified.pop("swap_mode", None)
            verified.pop("reference_solution", None)
            return verified

        last_err = "local_verify_failed"
        logger.warning(
            "[coding_gen] local verify failed attempt=%s title=%s",
            attempt,
            normalized.get("title"),
        )

    logger.warning("[coding_gen] giving up last_err=%s", last_err[:300])
    return None


def _is_rate_limited(message: str) -> bool:
    text = (message or "").lower()
    return "429" in text or "too many requests" in text or "rate_limit" in text


def _reference_text(data: dict[str, Any]) -> str:
    return str(
        data.get("reference_solution")
        or data.get("solution")
        or data.get("python_solution")
        or ""
    ).strip()


def _fill_missing_reference_solution(
    client: Any,
    model: str,
    draft: dict[str, Any],
) -> Optional[str]:
    """Ask Groq for only the missing Python reference when the draft omitted it."""
    title = str(draft.get("title") or "").strip()
    statement = str(draft.get("statement") or draft.get("description") or "").strip()
    entry = str(
        draft.get("entry_function") or draft.get("function_name") or "solution"
    ).strip() or "solution"
    examples = draft.get("examples") or draft.get("sample_cases") or []
    if not title or not statement or not examples:
        return None

    try:
        examples_json = json.dumps(examples[:2], ensure_ascii=False)[:1200]
    except Exception:
        examples_json = str(examples)[:1200]

    prompt = f"""The problem draft below is missing reference_solution.
Return STRICT JSON with exactly one key: reference_solution (Python 3 string).

Rules:
- Must define `def solution(data):` OR `def {entry}(...):` in Python
- Read example input fields via data["key"] using the SAME keys as the example input objects
- Correct for the examples; never return the input unchanged
- Use \\n escapes; no markdown; no triple quotes

title: {title}
entry_function: {entry}
statement:
{statement[:900]}

examples:
{examples_json}
"""
    try:
        resp = client.chat.completions.create(
            **groq_kwargs(
                model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You only write a Python reference_solution for an existing DSA "
                            "problem draft. Return JSON {\"reference_solution\": \"...\"}."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.2,
                max_tokens=900,
                timeout=45,
                json_mode=True,
            )
        )
        raw = resp.choices[0].message.content or ""
        parsed = _loads_problem_json(raw)
        code = _reference_text(parsed)
        if code and re.search(r"^\s*def\s+\w+\s*\(", code, flags=re.M):
            return code
    except Exception as exc:  # noqa: BLE001
        logger.warning("[coding_gen] fill reference_solution failed: %s", exc)
    return None


def _loads_problem_json(raw: str) -> dict[str, Any]:
    text = _strip_fences(raw)
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    repaired = _repair_jsonish(text)
    data = json.loads(repaired)
    if not isinstance(data, dict):
        raise ValueError("parsed JSON is not an object")
    return data


def _unescape_codeish(content: str) -> str:
    """Turn JSON-style escapes inside triple-quoted LLM code into real characters."""
    text = content or ""
    # Already real newlines → leave alone (except keep common JSON escapes if mixed)
    if "\\n" not in text and "\\t" not in text:
        return text
    return (
        text.replace("\\\\", "\0")
        .replace("\\n", "\n")
        .replace("\\t", "\t")
        .replace('\\"', '"')
        .replace("\\'", "'")
        .replace("\0", "\\")
    )


def _repair_jsonish(text: str) -> str:
    """Convert common LLM mistakes (triple-quoted code blocks) into valid JSON strings."""

    def _repl(match: re.Match[str]) -> str:
        return json.dumps(_unescape_codeish(match.group(1)))

    # """..."""  or '''...'''
    out = re.sub(r'"""([\s\S]*?)"""', _repl, text)
    out = re.sub(r"'''([\s\S]*?)'''", _repl, out)
    return out


def _extract_failed_generation(exc: Exception) -> Optional[dict[str, Any]]:
    """Groq sometimes returns the draft in error.failed_generation — salvage it."""
    import ast

    failed = None
    body = getattr(exc, "body", None)
    if isinstance(body, dict):
        err = body.get("error") if isinstance(body.get("error"), dict) else body
        if isinstance(err, dict):
            failed = err.get("failed_generation")

    if failed is None:
        msg = str(exc)
        if "failed_generation" not in msg:
            return None
        # Typical: Error code: 400 - {'error': {... 'failed_generation': '...'}}
        dash = msg.find(" - ")
        if dash >= 0:
            tail = msg[dash + 3 :].strip()
            try:
                parsed = ast.literal_eval(tail)
                if isinstance(parsed, dict):
                    err = parsed.get("error") if isinstance(parsed.get("error"), dict) else parsed
                    if isinstance(err, dict):
                        failed = err.get("failed_generation")
            except Exception:
                failed = None

    if not failed:
        return None
    try:
        return _loads_problem_json(str(failed))
    except Exception as salvage_exc:  # noqa: BLE001
        logger.warning("[coding_gen] salvage parse failed: %s", salvage_exc)
        return None


def _finalize_local(problem: dict[str, Any]) -> Optional[dict[str, Any]]:
    """Verify / align examples using local Python only (no extra Groq calls)."""
    mode = _detect_swap_mode(problem)
    draft = dict(problem)
    if mode:
        draft["swap_mode"] = mode
        draft["reference_solution"] = _canonical_min_swaps_reference(mode)
        draft["statement"] = _canonical_swap_statement(mode)

    locked = _align_to_reference(draft)
    if not locked:
        # If LLM reference fails, try a tiny fallback only for non-swap
        if mode:
            return None
        return None

    # Ensure explanations exist
    examples = []
    for ex in locked["examples"]:
        explanation = ex.get("explanation") or (
            f"For input {ex['input']}, the correct return value is {ex['output']}."
        )
        examples.append({**ex, "explanation": explanation})
    locked["examples"] = examples

    lang = str(locked.get("language") or "python")
    entry = str(locked.get("entry_function") or "solution")
    starter = str(locked.get("starter_code") or "").strip()
    if not starter or entry not in starter:
        locked["starter_code"] = _default_starter(lang, entry)
    return locked


def _strip_fences(content: str) -> str:
    text = (content or "").strip()
    text = re.sub(r"^```(?:json|python)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _default_starter(language: str, entry: str) -> str:
    if language == "javascript":
        return f"function {entry}(/* args */) {{\n  // write your solution\n}}\n"
    if language == "typescript":
        return f"function {entry}(/* args */): unknown {{\n  // write your solution\n  return null;\n}}\n"
    if language == "java":
        return (
            "class Solution {\n"
            f"    public Object {entry}(Object input) {{\n"
            "        // write your solution\n"
            "        return null;\n"
            "    }\n"
            "}\n"
        )
    if language == "cpp":
        return (
            "#include <bits/stdc++.h>\nusing namespace std;\n\n"
            f"auto {entry}(auto input) {{\n"
            "    // write your solution\n"
            "    return input;\n"
            "}\n"
        )
    if language == "csharp":
        return (
            "public class Solution {\n"
            f"    public object {entry}(object input) {{\n"
            "        // write your solution\n"
            "        return null;\n"
            "    }\n"
            "}\n"
        )
    if language == "go":
        return (
            "package main\n\n"
            f"func {entry}(input interface{{}}) interface{{}} {{\n"
            "\t// write your solution\n"
            "\treturn nil\n"
            "}\n"
        )
    if language == "ruby":
        return f"def {entry}(input)\n  # write your solution\n  nil\nend\n"
    if language == "php":
        return f"<?php\nfunction {entry}($input) {{\n  // write your solution\n  return null;\n}}\n"
    if language == "kotlin":
        return f"fun {entry}(input: Any?): Any? {{\n    // write your solution\n    return null\n}}\n"
    if language == "rust":
        return f"fn {entry}(input: String) -> String {{\n    // write your solution\n    input\n}}\n"
    if language == "swift":
        return f"func {entry}(_ input: Any) -> Any {{\n    // write your solution\n    return input\n}}\n"
    return (
        f"def {entry}(data):\n"
        "    \"\"\"Return the answer for the given input (see Examples).\"\"\"\n"
        "    # write your solution\n"
        "    pass\n"
    )


def _coerce_examples(raw: Any) -> list[dict[str, str]]:
    examples: list[dict[str, str]] = []
    if not isinstance(raw, list):
        return examples
    for item in raw[:4]:
        if isinstance(item, dict):
            inp = item.get("input", item.get("Input", ""))
            out = item.get("output", item.get("Output", item.get("expected", "")))
            exp = item.get("explanation", item.get("Explanation", ""))
            # Sometimes models nest values
            if isinstance(inp, (dict, list)):
                inp = json.dumps(inp)
            if isinstance(out, (dict, list, int, float, bool)) or out is None:
                out = json.dumps(out)
            examples.append(
                {
                    "input": str(inp).strip(),
                    "output": str(out).strip(),
                    "explanation": str(exp or "").strip(),
                }
            )
    # Drop empties
    examples = [e for e in examples if e["input"]]
    return examples


def _find_any_top_level_def(code: str) -> Optional[str]:
    """Best-effort fallback: find any function name defined in the code."""
    for m in re.finditer(r"^\s*def\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\(", code, flags=re.M):
        name = m.group(1)
        if name != "solution":
            return name
    return None


def _ensure_solution_fn(reference: str, entry: str) -> str:
    """Wrap the model's entry function as solution(data).

    IMPORTANT: never fabricate a fake `return data` identity stub — that would
    silently "pass" local verification while echoing the input back as the
    answer. If no real function can be found to wrap, return the code
    unchanged so normalize/verify fails loudly and the caller retries.
    """
    code = (reference or "").strip()
    if not code:
        return code
    if re.search(r"^\s*def\s+solution\s*\(", code, flags=re.M):
        return code

    target = entry if entry and re.search(rf"def\s+{re.escape(entry)}\s*\(", code) else None
    if not target:
        target = _find_any_top_level_def(code)
    if not target:
        # No usable function at all — leave as-is; downstream check will reject it.
        return code

    return code + "\n\n" + _SOLUTION_WRAPPER_TEMPLATE.format(target=target)


# Signature-aware calling wrapper: instead of blindly guessing **data vs *vals
# (which throws TypeError whenever the model's parameter names/order don't
# exactly match the example JSON keys — the #1 cause of local-verify failures),
# introspect the target function's real parameters and bind by name first,
# falling back through progressively looser strategies. Every strategy is
# tried in order; only if ALL of them fail do we let the last error propagate
# (so genuinely broken reference code still fails verification correctly).
_SOLUTION_WRAPPER_TEMPLATE = '''def solution(data):
    import inspect as __inspect
    _fn = {target}
    _last_exc = None
    try:
        _params = list(__inspect.signature(_fn).parameters.keys())
    except (TypeError, ValueError):
        _params = []

    if isinstance(data, dict):
        if _params and all(p in data for p in _params):
            try:
                return _fn(**{{p: data[p] for p in _params}})
            except TypeError as exc:
                _last_exc = exc
        try:
            return _fn(**data)
        except TypeError as exc:
            _last_exc = exc
        try:
            return _fn(*list(data.values()))
        except TypeError as exc:
            _last_exc = exc
        try:
            return _fn(data)
        except TypeError as exc:
            _last_exc = exc
        raise _last_exc
    if isinstance(data, (list, tuple)):
        try:
            return _fn(*data)
        except TypeError as exc:
            _last_exc = exc
        try:
            return _fn(data)
        except TypeError as exc:
            raise exc from _last_exc
    return _fn(data)
'''


def _normalize_problem(
    data: dict[str, Any], *, language: str
) -> tuple[Optional[dict[str, Any]], str]:
    if not isinstance(data, dict):
        return None, "not_a_dict"

    title = str(data.get("title") or data.get("name") or "").strip()
    statement = str(data.get("statement") or data.get("description") or "").strip()
    entry = str(
        data.get("entry_function")
        or data.get("function_name")
        or data.get("entry")
        or "solution"
    ).strip()
    if len(title) < 3:
        return None, "title_too_short"
    if len(statement) < 12:
        return None, "statement_too_short"
    if len(entry) < 2:
        entry = "solution"

    difficulty = str(data.get("difficulty") or "medium").strip().lower()
    if difficulty not in {"easy", "medium", "hard"}:
        difficulty = "medium"

    examples = _coerce_examples(data.get("examples") or data.get("sample_cases"))
    if len(examples) == 1:
        # Duplicate as edge placeholder with same I/O is bad; keep one and synthesize sorted-style edge if list
        examples.append(
            {
                "input": examples[0]["input"],
                "output": examples[0]["output"],
                "explanation": "Same as example 1 (model returned only one example).",
            }
        )
    if len(examples) < 1:
        return None, "no_examples"
    # Prefer 2
    examples = examples[:2]
    if any(not ex["input"] for ex in examples):
        return None, "empty_example_input"

    tags_raw = data.get("skill_tags") or data.get("tags") or []
    tags = [str(t).strip() for t in tags_raw if str(t).strip()][:6]

    starter = str(data.get("starter_code") or data.get("starter") or "").strip()
    if not starter or (entry and entry not in starter and language == "python"):
        starter = _default_starter(language, entry)

    reference = str(
        data.get("reference_solution")
        or data.get("solution")
        or data.get("python_solution")
        or ""
    ).strip()
    reference = _ensure_solution_fn(reference, entry)
    if "def solution" not in reference:
        return None, "missing_def_solution"

    swap_raw = data.get("swap_mode")
    swap_mode = None
    if swap_raw is not None and str(swap_raw).strip().lower() not in {"", "null", "none"}:
        sm = str(swap_raw).strip().lower()
        if sm in {"adjacent", "any"}:
            swap_mode = sm

    estimated = _clamp_minutes(
        data.get("estimated_minutes")
        or data.get("estimated_time_min")
        or data.get("time_limit_min"),
        difficulty,
    )

    return {
        "title": title[:255],
        "difficulty": difficulty,
        "statement": statement,
        "entry_function": entry[:64],
        "constraints_text": str(data.get("constraints_text") or data.get("constraints") or "").strip(),
        "skill_tags": tags,
        "examples": examples,
        "starter_code": starter,
        "language": language,
        "reference_solution": reference,
        "swap_mode": swap_mode,
        "estimated_minutes": estimated,
    }, ""


def _clamp_minutes(raw: Any, difficulty: str = "medium") -> int:
    defaults = {"easy": 15, "hard": 45}
    fallback = defaults.get((difficulty or "medium").strip().lower(), 25)
    try:
        minutes = int(raw)
    except (TypeError, ValueError):
        minutes = fallback
    return max(5, min(180, minutes))


def _problem_text(problem: dict[str, Any]) -> str:
    return " ".join(
        [
            str(problem.get("title") or ""),
            str(problem.get("statement") or ""),
            " ".join(str(t) for t in (problem.get("skill_tags") or [])),
            str(problem.get("entry_function") or ""),
        ]
    ).lower()


def _detect_swap_mode(problem: dict[str, Any]) -> Optional[str]:
    raw = str(problem.get("swap_mode") or "").strip().lower()
    if raw in {"adjacent", "any"}:
        return raw
    text = _problem_text(problem)
    if any(
        k in text
        for k in (
            "adjacent swap",
            "adjacent swaps",
            "only adjacent",
            "inversion",
            "inversions",
            "bubble sort",
        )
    ):
        return "adjacent"
    if any(
        k in text
        for k in (
            "any two",
            "any elements",
            "any indices",
            "any index",
            "not necessarily adjacent",
            "swap any",
            "cycle decomposition",
            "number of cycles",
        )
    ):
        return "any"
    # Generic min-swaps without qualifier → default to adjacent (clearer for interviews)
    if any(
        k in text
        for k in ("minimum swap", "min swap", "swaps to sort", "swap to sort")
    ):
        return "adjacent"
    return None


def _canonical_swap_statement(mode: str) -> str:
    if mode == "adjacent":
        return (
            "Given an array of distinct integers, return the minimum number of "
            "adjacent swaps required to sort the array in ascending order. "
            "An adjacent swap exchanges two neighboring elements. "
            "This value equals the number of inversions in the array. "
            "Input is the array (or an object containing the array). Return an integer."
        )
    return (
        "Given an array of distinct integers, return the minimum number of swaps "
        "required to sort the array in ascending order, where you may swap any two "
        "elements (not only adjacent ones). "
        "This equals n minus the number of cycles in the position permutation. "
        "Input is the array (or an object containing the array). Return an integer."
    )


def _canonical_min_swaps_reference(mode: str) -> str:
    if mode == "adjacent":
        return '''
def solution(data):
    if isinstance(data, dict):
        arr = list(data.get("arr") or data.get("nums") or data.get("array") or next(iter(data.values())))
    else:
        arr = list(data)
    vals = sorted(set(arr))
    rank = {v: i + 1 for i, v in enumerate(vals)}
    bit = [0] * (len(vals) + 2)

    def update(i):
        while i < len(bit):
            bit[i] += 1
            i += i & -i

    def query(i):
        s = 0
        while i > 0:
            s += bit[i]
            i -= i & -i
        return s

    inv = 0
    for x in reversed(arr):
        r = rank[x]
        inv += query(r - 1)
        update(r)
    return inv
'''.strip()

    return '''
def solution(data):
    if isinstance(data, dict):
        arr = list(data.get("arr") or data.get("nums") or data.get("array") or next(iter(data.values())))
    else:
        arr = list(data)
    n = len(arr)
    pos = list(enumerate(arr))
    pos.sort(key=lambda x: x[1])
    visited = [False] * n
    swaps = 0
    for i in range(n):
        if visited[i] or pos[i][0] == i:
            continue
        cycle = 0
        j = i
        while not visited[j]:
            visited[j] = True
            j = pos[j][0]
            cycle += 1
        if cycle > 0:
            swaps += cycle - 1
    return swaps
'''.strip()


def _normalize_output(value: str) -> str:
    text = (value or "").strip()
    try:
        return json.dumps(json.loads(text), sort_keys=True, separators=(",", ":"))
    except Exception:
        cleaned = (
            text.replace("True", "true")
            .replace("False", "false")
            .replace("None", "null")
        )
        try:
            return json.dumps(json.loads(cleaned), sort_keys=True, separators=(",", ":"))
        except Exception:
            return " ".join(text.split())


def _is_identity_echo(examples: list[dict[str, str]], outputs: list[str]) -> bool:
    """Detect a broken/no-op reference that just echoes the input back as the answer.

    This is the exact bug behind "Required Return" showing the raw input JSON:
    the reference ran without error, so verify "passed", but the function never
    actually computed anything.
    """
    if not outputs:
        return False
    for ex, out in zip(examples, outputs):
        inp_norm = _normalize_output(str(ex.get("input") or ""))
        out_norm = _normalize_output(str(out or ""))
        if not inp_norm or inp_norm != out_norm:
            return False
    return True


def _run_reference_outputs(
    reference: str,
    examples: list[dict[str, str]],
) -> Optional[list[str]]:
    from services.coding_runner import run_examples

    if not reference.strip() or "def solution" not in reference:
        return None

    report = run_examples(
        language="python",
        code=reference,
        examples=examples,
        entry_function="solution",
        timeout_sec=5.0,
    )
    rows = report.get("results") or []
    if len(rows) != len(examples):
        return None

    outputs: list[str] = []
    for row, original in zip(rows, examples):
        if row.get("timed_out") or row.get("error") or int(row.get("exit_code") or 0) != 0:
            logger.warning(
                "[coding_gen] reference failed: error=%s exit=%s stderr=%s",
                row.get("error"),
                row.get("exit_code"),
                (row.get("stderr") or "")[:1500],
            )
            return None
        actual = str(row.get("actual") or "").strip()
        claimed = str(original.get("output") or "").strip()
        if actual == "" and claimed not in {"", '""', "''", "null", "None"}:
            return None
        outputs.append(actual)

    if _is_identity_echo(examples, outputs):
        logger.warning(
            "[coding_gen] reference looks like a no-op (output == input echoed back) — rejecting"
        )
        return None

    return outputs


def _align_to_reference(problem: dict[str, Any]) -> Optional[dict[str, Any]]:
    examples = problem.get("examples") or []
    ref = problem.get("reference_solution") or ""
    outs = _run_reference_outputs(ref, examples)
    if outs is None:
        return None
    fixed = []
    for original, actual in zip(examples, outs):
        fixed.append(
            {
                "input": original["input"],
                "output": actual,
                "explanation": str(original.get("explanation") or "").strip(),
            }
        )
    out = dict(problem)
    out["examples"] = fixed
    return out
