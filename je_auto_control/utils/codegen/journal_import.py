"""Turn one run of an action journal into a candidate script for review.

The journal (``utils/action_journal``) holds what the executor ran. This reads
one run of it and rebuilds an action list from the *inputs* it recorded --
never from outcomes, never by evaluating text -- then renders it through the
existing :func:`~je_auto_control.utils.codegen.codegen.generate_code`.

What is rebuilt, and what is only observed:

* A top-level step is emitted as it was written, block body and all: the
  journal stored the whole ``AC_loop`` / ``AC_if_*`` / ``AC_parallel``, so its
  control flow is recovered, not guessed.
* Where the block itself cannot be rebuilt -- its start is not in the log, its
  arguments could not be stored, it calls a macro defined outside the run --
  the steps that actually ran beneath it are emitted in order instead, marked
  ``observed``, and the candidate says ``observed_path_only``: it replays the
  path this run took, not the script's logic. A branch that did not run is
  never invented.
* Inside an observed ``AC_retry`` only the last attempt is kept; the manifest
  counts the attempts.
* A masked secret is not replayable. Its place is taken by a
  ``${journal_redacted_N_M}`` reference, which fails as an unknown variable
  until it is replaced; a ``${secrets.NAME}`` reference in the journal is kept.

The candidate is checked without touching a device: the source is parsed, the
command names are looked up, and the action list goes through the executor's
dry run. Nothing is executed.

This module imports no ``PySide6``.
"""
import ast
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import (
    Any, Dict, FrozenSet, List, Mapping, Optional, Sequence, Set, Tuple, Union,
)

from je_auto_control.utils.action_journal.events import (
    SCHEMA_VERSION, STATUS_ERROR, STATUS_INCOMPLETE, STATUS_OK, ActionEvent,
    JournalFormatError,
)
from je_auto_control.utils.action_journal.sanitize import (
    REASON_MASKED, replace_unreplayable,
)
from je_auto_control.utils.action_journal.store import (
    JournalContents, list_journal_runs, load_journal,
)
from je_auto_control.utils.codegen.codegen import generate_code
from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils.json_store.json_store import atomic_write_text
from je_auto_control.utils.executor.action_schema import (
    FLOW_BODY_KEYS, FLOW_BRANCH_LIST_KEYS, unknown_command_names,
)

MODE_RECORDED = "recorded"
MODE_OBSERVED = "observed"
MODE_DETACHED = "detached"

_TARGETS = ("pytest", "python", "robot")
_STYLES = ("calls", "actions")
_MACRO_CALL = "AC_call_macro"
_MACRO_DEFINE = "AC_define_macro"
_RETRY = "AC_retry"


class JournalImportError(AutoControlException, ValueError):
    """The journal run cannot be turned into a candidate script."""


@dataclass(frozen=True)
class CandidateScript:
    """A generated script, where each step came from, and what to check.

    ``actions`` is the action list ``code`` replays -- what a recording
    editor or the Script Builder opens. ``observed_path_only`` is true when
    some control flow could not be rebuilt and the steps that ran stand in
    for it.
    """

    code: str
    manifest: Dict[str, Any]
    warnings: Tuple[str, ...] = ()
    actions: List[Any] = field(default_factory=list)
    observed_path_only: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """The candidate as a JSON-ready dict."""
        return {"code": self.code, "manifest": self.manifest,
                "warnings": list(self.warnings), "actions": self.actions,
                "observed_path_only": self.observed_path_only}


def _nesting_commands() -> FrozenSet[str]:
    """Commands whose arguments hold action lists the executor runs."""
    from je_auto_control.utils.executor.action_executor import Executor
    return frozenset(FLOW_BODY_KEYS) | frozenset(FLOW_BRANCH_LIST_KEYS) | frozenset(
        Executor._DEFERRED_COMMAND_KEYS) | {_MACRO_CALL}


class _Run:
    """One run's events as a tree, in the order they started."""

    def __init__(self, contents: JournalContents) -> None:
        self.events = contents.events
        self.lines = contents.lines
        self.children: Dict[str, List[ActionEvent]] = {}
        self.roots: List[ActionEvent] = []
        self.orphans: Set[str] = set()
        seen: Set[str] = set()
        for event in self.events:
            if event.parent_id is None:
                self.roots.append(event)
            elif event.parent_id in seen:
                self.children.setdefault(event.parent_id, []).append(event)
            else:
                # Its parent started before the journal did (or was lost).
                self.roots.append(event)
                self.orphans.add(event.step_id)
            seen.add(event.step_id)

    def detached(self, nesting: FrozenSet[str]) -> Set[str]:
        """Roots that ran on another thread *inside* a nesting root step.

        A runner that hands work to a thread pool (the DAG runner, a device
        matrix) records its steps without a parent. Emitting them next to the
        block that ran them would run them twice.
        """
        hosts = [root for root in self.roots
                 if root.command in nesting and root.finished_at is not None]
        return {root.step_id for root in self.roots for host in hosts
                if _inside(root, host)}


def _inside(event: ActionEvent, host: ActionEvent) -> bool:
    return (event is not host and event.thread != host.thread
            and host.started_at <= event.started_at
            and event.started_at <= (host.finished_at or 0.0))


def _attempts(parent: ActionEvent, children: Sequence[ActionEvent]
              ) -> List[List[ActionEvent]]:
    """The children of an ``AC_retry`` step, split into its attempts.

    The body runs strictly, so an attempt ends at its first failed step or
    after as many steps as the body holds.
    """
    body = parent.params.get("body") if isinstance(parent.params, dict) else None
    size = len(body) if isinstance(body, list) and body else len(children) or 1
    attempts: List[List[ActionEvent]] = [[]]
    for child in children:
        attempts[-1].append(child)
        if child.status != STATUS_OK or len(attempts[-1]) >= size:
            attempts.append([])
    return [attempt for attempt in attempts if attempt]


class _Builder:
    """Collects the candidate's actions, manifest steps and warnings."""

    def __init__(self, run: _Run) -> None:
        self.run = run
        self.nesting = _nesting_commands()
        self.detached = run.detached(self.nesting)
        self.actions: List[Any] = []
        self.steps: List[Dict[str, Any]] = []
        self.warnings: List[str] = []
        self.observed = False
        # Names as the journal recorded them: read from a file, so not known to be strings.
        self._macros: Set[object] = set()

    def build(self) -> None:
        """Walk every root step of the run."""
        for root in self.run.roots:
            if root.step_id in self.detached:
                self._note(root, MODE_DETACHED, emitted=False)
                self.warnings.append(
                    f"{self._where(root)} ran on another thread inside a block of this run "
                    "with no recorded parent; it is part of that block and is not emitted")
                continue
            self._emit(root, observed=root.step_id in self.run.orphans)
        self._summarise()

    def _where(self, event: ActionEvent) -> str:
        return f"line {self.run.lines.get(event.step_id, '?')} ({event.command})"

    def _note(self, event: ActionEvent, mode: str, emitted: bool,
              **extra: Any) -> None:
        self.steps.append({
            "step_id": event.step_id, "parent_id": event.parent_id,
            "line": self.run.lines.get(event.step_id), "sequence": event.sequence,
            "command": event.command, "status": event.status, "mode": mode,
            "emitted": emitted, "branch": event.branch,
            "action_index": len(self.actions) if emitted else None,
            "unreplayable": dict(event.unreplayable), **extra})

    def _unrecoverable(self, event: ActionEvent) -> Optional[str]:
        """Why ``event``'s own arguments cannot stand for what ran under it."""
        if event.command not in self.nesting:
            return None
        if event.command == _MACRO_CALL:
            name = event.params.get("name") if isinstance(event.params, dict) else None
            return None if name in self._macros else (
                f"macro {name!r} is not defined in this run")
        lost = [path for path, reason in event.unreplayable.items()
                if reason != REASON_MASKED]
        if lost:
            return f"{', '.join(sorted(lost))} could not be stored"
        return None

    def _emit(self, event: ActionEvent, observed: bool) -> None:
        children = self.run.children.get(event.step_id, [])
        reason = self._unrecoverable(event)
        if reason is not None and children:
            self._emit_observed_path(event, children, reason)
            return
        if reason is not None:
            self.warnings.append(
                f"{self._where(event)}: {reason}, and no step beneath it was recorded; "
                "emitted as written")
        if observed:
            self.observed = True
            self.warnings.append(
                f"{self._where(event)} ran inside a block the journal does not hold; "
                "emitted as an observed step")
        extra = {}
        if event.command == _RETRY:
            extra["attempts"] = len(_attempts(event, children))
        self._note(event, MODE_OBSERVED if observed else MODE_RECORDED, True, **extra)
        self.actions.append(self._action(event))
        self._remember_macro(event)

    def _emit_observed_path(self, event: ActionEvent, children: Sequence[ActionEvent],
                            reason: str) -> None:
        """Stand the steps that ran under ``event`` in for the block itself."""
        self.observed = True
        kept = list(children)
        extra: Dict[str, Any] = {}
        if event.command == _RETRY:
            attempts = _attempts(event, children)
            kept, extra["attempts"] = attempts[-1], len(attempts)
        self.warnings.append(
            f"{self._where(event)}: {reason}; its control flow is not rebuilt -- the "
            f"{len(kept)} step(s) that ran beneath it are emitted as the observed path")
        self._note(event, MODE_OBSERVED, False, **extra)
        for child in kept:
            self._emit(child, observed=True)

    def _remember_macro(self, event: ActionEvent) -> None:
        if event.command == _MACRO_DEFINE and isinstance(event.params, dict):
            self._macros.add(event.params.get("name"))

    def _action(self, event: ActionEvent) -> List[Any]:
        """The action ``event`` recorded, with unreplayable values made loud."""
        if event.params is None:
            return [event.command]
        index = len(self.actions)
        names: Dict[str, str] = {}

        def substitute(path: str) -> str:
            names[path] = f"journal_redacted_{index}_{len(names) + 1}"
            return "${" + names[path] + "}"

        params = replace_unreplayable(event.params, event.unreplayable, substitute)
        for path, name in names.items():
            self.warnings.append(
                f"{self._where(event)}: {path} is not replayable "
                f"({event.unreplayable[path]}); the candidate uses ${{{name}}} -- "
                "replace it (a ${secrets.NAME} reference for a secret) before running")
        return [event.command, params]

    def _summarise(self) -> None:
        emitted = [step for step in self.steps if step["emitted"]]
        for status, text in ((STATUS_ERROR, "failed"),
                             (STATUS_INCOMPLETE, "did not finish")):
            lines = [str(step["line"]) for step in emitted if step["status"] == status]
            if lines:
                self.warnings.append(
                    f"{len(lines)} emitted step(s) {text} in the recorded run "
                    f"(line {', '.join(lines)}); they are kept because they are the "
                    "script's input, not its result")


def _check_order(contents: JournalContents, warnings: List[str]) -> None:
    """Warn when a session's sequence numbers do not rise with the file."""
    last: Dict[str, int] = {}
    for event in contents.events:
        token = event.step_id.rpartition("-")[0]
        if event.sequence <= last.get(token, 0):
            warnings.append(
                f"line {contents.lines.get(event.step_id)}: sequence {event.sequence} "
                "is out of order; steps are taken in file order")
        last[token] = max(event.sequence, last.get(token, 0))
    if contents.torn_lines:
        warnings.append(
            "skipped unreadable line(s) "
            + ", ".join(str(number) for number in contents.torn_lines)
            + " (a write that was cut off)")


def _validate(code: str, actions: List[Any], target: str,
              warnings: List[str]) -> Dict[str, Any]:
    """Check the product without running it: syntax, command names, dry run."""
    from je_auto_control.utils.executor.action_executor import Executor
    checks: Dict[str, Any] = {"ast": None, "unknown_commands": [], "dry_run": None}
    if target != "robot":
        ast.parse(code)  # a SyntaxError here is a codegen defect; let it out
        checks["ast"] = True
    # A private executor: the dry run never touches the shared one's state.
    checker = Executor()
    unknown = unknown_command_names(actions, checker.known_commands())
    checks["unknown_commands"] = unknown
    if unknown:
        warnings.append(
            "unknown command(s) " + ", ".join(unknown)
            + " -- from a plugin that is not loaded here? The dry run was skipped")
        checks["dry_run"] = False
        return checks
    checks["dry_run"] = len(checker.execute_action(actions, dry_run=True)) == len(actions)
    return checks


def _script_name(run_id: str) -> str:
    return "journal_run_" + re.sub(r"\W+", "_", run_id)[:40]


def generate_candidate_from_log(path: Union[str, Path], *, run_id: str,
                                target: str = "pytest",
                                style: str = "actions") -> CandidateScript:
    """Build a reviewable candidate script from run ``run_id`` of a journal.

    ``target`` is ``pytest`` / ``python`` / ``robot`` and ``style`` ``actions``
    (embed the list, exact) or ``calls``, as for ``generate_code``. Raises
    :class:`JournalFormatError` for a file that is not a journal of this
    schema and :class:`JournalImportError` when the run holds nothing to
    emit. Nothing read from the log is executed.
    """
    if target not in _TARGETS:
        raise JournalImportError(f"unknown codegen target: {target!r}")
    if style not in _STYLES:
        raise JournalImportError(f"unknown codegen style: {style!r}")
    journal_path = os.path.realpath(os.fspath(path))
    contents = load_journal(journal_path, run_id=run_id)
    if not contents.events:
        raise JournalImportError(f"run {run_id!r} has no events in {journal_path}")
    builder = _Builder(_Run(contents))
    builder.build()
    if not builder.actions:
        raise JournalImportError(f"run {run_id!r} has no step that can be emitted")
    warnings = builder.warnings
    _check_order(contents, warnings)
    code = generate_code(builder.actions, target=target,
                         name=_script_name(run_id), style=style)
    manifest = {
        "schema_version": SCHEMA_VERSION, "journal": journal_path, "run_id": run_id,
        "target": target, "style": style, "event_count": len(contents.events),
        "action_count": len(builder.actions),
        "observed_path_only": builder.observed,
        "outcomes_used_as_input": False, "executed": False,
        "steps": builder.steps,
        "validation": _validate(code, builder.actions, target, warnings),
    }
    return CandidateScript(code=code, manifest=manifest, warnings=tuple(warnings),
                           actions=builder.actions, observed_path_only=builder.observed)


def only_run_id(path: Union[str, Path]) -> str:
    """The id of the journal's single run; raise when there is none or several."""
    runs = [run["run_id"] for run in list_journal_runs(os.path.realpath(os.fspath(path)))]
    if len(runs) != 1:
        raise JournalImportError(
            f"the journal holds {len(runs)} run(s); name one with run_id: "
            + (", ".join(runs) or "(none)"))
    return runs[0]


def write_candidate(candidate: CandidateScript, output: Union[str, Path],
                    manifest: Optional[Union[str, Path]] = None) -> Mapping[str, str]:
    """Write the candidate's code (and its manifest, when a path is given)."""
    written = {"output": os.path.realpath(os.fspath(output))}
    atomic_write_text(written["output"], candidate.code)
    if manifest:
        written["manifest"] = os.path.realpath(os.fspath(manifest))
        atomic_write_text(written["manifest"], json.dumps(
            {**candidate.manifest, "warnings": list(candidate.warnings)},
            ensure_ascii=False, indent=2))
    return written


__all__ = [
    "CandidateScript", "JournalFormatError", "JournalImportError",
    "generate_candidate_from_log", "only_run_id", "write_candidate",
]
