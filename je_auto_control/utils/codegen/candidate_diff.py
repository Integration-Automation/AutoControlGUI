"""What a candidate script would change: a unified diff against what is already there.

A candidate built from an action journal replaces something -- the action list
open in the recording editor, or a script file exported earlier. Before it
does, :func:`diff_candidate` says what would change, as a unified diff with
counts, so the replacement is reviewed instead of taken on trust.

Two things can be compared, matching the two forms a
:class:`~je_auto_control.utils.codegen.journal_import.CandidateScript` carries:

* its **action list** against another action list (:func:`diff_actions`), one
  action per line when it fits, indented JSON when it nests a body;
* its **code** against other source text (:func:`diff_code`).

Nothing here reads the journal or executes anything.
"""
import difflib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Union

from je_auto_control.utils.codegen.journal_import import CandidateScript, JournalImportError
from je_auto_control.utils.json.json_file import read_action_json

#: An action longer than this as one line is shown as indented JSON instead.
_ONE_LINE_LIMIT = 100


@dataclass(frozen=True)
class CandidateDiff:
    """A unified diff and its totals.

    ``kind`` is ``"actions"`` or ``"code"``. ``text`` is empty when the two
    sides are identical; ``added`` / ``removed`` count changed lines, not the
    diff's headers.
    """

    kind: str
    text: str
    added: int
    removed: int
    before_label: str = "current"
    after_label: str = "candidate"

    @property
    def identical(self) -> bool:
        """Whether the candidate changes nothing."""
        return self.added == 0 and self.removed == 0

    def to_dict(self) -> Dict[str, Any]:
        """The diff as a JSON-ready dict."""
        return {"kind": self.kind, "text": self.text, "added": self.added, "removed": self.removed,
                "identical": self.identical, "before": self.before_label, "after": self.after_label}


def action_lines(actions: Sequence[Any]) -> List[str]:
    """Render an action list as the lines a diff compares.

    Keys are sorted so two equal actions always render the same; an action
    that nests other actions is spread over several lines, so a change deep
    in a loop body shows as that line and not as the whole loop.
    """
    lines: List[str] = []
    for action in actions:
        compact = json.dumps(action, ensure_ascii=False, sort_keys=True)
        if len(compact) <= _ONE_LINE_LIMIT:
            lines.append(compact)
        else:
            lines.extend(json.dumps(action, ensure_ascii=False, sort_keys=True, indent=2).splitlines())
    return lines


def _diff(kind: str, before: Sequence[str], after: Sequence[str],
          before_label: str, after_label: str, context: int) -> CandidateDiff:
    if context < 0:
        raise JournalImportError(f"diff context must not be negative, got {context}")
    rows = list(difflib.unified_diff(list(before), list(after), fromfile=before_label,
                                     tofile=after_label, lineterm="", n=context))
    body = rows[2:]         # after the "---" / "+++" headers
    added = sum(1 for row in body if row.startswith("+"))
    removed = sum(1 for row in body if row.startswith("-"))
    return CandidateDiff(kind, "\n".join(rows), added, removed, before_label, after_label)


def diff_actions(before: Sequence[Any], after: Sequence[Any], *, before_label: str = "current",
                 after_label: str = "candidate", context: int = 3) -> CandidateDiff:
    """Diff two action lists, ``before`` being what ``after`` would replace."""
    return _diff("actions", action_lines(before), action_lines(after), before_label, after_label, context)


def diff_code(before: str, after: str, *, before_label: str = "current",
              after_label: str = "candidate", context: int = 3) -> CandidateDiff:
    """Diff two source texts line by line, ``before`` being what ``after`` would replace."""
    return _diff("code", before.splitlines(), after.splitlines(), before_label, after_label, context)


def diff_candidate(candidate: CandidateScript, *, actions: Optional[Sequence[Any]] = None,
                   code: Optional[str] = None, before_label: str = "current",
                   context: int = 3) -> CandidateDiff:
    """Diff ``candidate`` against the action list or the code it would replace.

    Give exactly one of ``actions`` (compared with ``candidate.actions``) and
    ``code`` (compared with ``candidate.code``).
    """
    if (actions is None) == (code is None):
        raise JournalImportError("diff_candidate needs exactly one of actions= and code=")
    if actions is not None:
        return diff_actions(actions, candidate.actions, before_label=before_label, context=context)
    return diff_code(code or "", candidate.code, before_label=before_label, context=context)


def diff_candidate_against_file(candidate: CandidateScript, path: Union[str, Path], *,
                                context: int = 3) -> CandidateDiff:
    """Diff ``candidate`` against a file: a ``.json`` action file, or any other file as code.

    A missing file is an empty "before", so the diff is the whole candidate.
    """
    target = Path(path)
    label = str(target)
    if target.suffix.lower() == ".json":
        before = read_action_json(label) if target.is_file() else []
        return diff_candidate(candidate, actions=before, before_label=label, context=context)
    text = target.read_text(encoding="utf-8") if target.is_file() else ""
    return diff_candidate(candidate, code=text, before_label=label, context=context)


__all__ = [
    "CandidateDiff", "action_lines", "diff_actions", "diff_candidate",
    "diff_candidate_against_file", "diff_code",
]
