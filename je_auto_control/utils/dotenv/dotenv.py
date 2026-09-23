""".env file parsing and serialisation (no ``python-dotenv`` dependency).

``script_vars.load_vars_from_json`` ingests flat JSON, but nothing reads the
de-facto 12-factor ``.env`` file. This parses ``KEY=VALUE`` lines — honouring
``export`` prefixes, single/double quoting (a quoted value may span lines),
escapes, and inline comments — into a plain dict that can feed a config layer.

Pure standard library (``re``); imports no ``PySide6``. ``parse_dotenv`` is a
pure string-to-dict function; the loader merges into a caller-supplied mapping
rather than mutating ``os.environ``, so it is safe and deterministic in CI.
"""
import re
from pathlib import Path
from typing import Dict, List, MutableMapping, Optional, Tuple

_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]*$")
_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", '"': '"', "\\": "\\", "'": "'"}


def _unescape(value: str) -> str:
    out = []
    chars = iter(value)
    for char in chars:
        if char == "\\":
            nxt = next(chars, "\\")
            out.append(_ESCAPES.get(nxt, "\\" + nxt))
        else:
            out.append(char)
    return "".join(out)


def _strip_inline_comment(value: str) -> str:
    marker = value.find(" #")
    return value[:marker] if marker != -1 else value


def _unquoted(value: str) -> str:
    if value.startswith("#"):          # ``KEY= # comment`` is an empty value
        return ""
    return _strip_inline_comment(value).strip()


def _closing_quote(value: str, quote: str) -> int:
    """Index of the quote closing ``value[0]``, or -1; ``\\"`` does not close."""
    index = 1
    while index < len(value):
        if value[index] == "\\" and quote == '"':
            index += 2
            continue
        if value[index] == quote:
            return index
        index += 1
    return -1


def _parse_entry(lines: List[str], index: int) -> Tuple[Optional[Tuple[str, str]], int]:
    """Parse the entry starting at ``lines[index]``; return it and the next index.

    A quoted value ends at its closing quote -- anything after it (an inline
    comment) is ignored, and it may run over several lines. One that is never
    closed is read as plain text of its own line, as before.
    """
    head = _parse_line(lines[index])
    if head is None:
        return None, index + 1
    key, raw = head
    value = raw.strip()
    quote = value[:1]
    if quote not in ("'", '"'):
        return (key, _unquoted(value)), index + 1
    end, close = index + 1, _closing_quote(value, quote)
    while close == -1 and end < len(lines):
        value += "\n" + lines[end]
        end += 1
        close = _closing_quote(value, quote)
    if close == -1:
        return (key, _unquoted(raw.strip())), index + 1
    inner = value[1:close]
    return (key, inner if quote == "'" else _unescape(inner)), end


def _parse_line(line: str) -> Optional[Tuple[str, str]]:
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return None
    if stripped.startswith("export "):
        stripped = stripped[len("export "):].lstrip()
    key, sep, raw = stripped.partition("=")
    key = key.strip()
    if not sep or not _KEY_RE.match(key):
        return None
    return key, raw


def parse_dotenv(text: str) -> Dict[str, str]:
    """Parse ``.env`` ``text`` into an ordered ``{key: value}`` dict."""
    result: Dict[str, str] = {}
    # Only CR / LF end a line: str.splitlines() also splits on \\v, \\f and
    # U+2028, which dump_dotenv leaves unquoted, so such values were cut.
    lines = re.split(r"\r\n|\r|\n", text or "")
    index = 0
    while index < len(lines):
        item, index = _parse_entry(lines, index)
        if item is not None:
            result[item[0]] = item[1]
    return result


def dotenv_values(path: str) -> Dict[str, str]:
    """Read and parse a ``.env`` file at ``path``.

    Decoded as ``utf-8-sig``: with a BOM (Notepad) the first key read as
    U+FEFF followed by ``KEY``, was rejected as invalid and silently
    dropped.
    """
    return parse_dotenv(Path(path).read_text(encoding="utf-8-sig"))


def load_dotenv(path: str, env: MutableMapping[str, str], *,
                override: bool = False) -> MutableMapping[str, str]:
    """Merge a ``.env`` file into ``env`` and return it.

    Existing keys are kept unless ``override`` is set. ``env`` is supplied by
    the caller (never ``os.environ`` implicitly), keeping the load explicit.
    """
    for key, value in dotenv_values(path).items():
        if override or key not in env:
            env[key] = value
    return env


def dump_dotenv(mapping: MutableMapping[str, str]) -> str:
    """Serialise ``mapping`` to ``.env`` text, quoting values when needed."""
    lines = []
    for key, value in mapping.items():
        text = str(value)
        # Quote anything parsing would otherwise change: surrounding spaces,
        # ``#``, line breaks (``\\r`` too -- the parser splits on it) and quotes.
        if text != text.strip() or any(ch in text for ch in ('#', '\n', '\r', '"', "'")):
            text = '"' + text.replace("\\", "\\\\").replace('"', '\\"').replace(
                "\n", "\\n").replace("\r", "\\r") + '"'
        lines.append(f"{key}={text}")
    return "\n".join(lines)
