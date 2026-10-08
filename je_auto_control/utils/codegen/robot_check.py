"""A structural check of generated Robot Framework source.

**This is not the Robot Framework parser.** ``robotframework`` is not a
dependency of this package, so nothing here resolves a keyword, imports a
library or evaluates a variable. It reads the space-separated format line by
line and reports what would stop Robot from *loading* the file at all:

* text before the first section, an unknown section header, or no test case;
* a row in ``*** Settings ***`` / ``*** Variables ***`` that is indented, or a
  setting Robot does not have;
* a test or keyword with no body, two tests with one name, a body row with no
  owner, a body row indented by a single space (Robot reads that as a name);
* a body row with no keyword after an assignment, an unknown ``[Setting]``,
  an unclosed ``${`` / ``@{`` / ``&{`` / ``%{``, and ``FOR`` / ``IF`` /
  ``TRY`` / ``WHILE`` blocks that are not closed by ``END``.

A file that passes can still fail in Robot -- an unknown keyword, a wrong
argument count, a library that does not import. Run ``robot --dryrun`` for
that.

Pure standard library; imports no ``PySide6``.
"""
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

from je_auto_control.utils.exception.exceptions import AutoControlException

_SECTIONS = {
    "setting": "settings", "settings": "settings",
    "variable": "variables", "variables": "variables",
    "test case": "tests", "test cases": "tests", "task": "tests", "tasks": "tests",
    "keyword": "keywords", "keywords": "keywords",
    "comment": "comments", "comments": "comments",
}
_SETTINGS = frozenset({
    "documentation", "library", "resource", "variables", "metadata", "name",
    "suite setup", "suite teardown", "test setup", "test teardown", "task setup",
    "task teardown", "test template", "task template", "test timeout",
    "task timeout", "test tags", "task tags", "force tags", "default tags",
    "keyword tags",
})
_BODY_SETTINGS = frozenset({
    "documentation", "tags", "setup", "teardown", "template", "timeout",
    "arguments", "return",
})
_OPENERS = frozenset({"FOR", "IF", "TRY", "WHILE", "GROUP"})
#: Words that are a whole statement or branch marker, needing no keyword cell.
_MARKERS = frozenset({
    "END", "ELSE", "ELSE IF", "EXCEPT", "FINALLY", "BREAK", "CONTINUE", "RETURN",
    "VAR",
})
_HEADER = re.compile(r"^\*+\s*(.*?)\s*\**\s*$")
_CELLS = re.compile(r" {2,}|\t+")
_ASSIGNMENT = re.compile(r"^[$@&]\{[^{}]+\}\s?=?$")
_VARIABLE_NAME = re.compile(r"^[$@&]\{[^{}]+\}\s?=?$")
_SETTING_CELL = re.compile(r"^\[\s*(.+?)\s*\]$")
_CONTINUATION = "..."


class RobotStructureError(AutoControlException, ValueError):
    """Generated Robot source is not structured as a Robot suite file."""


@dataclass
class _Owner:
    """One test case or keyword: where it starts and what its body holds."""

    name: str
    line: int
    rows: int = 0
    open_blocks: List[int] = field(default_factory=list)


@dataclass
class _State:
    section: Optional[str] = None
    owner: Optional[_Owner] = None
    tests: Dict[str, int] = field(default_factory=dict)
    problems: List[str] = field(default_factory=list)

    def note(self, line: int, text: str) -> None:
        """Record one problem at ``line``."""
        self.problems.append(f"line {line}: {text}")

    def close_owner(self) -> None:
        """Finish the current test or keyword, reporting an empty or open body."""
        owner, self.owner = self.owner, None
        if owner is None:
            return
        if owner.rows == 0:
            self.note(owner.line, f"{owner.name!r} has no body")
        for opened in owner.open_blocks:
            self.note(opened, "block is not closed by END")


def _cells(text: str) -> List[str]:
    return [cell for cell in _CELLS.split(text.strip()) if cell != ""]


def _unbalanced_variable(cell: str) -> bool:
    """Whether ``cell`` opens a ``${`` / ``@{`` / ``&{`` / ``%{`` it never closes."""
    depth = 0
    index = 0
    while index < len(cell):
        char = cell[index]
        if char == "\\":
            index += 2
            continue
        if char in "$@&%" and cell[index + 1:index + 2] == "{":
            depth += 1
            index += 2
            continue
        if char == "}" and depth:
            depth -= 1
        index += 1
    return depth != 0


def _check_header(state: _State, number: int, text: str) -> None:
    match = _HEADER.match(text)
    name = (match.group(1) if match else "").lower()
    state.close_owner()
    state.section = _SECTIONS.get(name)
    if state.section is None:
        state.note(number, f"unknown section header {text.strip()!r}")
        state.section = "unknown"


def _check_table_row(state: _State, number: int, raw: str) -> None:
    """A row of ``*** Settings ***`` or ``*** Variables ***``."""
    if raw[:1] in " \t":
        state.note(number, f"a row in the {state.section} section may not be indented")
        return
    cells = _cells(raw)
    if cells[0] == _CONTINUATION:
        return
    if state.section == "settings" and cells[0].lower() not in _SETTINGS:
        state.note(number, f"unknown setting {cells[0]!r}")
    if state.section == "variables" and not _VARIABLE_NAME.match(cells[0]):
        state.note(number, f"{cells[0]!r} is not a variable name")


def _check_name_row(state: _State, number: int, raw: str) -> None:
    """A row at column 0 of a test or keyword section: the owner's name."""
    state.close_owner()
    name = raw.strip()
    state.owner = _Owner(name, number)
    if len(_cells(raw)) > 1:
        # Robot would read the further cells as the first body row.
        state.owner.rows += 1
    if state.section != "tests":
        return
    if name.lower() in state.tests:
        state.note(number, f"test case {name!r} is defined twice "
                           f"(first at line {state.tests[name.lower()]})")
    state.tests.setdefault(name.lower(), number)


def _check_blocks(owner: _Owner, state: _State, number: int, first: str) -> None:
    if first in _OPENERS:
        owner.open_blocks.append(number)
    elif first == "END":
        if owner.open_blocks:
            owner.open_blocks.pop()
        else:
            state.note(number, "END closes nothing")


def _check_body_cells(state: _State, number: int, cells: Sequence[str]) -> None:
    first = cells[0]
    setting = _SETTING_CELL.match(first)
    if setting is not None:
        if setting.group(1).lower() not in _BODY_SETTINGS:
            state.note(number, f"unknown setting {first!r}")
        return
    if first in _OPENERS or first in _MARKERS:
        return
    keyword = [cell for cell in cells if not _ASSIGNMENT.match(cell)]
    if not keyword:
        state.note(number, "an assignment is not followed by a keyword")


def _check_body_row(state: _State, number: int, raw: str) -> None:
    """An indented row of a test or keyword section: one step."""
    owner = state.owner
    indent = len(raw) - len(raw.lstrip(" \t"))
    if "\t" not in raw[:indent] and indent < 2:
        state.note(number, "a body row needs two or more spaces of indentation")
        return
    if owner is None:
        state.note(number, "a body row has no test case or keyword above it")
        return
    cells = _cells(raw)
    if cells[0] == _CONTINUATION:
        if owner.rows == 0:
            state.note(number, "a continuation row has nothing to continue")
        return
    owner.rows += 1
    _check_blocks(owner, state, number, cells[0])
    _check_body_cells(state, number, cells)


def _check_row(state: _State, number: int, raw: str) -> None:
    if state.section is None:
        state.note(number, "text before the first section header")
    elif state.section in ("settings", "variables"):
        _check_table_row(state, number, raw)
    elif state.section in ("tests", "keywords"):
        if raw[:1] in " \t":
            _check_body_row(state, number, raw)
        else:
            _check_name_row(state, number, raw)


def check_robot_structure(source: str) -> List[str]:
    """Problems that would stop Robot Framework loading ``source``; ``[]`` if none.

    A structural check of the space-separated format -- sections, indentation,
    keyword rows -- and **not** the Robot Framework parser: no keyword is
    resolved and no library imported. Each problem reads ``line N: ...``.
    """
    state = _State()
    for number, raw in enumerate(source.splitlines(), start=1):
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        if raw.startswith("*"):
            _check_header(state, number, raw)
            continue
        if state.section != "comments" and any(
                _unbalanced_variable(cell) for cell in _cells(raw)):
            state.note(number, "a variable is opened and never closed")
        _check_row(state, number, raw)
    state.close_owner()
    if not state.tests:
        state.problems.append("the file defines no test case")
    return state.problems


def require_robot_structure(source: str) -> None:
    """Raise :class:`RobotStructureError` if :func:`check_robot_structure` finds a problem."""
    problems = check_robot_structure(source)
    if problems:
        raise RobotStructureError(
            "generated Robot source is malformed: " + "; ".join(problems))


__all__ = ["RobotStructureError", "check_robot_structure", "require_robot_structure"]
