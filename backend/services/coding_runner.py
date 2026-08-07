"""Local coding runner for demo/dev (timeout-bounded subprocess).

Not a production sandbox — use Piston/Judge0 later for harder isolation.
Supports a single file or a small multi-file workspace.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from services.coding_languages import CODING_LANGUAGES, SUPPORTED_LANGUAGES, language_entry


MAX_CODE_CHARS = 80_000
MAX_STDIN_CHARS = 20_000
MAX_FILES = 20
MAX_FILE_CHARS = 40_000
DEFAULT_TIMEOUT_SEC = 5.0
MAX_OUTPUT_CHARS = 20_000


@dataclass
class RunResult:
    ok: bool
    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool
    language: str
    error: Optional[str] = None


def _trim(text: str, limit: int = MAX_OUTPUT_CHARS) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 20] + "\n...[truncated]..."


def _resolve_node() -> Optional[str]:
    return shutil.which("node") or shutil.which("nodejs")


def _safe_rel_path(path: str) -> Optional[str]:
    raw = (path or "").replace("\\", "/").strip().lstrip("/")
    if not raw or ".." in raw.split("/"):
        return None
    if any(part.startswith(".") for part in raw.split("/")):
        return None
    return raw


def _default_entry(language: str, files: dict[str, str], entry_path: Optional[str]) -> str:
    if entry_path and entry_path in files:
        return entry_path
    preferred = language_entry(language)
    if preferred in files:
        return preferred
    meta = CODING_LANGUAGES.get(language, {})
    ext = f".{meta.get('extension', '')}" if meta.get("extension") else ""
    if ext:
        for name in files:
            if name.endswith(ext):
                return name
    return next(iter(files.keys()))


def _build_cmd(lang: str, root: Path, entry: str) -> tuple[Optional[list[str]], Optional[str]]:
    """Return (command, error)."""
    entry_path = root / entry
    if lang == "python":
        return [sys.executable, "-I", str(entry_path)], None
    if lang in {"javascript", "typescript"}:
        node = _resolve_node()
        if not node:
            return None, "Node.js is not installed or not on PATH"
        if lang == "typescript":
            # Prefer tsx if present; else try npx tsx once.
            tsx = shutil.which("tsx")
            if tsx:
                return [tsx, str(entry_path)], None
            return [node, "--import", "tsx", str(entry_path)], None
        return [node, str(entry_path)], None
    if lang == "ruby":
        ruby = shutil.which("ruby")
        if not ruby:
            return None, "Ruby is not installed or not on PATH"
        return [ruby, str(entry_path)], None
    if lang == "php":
        php = shutil.which("php")
        if not php:
            return None, "PHP is not installed or not on PATH"
        return [php, str(entry_path)], None
    if lang == "go":
        go = shutil.which("go")
        if not go:
            return None, "Go is not installed or not on PATH"
        return [go, "run", str(entry_path)], None
    if lang == "java":
        javac = shutil.which("javac")
        java = shutil.which("java")
        if not javac or not java:
            return None, "Java JDK (javac/java) is not installed or not on PATH"
        # Compile all .java then run harness class
        return ["__java__"], None  # special-cased below
    if lang == "cpp":
        gxx = shutil.which("g++") or shutil.which("clang++")
        if not gxx:
            return None, "g++/clang++ is not installed or not on PATH"
        return ["__cpp__"], None
    meta = CODING_LANGUAGES.get(lang)
    if meta and not meta.get("runnable"):
        return None, f"Run is not enabled yet for {meta.get('label', lang)} (editor + AI generate only)"
    return None, f"Unsupported language: {lang}"


def run_code(
    *,
    language: str,
    code: str,
    stdin: str = "",
    timeout_sec: float = DEFAULT_TIMEOUT_SEC,
    files: Optional[dict[str, str]] = None,
    entry_path: Optional[str] = None,
) -> RunResult:
    lang = (language or "").strip().lower()
    if lang not in SUPPORTED_LANGUAGES:
        return RunResult(
            ok=False,
            exit_code=-1,
            stdout="",
            stderr="",
            timed_out=False,
            language=lang,
            error=f"Unsupported language: {language}",
        )

    workspace: dict[str, str] = {}
    if files:
        if len(files) > MAX_FILES:
            return RunResult(
                ok=False,
                exit_code=-1,
                stdout="",
                stderr="",
                timed_out=False,
                language=lang,
                error=f"Too many files (max {MAX_FILES})",
            )
        for raw_path, content in files.items():
            safe = _safe_rel_path(str(raw_path))
            if not safe:
                return RunResult(
                    ok=False,
                    exit_code=-1,
                    stdout="",
                    stderr="",
                    timed_out=False,
                    language=lang,
                    error=f"Invalid file path: {raw_path}",
                )
            text = content if content is not None else ""
            if len(text) > MAX_FILE_CHARS:
                return RunResult(
                    ok=False,
                    exit_code=-1,
                    stdout="",
                    stderr="",
                    timed_out=False,
                    language=lang,
                    error=f"File too large: {safe}",
                )
            workspace[safe] = text
    else:
        source = code or ""
        if len(source) > MAX_CODE_CHARS:
            return RunResult(
                ok=False,
                exit_code=-1,
                stdout="",
                stderr="",
                timed_out=False,
                language=lang,
                error=f"Code exceeds {MAX_CODE_CHARS} characters",
            )
        workspace[language_entry(lang)] = source

    if not workspace:
        return RunResult(
            ok=False,
            exit_code=-1,
            stdout="",
            stderr="",
            timed_out=False,
            language=lang,
            error="No files to run",
        )

    if len(stdin) > MAX_STDIN_CHARS:
        return RunResult(
            ok=False,
            exit_code=-1,
            stdout="",
            stderr="",
            timed_out=False,
            language=lang,
            error=f"stdin exceeds {MAX_STDIN_CHARS} characters",
        )

    entry = _default_entry(lang, workspace, entry_path)
    cmd_or_special, cmd_err = _build_cmd(lang, Path("."), entry)
    if cmd_err and cmd_or_special is None:
        return RunResult(
            ok=False,
            exit_code=-1,
            stdout="",
            stderr="",
            timed_out=False,
            language=lang,
            error=cmd_err,
        )

    tmp_dir: Optional[str] = None
    try:
        tmp_dir = tempfile.mkdtemp(prefix="coding_ws_")
        root = Path(tmp_dir)
        for rel, content in workspace.items():
            path = root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8", newline="\n")

        env = {
            "PATH": os.environ.get("PATH", ""),
            "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
            "TEMP": os.environ.get("TEMP", tempfile.gettempdir()),
            "TMP": os.environ.get("TMP", tempfile.gettempdir()),
            "PYTHONIOENCODING": "utf-8",
            "PYTHONPATH": str(root),
        }

        if lang == "java":
            java_files = sorted(str(p) for p in root.glob("*.java"))
            compile_proc = subprocess.run(
                ["javac", *java_files],
                cwd=str(root),
                capture_output=True,
                text=True,
                timeout=timeout_sec,
                env=env,
            )
            if compile_proc.returncode != 0:
                return RunResult(
                    ok=False,
                    exit_code=int(compile_proc.returncode),
                    stdout=_trim(compile_proc.stdout or ""),
                    stderr=_trim(compile_proc.stderr or ""),
                    timed_out=False,
                    language=lang,
                    error="Java compile failed",
                )
            main_class = Path(entry).stem
            if entry.startswith("__prabhat") or main_class == "PrabhatHarness":
                main_class = "PrabhatHarness"
            cmd = ["java", "-cp", str(root), main_class]
        elif lang == "cpp":
            out_bin = root / ("a.exe" if os.name == "nt" else "a.out")
            gxx = shutil.which("g++") or shutil.which("clang++")
            compile_proc = subprocess.run(
                [gxx, "-std=c++17", "-O0", str(root / entry), "-o", str(out_bin)],
                cwd=str(root),
                capture_output=True,
                text=True,
                timeout=timeout_sec,
                env=env,
            )
            if compile_proc.returncode != 0:
                return RunResult(
                    ok=False,
                    exit_code=int(compile_proc.returncode),
                    stdout=_trim(compile_proc.stdout or ""),
                    stderr=_trim(compile_proc.stderr or ""),
                    timed_out=False,
                    language=lang,
                    error="C++ compile failed",
                )
            cmd = [str(out_bin)]
        elif lang == "typescript":
            tsx = shutil.which("tsx")
            node = _resolve_node()
            if tsx:
                cmd = [tsx, str(root / entry)]
            else:
                # Fall back: execute as JS-like via node if user wrote plain JS in .ts
                completed_try = subprocess.run(
                    [node or "node", "--experimental-strip-types", str(root / entry)],
                    input=stdin,
                    capture_output=True,
                    text=True,
                    timeout=timeout_sec,
                    cwd=str(root),
                    env=env,
                )
                if completed_try.returncode == 0 or "experimental-strip-types" not in (
                    completed_try.stderr or ""
                ):
                    return RunResult(
                        ok=completed_try.returncode == 0,
                        exit_code=int(completed_try.returncode),
                        stdout=_trim(completed_try.stdout or ""),
                        stderr=_trim(completed_try.stderr or ""),
                        timed_out=False,
                        language=lang,
                    )
                return RunResult(
                    ok=False,
                    exit_code=-1,
                    stdout="",
                    stderr=_trim(completed_try.stderr or ""),
                    timed_out=False,
                    language=lang,
                    error="TypeScript runner needs Node 22+ or tsx on PATH",
                )
        else:
            cmd, _ = _build_cmd(lang, root, entry)
            if not cmd:
                return RunResult(
                    ok=False,
                    exit_code=-1,
                    stdout="",
                    stderr="",
                    timed_out=False,
                    language=lang,
                    error=cmd_err or f"Unsupported language: {lang}",
                )

        completed = subprocess.run(
            cmd,
            input=stdin,
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            cwd=str(root),
            env=env,
        )
        return RunResult(
            ok=completed.returncode == 0,
            exit_code=int(completed.returncode),
            stdout=_trim(completed.stdout or ""),
            stderr=_trim(completed.stderr or ""),
            timed_out=False,
            language=lang,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = _trim((exc.stdout or "") if isinstance(exc.stdout, str) else "")
        stderr = _trim((exc.stderr or "") if isinstance(exc.stderr, str) else "")
        return RunResult(
            ok=False,
            exit_code=-1,
            stdout=stdout,
            stderr=stderr or f"Execution timed out after {timeout_sec:.0f}s",
            timed_out=True,
            language=lang,
            error="timeout",
        )
    except Exception as exc:  # noqa: BLE001
        return RunResult(
            ok=False,
            exit_code=-1,
            stdout="",
            stderr="",
            timed_out=False,
            language=lang,
            error=str(exc),
        )
    finally:
        if tmp_dir:
            shutil.rmtree(tmp_dir, ignore_errors=True)


def _normalize_output(value: str) -> str:
    text = (value or "").strip()
    try:
        return json.dumps(json.loads(text), sort_keys=True, separators=(",", ":"))
    except Exception:
        return " ".join(text.split())


def _snake_to_camel(name: str) -> str:
    parts = [p for p in (name or "").split("_") if p]
    if not parts:
        return ""
    return parts[0] + "".join(p[:1].upper() + p[1:] for p in parts[1:])


def _function_candidates(entry_function: Optional[str]) -> list[str]:
    names: list[str] = []
    if entry_function:
        names.append(entry_function.strip())
        camel = _snake_to_camel(entry_function.strip())
        if camel and camel not in names:
            names.append(camel)
    for fallback in ("solution", "solve", "main"):
        if fallback not in names:
            names.append(fallback)
    return [n for n in names if n]


def _python_harness(candidate_entry: str, fn_names: list[str]) -> str:
    names_lit = json.dumps(fn_names)
    # Separate harness entry so candidate `if __name__ == "__main__"` does not run.
    return f'''# Auto-generated — do not edit
import ast
import importlib.util
import json
import sys
from pathlib import Path

ENTRY = {candidate_entry!r}
FN_NAMES = {names_lit}

def _dump(value):
    if isinstance(value, (dict, list)):
        print(json.dumps(value, separators=(",", ":")))
    elif value is True:
        print("true")
    elif value is False:
        print("false")
    elif value is None:
        print("null")
    else:
        print(value)

path = Path(ENTRY)
spec = importlib.util.spec_from_file_location("candidate_sol", path.resolve())
if spec is None or spec.loader is None:
    raise SystemExit(f"Cannot load candidate file: {{ENTRY}}")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

fn = None
for name in FN_NAMES:
    cand = getattr(mod, name, None)
    if callable(cand):
        fn = cand
        break
if fn is None:
    raise SystemExit(
        "No solution function found. Define one of: " + ", ".join(FN_NAMES)
    )

raw = sys.stdin.read().strip()
data = ast.literal_eval(raw or "None")
_dump(fn(data))
'''


def _javascript_harness(candidate_entry: str, fn_names: list[str]) -> str:
    names_lit = json.dumps(fn_names)
    return f'''// Auto-generated — do not edit
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const ENTRY = {candidate_entry!r};
const FN_NAMES = {names_lit};
const code = fs.readFileSync(path.resolve(ENTRY), "utf8");
const sandbox = {{
  module: {{ exports: {{}} }},
  exports: {{}},
  console,
  require,
  Buffer,
  setTimeout,
  clearTimeout,
}};
sandbox.global = sandbox;
sandbox.globalThis = sandbox;
vm.createContext(sandbox);
vm.runInContext(code, sandbox, {{ filename: ENTRY }});

let fn = null;
for (const name of FN_NAMES) {{
  if (typeof sandbox[name] === "function") {{
    fn = sandbox[name];
    break;
  }}
  if (typeof sandbox.module.exports === "function") {{
    fn = sandbox.module.exports;
    break;
  }}
  if (
    sandbox.module.exports &&
    typeof sandbox.module.exports[name] === "function"
  ) {{
    fn = sandbox.module.exports[name];
    break;
  }}
}}
if (!fn) {{
  throw new Error("No solution function found. Define one of: " + FN_NAMES.join(", "));
}}

const raw = fs.readFileSync(0, "utf8").trim();
const data = raw ? JSON.parse(raw) : null;
const result = fn(data);
if (typeof result === "object") {{
  console.log(JSON.stringify(result));
}} else if (typeof result === "boolean") {{
  console.log(result ? "true" : "false");
}} else if (result === null || result === undefined) {{
  console.log("null");
}} else {{
  console.log(String(result));
}}
'''


def _ruby_harness(candidate_entry: str, fn_names: list[str]) -> str:
    names_lit = json.dumps(fn_names)
    return f'''# Auto-generated — do not edit
require "json"
ENTRY = {candidate_entry!r}
FN_NAMES = {names_lit}
load ENTRY
fn = nil
FN_NAMES.each do |name|
  if respond_to?(name)
    fn = method(name)
    break
  end
end
raise "No solution function found. Define one of: #{{FN_NAMES.join(', ')}}" if fn.nil?
raw = STDIN.read.to_s.strip
data = raw.empty? ? nil : JSON.parse(raw)
result = fn.call(data)
if result.is_a?(Hash) || result.is_a?(Array)
  puts JSON.generate(result)
elsif result == true
  puts "true"
elsif result == false
  puts "false"
elsif result.nil?
  puts "null"
else
  puts result
end
'''


def _php_harness(candidate_entry: str, fn_names: list[str]) -> str:
    names_php = ", ".join(json.dumps(n) for n in fn_names)
    return f'''<?php
// Auto-generated — do not edit
require {json.dumps(candidate_entry)};
$fnNames = [{names_php}];
$fn = null;
foreach ($fnNames as $name) {{
  if (function_exists($name)) {{ $fn = $name; break; }}
}}
if ($fn === null) {{
  fwrite(STDERR, "No solution function found\\n");
  exit(1);
}}
$raw = trim(stream_get_contents(STDIN));
$data = $raw === "" ? null : json_decode($raw, true);
$result = $fn($data);
if (is_array($result) || is_object($result)) {{
  echo json_encode($result);
}} elseif (is_bool($result)) {{
  echo $result ? "true" : "false";
}} elseif ($result === null) {{
  echo "null";
}} else {{
  echo $result;
}}
'''


def _java_harness(fn_names: list[str]) -> str:
    """Hidden Java entry: parse stdin JSON/literal, call Solution.<method>, print result."""
    names_lit = ", ".join(json.dumps(n) for n in fn_names)
    return f'''// Auto-generated - do not edit
import java.io.*;
import java.lang.reflect.*;
import java.util.*;

public class PrabhatHarness {{
  static final String[] FN_NAMES = new String[] {{{names_lit}}};

  public static void main(String[] args) throws Exception {{
    String raw = readStdin().trim();
    if (raw.isEmpty()) raw = "null";
    Object data = MiniJson.parse(pythonishToJson(raw));

    Class<?> solClass = Class.forName("Solution");
    Object sol = null;
    try {{
      Constructor<?> ctor = solClass.getDeclaredConstructor();
      ctor.setAccessible(true);
      sol = ctor.newInstance();
    }} catch (NoSuchMethodException ignored) {{
      // static-only Solution
    }}

    Method target = null;
    boolean isStatic = false;
    for (String name : FN_NAMES) {{
      for (Method m : solClass.getDeclaredMethods()) {{
        if (!m.getName().equals(name) || m.getParameterCount() != 1) continue;
        m.setAccessible(true);
        target = m;
        isStatic = Modifier.isStatic(m.getModifiers());
        break;
      }}
      if (target != null) break;
    }}
    if (target == null) {{
      System.err.println("No solution method found. Define one of: " + String.join(", ", FN_NAMES));
      System.exit(1);
    }}
    if (!isStatic && sol == null) {{
      System.err.println("Solution needs a public no-arg constructor for instance methods.");
      System.exit(1);
    }}

    Object arg = coerce(data, target.getParameterTypes()[0]);
    Object result = isStatic ? target.invoke(null, arg) : target.invoke(sol, arg);
    dump(result);
  }}

  static String readStdin() throws IOException {{
    ByteArrayOutputStream bos = new ByteArrayOutputStream();
    byte[] buf = new byte[4096];
    int n;
    while ((n = System.in.read(buf)) >= 0) bos.write(buf, 0, n);
    return bos.toString("UTF-8");
  }}

  static String pythonishToJson(String s) {{
    String t = s.trim();
    // Allow Python literals True/False/None in example inputs
    t = t.replace("None", "null").replace("True", "true").replace("False", "false");
    return t;
  }}

  static Object coerce(Object data, Class<?> type) {{
    if (type == Object.class) return data;
    if (type == String.class) {{
      if (data == null) return null;
      if (data instanceof String) return data;
      return MiniJson.stringify(data);
    }}
    if ((type == Integer.class || type == int.class) && data instanceof Number)
      return ((Number) data).intValue();
    if ((type == Long.class || type == long.class) && data instanceof Number)
      return ((Number) data).longValue();
    if ((type == Double.class || type == double.class) && data instanceof Number)
      return ((Number) data).doubleValue();
    if ((type == Boolean.class || type == boolean.class) && data instanceof Boolean)
      return data;
    if (type == List.class || type == Collection.class) return data;
    if (type == Map.class) return data;
    if (type.isArray() && data instanceof List) {{
      List<?> list = (List<?>) data;
      Class<?> ct = type.getComponentType();
      Object arr = Array.newInstance(ct, list.size());
      for (int i = 0; i < list.size(); i++) Array.set(arr, i, coerce(list.get(i), ct));
      return arr;
    }}
    return data;
  }}

  static void dump(Object value) {{
    System.out.println(MiniJson.stringify(value));
  }}

  /** Tiny JSON parser/serializer (objects, arrays, strings, numbers, bool, null). */
  static final class MiniJson {{
    static Object parse(String s) {{
      Parser p = new Parser(s);
      Object v = p.parseValue();
      p.skipWs();
      return v;
    }}

    static String stringify(Object v) {{
      if (v == null) return "null";
      if (v instanceof Boolean) return ((Boolean) v) ? "true" : "false";
      if (v instanceof Number) {{
        double d = ((Number) v).doubleValue();
        if (Double.isFinite(d) && d == Math.rint(d) && Math.abs(d) < 1e15)
          return Long.toString(((Number) v).longValue());
        return Double.toString(d);
      }}
      if (v instanceof String) return quote((String) v);
      if (v instanceof Map) {{
        StringBuilder sb = new StringBuilder();
        sb.append("{{");
        boolean first = true;
        for (Object e : ((Map<?, ?>) v).entrySet()) {{
          Map.Entry<?, ?> en = (Map.Entry<?, ?>) e;
          if (!first) sb.append(",");
          first = false;
          sb.append(quote(String.valueOf(en.getKey()))).append(":").append(stringify(en.getValue()));
        }}
        sb.append("}}");
        return sb.toString();
      }}
      if (v instanceof Collection) {{
        StringBuilder sb = new StringBuilder();
        sb.append("[");
        boolean first = true;
        for (Object item : (Collection<?>) v) {{
          if (!first) sb.append(",");
          first = false;
          sb.append(stringify(item));
        }}
        sb.append("]");
        return sb.toString();
      }}
      if (v.getClass().isArray()) {{
        int len = Array.getLength(v);
        StringBuilder sb = new StringBuilder();
        sb.append("[");
        for (int i = 0; i < len; i++) {{
          if (i > 0) sb.append(",");
          sb.append(stringify(Array.get(v, i)));
        }}
        sb.append("]");
        return sb.toString();
      }}
      return quote(String.valueOf(v));
    }}

    static String quote(String s) {{
      StringBuilder sb = new StringBuilder();
      sb.append('"');
      for (int i = 0; i < s.length(); i++) {{
        char c = s.charAt(i);
        if (c == '"' || c == '\\\\') sb.append('\\\\').append(c);
        else if (c == '\\n') sb.append("\\\\n");
        else if (c == '\\r') sb.append("\\\\r");
        else if (c == '\\t') sb.append("\\\\t");
        else sb.append(c);
      }}
      sb.append('"');
      return sb.toString();
    }}

    static final class Parser {{
      final String s;
      int i = 0;
      Parser(String s) {{ this.s = s; }}
      void skipWs() {{ while (i < s.length() && Character.isWhitespace(s.charAt(i))) i++; }}
      char peek() {{ skipWs(); return i < s.length() ? s.charAt(i) : '\\0'; }}
      char next() {{ skipWs(); return s.charAt(i++); }}
      Object parseValue() {{
        char c = peek();
        if (c == '{{') return parseObject();
        if (c == '[') return parseArray();
        if (c == '"') return parseString();
        if (c == 't') {{ expect("true"); return Boolean.TRUE; }}
        if (c == 'f') {{ expect("false"); return Boolean.FALSE; }}
        if (c == 'n') {{ expect("null"); return null; }}
        return parseNumber();
      }}
      Map<String, Object> parseObject() {{
        next(); // {{
        Map<String, Object> map = new LinkedHashMap<>();
        skipWs();
        if (peek() == '}}') {{ next(); return map; }}
        while (true) {{
          String key = parseString();
          if (next() != ':') throw new RuntimeException("Expected :");
          map.put(key, parseValue());
          char c = next();
          if (c == '}}') break;
          if (c != ',') throw new RuntimeException("Expected , or }}");
        }}
        return map;
      }}
      List<Object> parseArray() {{
        next(); // [
        List<Object> list = new ArrayList<>();
        skipWs();
        if (peek() == ']') {{ next(); return list; }}
        while (true) {{
          list.add(parseValue());
          char c = next();
          if (c == ']') break;
          if (c != ',') throw new RuntimeException("Expected , or ]");
        }}
        return list;
      }}
      String parseString() {{
        if (next() != '"') throw new RuntimeException("Expected string");
        StringBuilder sb = new StringBuilder();
        while (i < s.length()) {{
          char c = s.charAt(i++);
          if (c == '"') break;
          if (c == '\\\\') {{
            char e = s.charAt(i++);
            if (e == 'n') sb.append('\\n');
            else if (e == 'r') sb.append('\\r');
            else if (e == 't') sb.append('\\t');
            else sb.append(e);
          }} else sb.append(c);
        }}
        return sb.toString();
      }}
      Number parseNumber() {{
        int start = i;
        if (peek() == '-') i++;
        while (i < s.length() && (Character.isDigit(s.charAt(i)) || s.charAt(i) == '.' || s.charAt(i) == 'e' || s.charAt(i) == 'E' || s.charAt(i) == '+' || s.charAt(i) == '-')) i++;
        String num = s.substring(start, i);
        if (num.indexOf('.') >= 0 || num.indexOf('e') >= 0 || num.indexOf('E') >= 0) return Double.valueOf(num);
        long v = Long.parseLong(num);
        if (v >= Integer.MIN_VALUE && v <= Integer.MAX_VALUE) return (int) v;
        return v;
      }}
      void expect(String lit) {{
        skipWs();
        if (!s.startsWith(lit, i)) throw new RuntimeException("Expected " + lit);
        i += lit.length();
      }}
    }}
  }}
}}
'''


def _with_harness(
    *,
    language: str,
    code: str,
    files: Optional[dict[str, str]],
    entry_path: Optional[str],
    entry_function: Optional[str],
) -> tuple[dict[str, str], str]:
    """Build workspace + hidden harness entry that calls the candidate function."""
    lang = (language or "").strip().lower()
    workspace: dict[str, str] = {}
    if files:
        workspace = {str(k): (v if v is not None else "") for k, v in files.items()}
    else:
        workspace[language_entry(lang)] = code or ""

    candidate_entry = _default_entry(lang, workspace, entry_path)
    fn_names = _function_candidates(entry_function)

    if lang in {"javascript", "typescript"}:
        harness_name = "__prabhat_harness.js"
        workspace[harness_name] = _javascript_harness(candidate_entry, fn_names)
        # For TS, prefer executing harness with node and loading file text in vm
        # (AI is instructed to keep typings light / JS-compatible).
    elif lang == "ruby":
        harness_name = "__prabhat_harness.rb"
        workspace[harness_name] = _ruby_harness(candidate_entry, fn_names)
    elif lang == "php":
        harness_name = "__prabhat_harness.php"
        workspace[harness_name] = _php_harness(candidate_entry, fn_names)
    elif lang == "python":
        harness_name = "__prabhat_harness.py"
        workspace[harness_name] = _python_harness(candidate_entry, fn_names)
    elif lang == "java":
        # Filename must match public class name for javac
        harness_name = "PrabhatHarness.java"
        workspace[harness_name] = _java_harness(fn_names)
        # Ensure candidate entry is present (Solution.java)
        if candidate_entry not in workspace and code:
            workspace[candidate_entry or "Solution.java"] = code
    else:
        # Fallback: run entry file directly (expects candidate to print) — still better than crash.
        # Prefer dedicated harnesses above for LeetCode-style checks.
        return workspace, candidate_entry

    return workspace, harness_name


def run_examples(
    *,
    language: str,
    code: str,
    examples: list[dict[str, Any]],
    timeout_sec: float = DEFAULT_TIMEOUT_SEC,
    files: Optional[dict[str, str]] = None,
    entry_path: Optional[str] = None,
    entry_function: Optional[str] = None,
) -> dict[str, Any]:
    """Run examples by calling the candidate function (hidden harness), not raw stdout."""
    harness_files, harness_entry = _with_harness(
        language=language,
        code=code,
        files=files,
        entry_path=entry_path,
        entry_function=entry_function,
    )
    results: list[dict[str, Any]] = []
    passed = 0
    run_lang = language
    if harness_entry.endswith(".js"):
        run_lang = "javascript"
    elif harness_entry.endswith(".py"):
        run_lang = "python"
    elif harness_entry.endswith(".rb"):
        run_lang = "ruby"
    elif harness_entry.endswith(".php"):
        run_lang = "php"
    elif harness_entry.endswith(".java"):
        run_lang = "java"

    for idx, example in enumerate(examples, start=1):
        stdin = str(example.get("input") or "")
        expected = str(example.get("output") or "")
        run = run_code(
            language=run_lang,
            code=code,
            stdin=stdin,
            timeout_sec=timeout_sec,
            files=harness_files,
            entry_path=harness_entry,
        )
        actual = (run.stdout or "").strip()
        match = (
            run.ok
            and not run.timed_out
            and _normalize_output(actual) == _normalize_output(expected)
        )
        if match:
            passed += 1
        results.append(
            {
                "index": idx,
                "input": stdin,
                "expected": expected,
                "actual": actual,
                "stderr": run.stderr,
                "exit_code": run.exit_code,
                "timed_out": run.timed_out,
                "passed": match,
                "error": run.error,
            }
        )
    total = len(results)
    return {
        "passed": passed,
        "total": total,
        "all_passed": total > 0 and passed == total,
        "results": results,
    }

