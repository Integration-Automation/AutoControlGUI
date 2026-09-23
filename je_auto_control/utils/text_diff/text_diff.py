"""Generate, apply and three-way-merge unified text diffs.

``difflib`` *generates* a unified diff but the standard library cannot *apply*
one, and there is no three-way merge anywhere — so updating a ``.received``
artifact, replaying a recorded text edit, or merging two edits of a base file
had no headless primitive. This adds the missing pieces. The complement,
``utils/json_patch``, covers structured JSON; this covers line-based text.

Operates on lines split without keep-ends and rejoined with ``\\n`` (a trailing
newline is preserved); ``\\r\\n`` and missing-final-newline nuances are out of
scope -- a ``\\ No newline at end of file`` marker is skipped, not applied.
Pure standard library (``difflib`` + ``re``); imports no ``PySide6``.
"""
import difflib
import re
from dataclasses import dataclass
from typing import List, Tuple

from je_auto_control.utils.exception.exceptions import AutoControlException

_HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


class PatchApplyError(AutoControlException):
    """A unified diff could not be applied to the given text."""


@dataclass(frozen=True)
class MergeResult:
    """Outcome of a three-way merge."""

    text: str
    conflicts: int
    clean: bool


def unified_diff(a: str, b: str, *, a_name: str = "a", b_name: str = "b",
                 context: int = 3) -> str:
    """Return a unified diff transforming ``a`` into ``b``."""
    lines = difflib.unified_diff(
        a.splitlines(), b.splitlines(), fromfile=a_name, tofile=b_name,
        lineterm="", n=context)
    return "\n".join(lines)


def _verify(source: List[str], index: int, expected: str) -> None:
    if index >= len(source) or source[index] != expected:
        raise PatchApplyError(
            f"context mismatch at source line {index + 1}")


def _apply_hunk(source: List[str], out: List[str], cursor: int,
                body: List[str]) -> int:
    for line in body:
        tag, content = line[:1], line[1:]
        if tag == "+":
            out.append(content)
        elif tag == "-":
            _verify(source, cursor, content)
            cursor += 1
        else:                       # context line (leading space)
            _verify(source, cursor, content)
            out.append(source[cursor])
            cursor += 1
    return cursor


def _read_hunk(lines: List[str], index: int, old_left: int,
               new_left: int) -> Tuple[List[str], int]:
    """The hunk body starting at ``index``, read by the header's line counts.

    Counting is what tells a removed ``-- comment`` line (``--- comment``)
    or an added ``++x`` line from a file header; skipping every line that
    starts with ``---`` / ``+++`` dropped them. ``\\`` marker lines are
    skipped.
    """
    body: List[str] = []
    while index < len(lines) and (old_left > 0 or new_left > 0):
        line = lines[index]
        index += 1
        tag = line[:1]
        if tag == "\\":
            continue
        old_left -= tag != "+"
        new_left -= tag != "-"
        body.append(line)
    while index < len(lines) and lines[index].startswith("\\"):
        index += 1
    return body, index


def _hunk_start(match: "re.Match") -> int:
    """0-based source line the hunk starts at.

    ``-N,0`` (a pure insertion, from ``-U0`` diffs) means "after line N",
    so it starts at N, not N - 1.
    """
    old_start = int(match.group(1))
    return old_start if match.group(2) == "0" else old_start - 1


def apply_unified(text: str, diff: str) -> str:
    """Apply a unified ``diff`` to ``text``; raise on context mismatch."""
    source = text.splitlines()
    out: List[str] = []
    cursor = 0
    lines = diff.splitlines()
    index = 0
    while index < len(lines):
        match = _HUNK_RE.match(lines[index])
        if match is None:
            index += 1
            continue
        start = _hunk_start(match)
        out.extend(source[cursor:start])
        cursor = max(cursor, start)
        body, index = _read_hunk(lines, index + 1, int(match.group(2) or 1),
                                 int(match.group(4) or 1))
        cursor = _apply_hunk(source, out, cursor, body)
    out.extend(source[cursor:])
    trailing = "\n" if text.endswith("\n") else ""
    return "\n".join(out) + (trailing if out else "")


# --- three-way merge -------------------------------------------------------

def _changes(base: List[str], side: List[str]) -> List[Tuple[int, int, List[str]]]:
    matcher = difflib.SequenceMatcher(None, base, side, autojunk=False)
    return [(i1, i2, side[j1:j2])
            for tag, i1, i2, j1, j2 in matcher.get_opcodes() if tag != "equal"]


def _overlap(ours: List[Tuple], theirs: List[Tuple]) -> bool:
    """Whether two change lists touch the same base lines.

    Two insertions at the same point overlap too: which goes first is a
    decision, and diff3 reports it as a conflict.
    """
    for o_lo, o_hi, _ in ours:
        for t_lo, t_hi, _ in theirs:
            if (o_lo < t_hi and t_lo < o_hi) or o_lo == o_hi == t_lo == t_hi:
                return True
    return False


def _conflict_block(ours: str, theirs: str, size: int) -> str:
    head, mid, tail = "<" * size, "=" * size, ">" * size
    return f"{head} ours\n{ours}\n{mid}\n{theirs}\n{tail} theirs\n"


def three_way_merge(base: str, ours: str, theirs: str, *,
                    marker_size: int = 7) -> MergeResult:
    """Merge ``ours`` and ``theirs`` against ``base`` (line-based)."""
    if ours == theirs:
        return MergeResult(ours, conflicts=0, clean=True)
    if ours == base:
        return MergeResult(theirs, conflicts=0, clean=True)
    if theirs == base:
        return MergeResult(ours, conflicts=0, clean=True)
    base_lines = base.splitlines()
    ours_changes = _changes(base_lines, ours.splitlines())
    # A change both sides made identically is one change, not a conflict
    # (and not applied twice).
    theirs_changes = [change for change in _changes(base_lines, theirs.splitlines())
                      if change not in ours_changes]
    if _overlap(ours_changes, theirs_changes):
        return MergeResult(
            _conflict_block(ours, theirs, marker_size), conflicts=1, clean=False)
    merged: List[str] = []
    cursor = 0
    for low, high, replacement in sorted(ours_changes + theirs_changes):
        merged.extend(base_lines[cursor:low])
        merged.extend(replacement)
        cursor = high
    merged.extend(base_lines[cursor:])
    trailing = "\n" if base.endswith("\n") else ""
    return MergeResult("\n".join(merged) + (trailing if merged else ""),
                       conflicts=0, clean=True)
