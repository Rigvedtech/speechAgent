"""Estimate time/space complexity of candidate code (local heuristics, no LLM).

Fast and offline — runs on every Run without Groq. Estimates, not formal proofs.
"""

from __future__ import annotations

import ast
import re
from typing import Any, Optional


def analyze_complexity(*, language: str, code: str) -> dict[str, Any]:
    """Return {time, space, note, confidence} for the given source."""
    lang = (language or "python").strip().lower()
    src = (code or "").strip()
    if not src:
        return {
            "time": "O(1)",
            "space": "O(1)",
            "note": "Empty code.",
            "confidence": "low",
        }

    if lang == "python":
        return _analyze_python(src)
    if lang in {"javascript", "typescript"}:
        return _analyze_js_like(src)
    return _analyze_generic(src)


def _analyze_python(src: str) -> dict[str, Any]:
    try:
        tree = ast.parse(src)
    except SyntaxError:
        # Fall back to generic regex if code doesn't parse yet
        return _analyze_generic(src)

    loop_depth = _max_loop_depth(tree)
    has_recursion = _has_recursion(tree)
    has_sort = _calls_named(tree, {"sorted", "sort"})
    has_heap = "heapq" in src or _calls_named(tree, {"heappush", "heappop", "heapify"})
    uses_extra = _uses_extra_space(tree)

    time, note_parts, confidence = _compose_time(
        loop_depth=loop_depth,
        has_recursion=has_recursion,
        has_sort=has_sort,
        has_heap=has_heap,
    )
    space = "O(n)" if uses_extra or has_recursion else "O(1)"
    if has_sort and space == "O(1)":
        space = "O(n)"  # Timsort / sorted() allocates
        note_parts.append("sort may use extra memory")

    return {
        "time": time,
        "space": space,
        "note": "; ".join(note_parts) if note_parts else "Heuristic estimate from control flow.",
        "confidence": confidence,
    }


def _max_loop_depth(node: ast.AST, depth: int = 0) -> int:
    best = depth
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.For, ast.While, ast.AsyncFor)):
            best = max(best, _max_loop_depth(child, depth + 1))
        elif isinstance(child, ast.ListComp):
            # Nested generators inside a comprehension
            gens = len(child.generators)
            best = max(best, _max_loop_depth(child, depth + gens))
        elif isinstance(child, (ast.SetComp, ast.DictComp, ast.GeneratorExp)):
            gens = len(getattr(child, "generators", []) or [])
            best = max(best, _max_loop_depth(child, depth + gens))
        else:
            best = max(best, _max_loop_depth(child, depth))
    return best


def _has_recursion(tree: ast.AST) -> bool:
    fn_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            fn_names.add(node.name)
    if not fn_names:
        return False
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = _call_name(node.func)
            if name and name in fn_names:
                return True
    return False


def _calls_named(tree: ast.AST, names: set[str]) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = _call_name(node.func)
            if name in names:
                return True
    return False


def _call_name(func: ast.AST) -> Optional[str]:
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _uses_extra_space(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, (ast.List, ast.Dict, ast.Set, ast.ListComp, ast.DictComp, ast.SetComp)):
            return True
        if isinstance(node, ast.Call):
            name = _call_name(node.func)
            if name in {"list", "dict", "set", "deque", "Counter", "defaultdict"}:
                return True
    return False


def _compose_time(
    *,
    loop_depth: int,
    has_recursion: bool,
    has_sort: bool,
    has_heap: bool,
) -> tuple[str, list[str], str]:
    notes: list[str] = []
    confidence = "medium"

    if loop_depth >= 3:
        time = f"O(n^{loop_depth})"
        notes.append(f"{loop_depth} nested loops")
        confidence = "high"
    elif loop_depth == 2:
        time = "O(n^2)"
        notes.append("2 nested loops")
        confidence = "high"
    elif loop_depth == 1:
        time = "O(n)"
        notes.append("single loop")
        confidence = "high"
    else:
        time = "O(1)"
        notes.append("no loops detected")
        confidence = "medium"

    if has_sort:
        # Sort dominates a single loop; with nested loops, n^2 usually wins.
        if loop_depth <= 1:
            time = "O(n log n)"
            notes.append("sorting detected")
            confidence = "high"
        else:
            notes.append("also uses sorting")

    if has_heap and loop_depth <= 1 and not has_sort:
        time = "O(n log n)"
        notes.append("heap operations")
        confidence = "medium"

    if has_recursion:
        notes.append("recursive calls — may change asymptotic cost")
        if loop_depth == 0 and not has_sort:
            time = "O(n)"  # common case: linear recursion / tree walk
            confidence = "low"
        else:
            confidence = "low"

    return time, notes, confidence


_JS_FOR = re.compile(
    r"\bfor\s*\(|\bwhile\s*\(|\bfor\s*\([^)]*\bof\b|\bfor\s*\([^)]*\bin\b|\.forEach\s*\(|\.map\s*\(",
    re.I,
)
_JS_SORT = re.compile(r"\.sort\s*\(", re.I)
_JS_NESTED_HINT = re.compile(
    r"(for\s*\([^)]*\)\s*\{[^}]{0,800}for\s*\()|(while\s*\([^)]*\)\s*\{[^}]{0,800}(for|while)\s*\()",
    re.I | re.S,
)


def _analyze_js_like(src: str) -> dict[str, Any]:
    loops = len(_JS_FOR.findall(src))
    nested = bool(_JS_NESTED_HINT.search(src))
    has_sort = bool(_JS_SORT.search(src))
    # Crude triple-nest: count max consecutive for/while openings in a window
    depth = _brace_loop_depth(src)

    time, notes, confidence = _compose_time(
        loop_depth=depth if depth else (2 if nested else (1 if loops else 0)),
        has_recursion=_looks_recursive_js(src),
        has_sort=has_sort,
        has_heap=False,
    )
    space = "O(n)" if re.search(r"\b(new\s+(Map|Set|Array)|\{|\[)", src) else "O(1)"
    return {
        "time": time,
        "space": space,
        "note": "; ".join(notes) if notes else "Heuristic estimate from control flow.",
        "confidence": confidence,
    }


def _brace_loop_depth(src: str) -> int:
    """Approximate nested for/while depth using a simple token scan."""
    tokens = re.findall(r"\b(for|while)\b|[{}]", src)
    depth = 0
    best = 0
    for tok in tokens:
        if tok in {"for", "while"}:
            depth += 1
            best = max(best, depth)
        elif tok == "}":
            depth = max(0, depth - 1)
        # '{' doesn't change loop nesting by itself
    return best


def _looks_recursive_js(src: str) -> bool:
    m = re.search(r"function\s+([A-Za-z_][\w]*)\s*\(", src)
    if not m:
        # arrow: const foo = (...) =>
        m = re.search(r"(?:const|let|var)\s+([A-Za-z_][\w]*)\s*=\s*(?:async\s*)?\([^)]*\)\s*=>", src)
    if not m:
        return False
    name = m.group(1)
    # Call site besides the definition
    calls = len(re.findall(rf"\b{re.escape(name)}\s*\(", src))
    return calls >= 2


def _analyze_generic(src: str) -> dict[str, Any]:
    depth = _brace_loop_depth(src)
    has_sort = bool(re.search(r"\b(sort|sorted|Arrays\.sort|Collections\.sort)\b", src, re.I))
    time, notes, confidence = _compose_time(
        loop_depth=depth,
        has_recursion=False,
        has_sort=has_sort,
        has_heap=False,
    )
    return {
        "time": time,
        "space": "O(n)" if depth >= 1 else "O(1)",
        "note": "; ".join(notes) if notes else "Heuristic estimate.",
        "confidence": "low" if confidence == "medium" else confidence,
    }
