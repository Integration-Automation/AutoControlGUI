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
from typing import Dict, List, Mapping, MutableMapping, Optional, Tuple

from je_auto_control.utils.exception.exceptions import AutoControlException

_BOM = chr(0xFEFF)
_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]*$")
_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", '"': '"', "\\": "\\", "'": "'"}


class DotenvError(AutoControlException, ValueError):
    """A mapping cannot be written as ``.env`` text (a key the parser would not read back)."""


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


_INLINE_COMMENT = re.compile(r"[ \t]#")


def _strip_inline_comment(value: str) -> str:
    # A tab before the # starts a comment too: "A=b\t# c" read as "b\t# c".
    match = _INLINE_COMMENT.search(value)
    return value[:match.start()] if match else value


def _unquoted(raw: str) -> str:
    """The unquoted value after ``=``: ``#`` starts a comment only after whitespace.

    ``KEY= # comment`` is empty, but ``COLOR=#ff0000`` is ``#ff0000``; the
    value used to be stripped first, which lost that difference and read it as
    empty.
    """
    return _strip_inline_comment(raw).strip()


def _line_close(line: str, quote: str, start: int) -> int:
    """Column of the first unescaped ``quote`` in ``line`` from ``start``, or -1.

    A backslash escapes the next character; at the end of a line it escapes
    the line break, so every line is scanned from a fresh state.
    """
    index = start
    while index < len(line):
        if line[index] == "\\":
            index += 2
            continue
        if line[index] == quote:
            return index
        index += 1
    return -1


class _Closers:
    """Per quote character, the first line at or after each line that holds an unescaped quote.

    Built once per parse: an unclosed quote rescanned every following line
    for each line it added, and each later unclosed quote did the same --
    ``A="x`` followed by 20,000 lines took 190 s.
    """

    def __init__(self, lines: List[str]) -> None:
        self._lines = lines
        self._next: Dict[str, List[int]] = {}

    def next_line(self, quote: str, start: int) -> int:
        """The index of the first line at or after ``start`` with an unescaped ``quote``, or -1."""
        if quote not in self._next:
            following = [-1] * (len(self._lines) + 1)
            for line_index in range(len(self._lines) - 1, -1, -1):
                has_quote = _line_close(self._lines[line_index], quote, 0) >= 0
                following[line_index] = line_index if has_quote else following[line_index + 1]
            self._next[quote] = following
        return self._next[quote][start]


def _parse_entry(lines: List[str], index: int, closers: _Closers) -> Tuple[Optional[Tuple[str, str]], int]:
    """Parse the entry starting at ``lines[index]``; return it and the next index.

    A quoted value ends at its closing quote -- anything after it (an inline
    comment) is ignored, and it may run over several lines, keeping each
    line's trailing whitespace. One that is never closed is read as plain text
    of its own line.
    """
    head = _parse_line(lines[index])
    if head is None:
        return None, index + 1
    key, raw = head
    value = raw.lstrip(" \t")
    quote = value[:1]
    if quote not in ("'", '"'):
        return (key, _unquoted(raw)), index + 1
    close, end = _line_close(value, quote, 1), index + 1
    if close >= 0:
        inner = value[1:close]
    else:
        last = closers.next_line(quote, index + 1)
        if last < 0:
            return (key, _unquoted(value)), index + 1
        tail = lines[last][:_line_close(lines[last], quote, 0)]
        inner = "\n".join([value[1:], *lines[index + 1:last], tail])
        end = last + 1
    return (key, _unescape_single(inner) if quote == "'" else _unescape(inner)), end


_SINGLE_QUOTE_ESCAPE = re.compile(r"\\([\\'])")


def _unescape_single(value: str) -> str:
    """Decode the only escapes a single-quoted value has: ``\\\\`` and ``\\'`` (python-dotenv)."""
    return _SINGLE_QUOTE_ESCAPE.sub(r"\1", value)


_EXPORT = re.compile(r"export[ \t]")


def _parse_line(line: str) -> Optional[Tuple[str, str]]:
    # Only the left side: the right is part of a quoted value that runs on.
    stripped = line.lstrip()
    if not stripped.strip() or stripped.startswith("#"):
        return None
    if _EXPORT.match(stripped):
        # "export\tKEY=1" is an export too; it was dropped as an unknown key.
        stripped = stripped[len("export"):].lstrip()
    key, sep, raw = stripped.partition("=")
    key = key.strip()
    if not sep or not _KEY_RE.match(key):
        return None
    return key, raw


def parse_dotenv(text: str) -> Dict[str, str]:
    """Parse ``.env`` ``text`` into an ordered ``{key: value}`` dict.

    A leading byte-order mark is skipped, as :func:`dotenv_values` does for
    files; it used to make the first key invalid and drop it.
    """
    result: Dict[str, str] = {}
    text = text or ""
    if text.startswith(_BOM):
        text = text[1:]
    # Only CR / LF end a line: str.splitlines() also splits on \\v, \\f and
    # U+2028, which dump_dotenv leaves unquoted, so such values were cut.
    lines = re.split(r"\r\n|\r|\n", text)
    closers = _Closers(lines)
    index = 0
    while index < len(lines):
        item, index = _parse_entry(lines, index, closers)
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


def dump_dotenv(mapping: Mapping[str, str]) -> str:
    """Serialise ``mapping`` to ``.env`` text, quoting values when needed.

    A key the parser would not read back raises :class:`DotenvError`: a key of
    ``"X\\nPATH"`` wrote a second line that set ``PATH``, ``"A=B"`` read back as
    ``A`` with ``B=`` in its value, and ``"1A"`` / ``"A B"`` vanished.
    """
    lines = []
    for key, value in mapping.items():
        if not isinstance(key, str) or not _KEY_RE.fullmatch(key):
            raise DotenvError(f"not a .env key: {key!r}")
        text = str(value)
        # Quote anything parsing would otherwise change: surrounding spaces,
        # ``#``, line breaks (``\\r`` too -- the parser splits on it) and quotes.
        if text != text.strip() or any(ch in text for ch in ('#', '\n', '\r', '"', "'")):
            text = '"' + text.replace("\\", "\\\\").replace('"', '\\"').replace(
                "\n", "\\n").replace("\r", "\\r") + '"'
        lines.append(f"{key}={text}")
    return "\n".join(lines)
