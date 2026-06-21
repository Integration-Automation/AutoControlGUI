""".env file parsing and serialisation (no ``python-dotenv`` dependency).

``script_vars.load_vars_from_json`` ingests flat JSON, but nothing reads the
de-facto 12-factor ``.env`` file. This parses ``KEY=VALUE`` lines — honouring
``export`` prefixes, single/double quoting, escapes, and inline comments — into
a plain dict that can feed a config layer.

Pure standard library (``re``); imports no ``PySide6``. ``parse_dotenv`` is a
pure string-to-dict function; the loader merges into a caller-supplied mapping
rather than mutating ``os.environ``, so it is safe and deterministic in CI.
"""
import re
from pathlib import Path
from typing import Dict, MutableMapping, Optional, Tuple

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


def _unquote(raw: str) -> str:
    value = raw.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        inner = value[1:-1]
        return inner if value[0] == "'" else _unescape(inner)
    return _strip_inline_comment(value).strip()


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
    return key, _unquote(raw)


def parse_dotenv(text: str) -> Dict[str, str]:
    """Parse ``.env`` ``text`` into an ordered ``{key: value}`` dict."""
    result: Dict[str, str] = {}
    for line in (text or "").splitlines():
        item = _parse_line(line)
        if item is not None:
            result[item[0]] = item[1]
    return result


def dotenv_values(path: str) -> Dict[str, str]:
    """Read and parse a ``.env`` file at ``path``."""
    return parse_dotenv(Path(path).read_text(encoding="utf-8"))


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
        if text != text.strip() or any(ch in text for ch in ('#', '\n', '"')):
            text = '"' + text.replace("\\", "\\\\").replace('"', '\\"').replace(
                "\n", "\\n") + '"'
        lines.append(f"{key}={text}")
    return "\n".join(lines)
