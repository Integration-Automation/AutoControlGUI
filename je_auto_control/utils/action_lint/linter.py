"""Programmatic linter — what the GitHub Actions workflow shells out to."""
from __future__ import annotations

import inspect
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set

from je_auto_control.utils.executor.action_schema import (
    BLOCK_REQUIRED_KEYS,
    FLOW_BODY_KEYS, FLOW_BRANCH_LIST_KEYS,
)


@dataclass
class LintSeverity:
    """Severity tags — stringly typed so CLI output stays plain text."""
    ERROR = "error"
    WARNING = "warning"


@dataclass
class LintIssue:
    """One linter finding."""
    index: int
    severity: str
    code: str
    message: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "index": self.index, "severity": self.severity,
            "code": self.code, "message": self.message,
        }


def _ac_callables() -> Dict[str, Any]:
    from je_auto_control.utils.executor.action_executor import executor
    return {
        name: fn for name, fn in executor.event_dict.items()
        if isinstance(name, str) and name.startswith("AC_") and callable(fn)
    }


def _block_commands() -> Set[str]:
    """Flow-control commands (AC_loop, AC_if_*, AC_try...), which live outside event_dict."""
    from je_auto_control.utils.executor.action_executor import executor
    return set(executor._block_commands)


class ActionLinter:
    """Walks an action JSON document and reports issues."""

    def __init__(self,
                 *, known_commands: Optional[Dict[str, Any]] = None,
                 block_commands: Optional[Set[str]] = None) -> None:
        self._commands = (
            known_commands if known_commands is not None else _ac_callables()
        )
        # Block commands used to be reported as unknown, so AC_loop, AC_try,
        # AC_if_* and the rest failed a valid file; their bodies go unchecked
        # too, so a typo inside a loop passed.
        if block_commands is not None:
            self._blocks = set(block_commands)
        else:
            self._blocks = _block_commands() if known_commands is None else set()

    def lint_actions(self,
                     actions: Sequence[Any]) -> List[LintIssue]:
        """Return every issue found in ``actions``.

        ``actions`` should be a list-of-lists, the same shape as the
        on-disk action JSON. Non-list inputs immediately fail.
        """
        if not isinstance(actions, list):
            return [LintIssue(
                index=-1, severity=LintSeverity.ERROR,
                code="not-a-list",
                message="action file root must be a list of [name, params]",
            )]
        issues: List[LintIssue] = []
        for idx, item in enumerate(actions):
            issues.extend(self._lint_item(idx, item))
        return issues

    def _lint_item(self, idx: int, item: Any, trail: str = "") -> List[LintIssue]:
        shape = self._shape_issue(item)
        if shape is not None:
            code, message = shape
            return [LintIssue(idx, LintSeverity.ERROR, code, trail + message)]
        name = item[0]
        params = item[1] if len(item) == 2 else {}
        if name in self._blocks:
            if not isinstance(params, dict):
                return [LintIssue(idx, LintSeverity.ERROR, "bad-params",
                                  f"{trail}{name} requires a dict of arguments")]
            # A block command's own arguments were never checked: AC_sleep
            # without "seconds" linted clean and raised KeyError when run.
            missing = [LintIssue(idx, LintSeverity.ERROR, "missing-param",
                                 f"{trail}{name} requires parameter {key!r}")
                       for key in BLOCK_REQUIRED_KEYS.get(name, ()) if key not in params]
            return missing + self._lint_bodies(idx, name, params, trail)
        if name not in self._commands:
            return [LintIssue(idx, LintSeverity.ERROR, "unknown-command",
                              f"{trail}unknown command {name!r}")]
        if isinstance(params, list):
            return []  # positional arguments, as the executor calls event(*args)
        return [LintIssue(i.index, i.severity, i.code, trail + i.message)
                for i in self._check_required(idx, name, params)]

    @staticmethod
    def _shape_issue(item: Any) -> Optional[tuple]:
        """``(code, message)`` when ``item`` is not ``[name]`` / ``[name, params]``."""
        if not isinstance(item, (list, tuple)):
            return "bad-shape", "action item must be a list [command_name, params]"
        if not item:
            return "empty-action", "action item is empty"
        if len(item) > 2:
            # The executor refuses a third element; the linter let it pass.
            return "bad-shape", "action item has more than [command_name, params]"
        if not isinstance(item[0], str):
            return "bad-name", f"command name must be a string, got {type(item[0]).__name__}"
        if len(item) == 2 and not isinstance(item[1], (dict, list)):
            # "" and other falsy non-dicts slipped past the old check.
            return "bad-params", "second element must be a JSON object or a list of arguments"
        return None

    def _lint_bodies(self, idx: int, name: str, params: Dict[str, Any],
                     trail: str) -> List[LintIssue]:
        """Lint the nested action lists a block command holds."""
        issues: List[LintIssue] = []
        bodies = [(key, params.get(key)) for key in FLOW_BODY_KEYS.get(name, ())]
        for key in FLOW_BRANCH_LIST_KEYS.get(name, ()):
            branches = params.get(key)
            if isinstance(branches, list):
                bodies.extend((f"{key}[{n}]", branch) for n, branch in enumerate(branches))
        for key, body in bodies:
            if not isinstance(body, list):
                continue
            for position, nested in enumerate(body):
                issues.extend(self._lint_item(idx, nested, f"{trail}{name}.{key}[{position}]: "))
        return issues

    def _check_required(self, idx: int, name: str,
                        params: Dict[str, Any]) -> List[LintIssue]:
        """Verify every required kwarg of the command is present."""
        callable_obj = self._commands[name]
        try:
            sig = inspect.signature(callable_obj)
        except (TypeError, ValueError):
            return []
        accepted, missing, accepts_kwargs = self._scan_signature(sig, params)
        unknown = (
            [p for p in params if p not in accepted]
            if not accepts_kwargs else []
        )
        issues: List[LintIssue] = [
            LintIssue(idx, LintSeverity.ERROR, "missing-param",
                      f"{name} requires parameter {m!r}")
            for m in missing
        ]
        issues.extend(
            LintIssue(idx, LintSeverity.WARNING, "unknown-param",
                      f"{name} has no parameter {u!r}")
            for u in unknown
        )
        return issues

    @staticmethod
    def _scan_signature(sig: inspect.Signature,
                         params: Dict[str, Any],
                         ) -> tuple:
        """Walk a Signature → (accepted_names, missing_required, accepts_kwargs)."""
        accepted: List[str] = []
        missing: List[str] = []
        accepts_kwargs = False
        for pname, param in sig.parameters.items():
            if pname == "self":
                continue
            if param.kind == inspect.Parameter.VAR_KEYWORD:
                accepts_kwargs = True
                continue
            if param.kind == inspect.Parameter.VAR_POSITIONAL:
                continue
            accepted.append(pname)
            if param.default is inspect.Parameter.empty and pname not in params:
                missing.append(pname)
        return accepted, missing, accepts_kwargs


def lint_actions(actions: Sequence[Any]) -> List[LintIssue]:
    """Convenience: ``ActionLinter().lint_actions(actions)``."""
    return ActionLinter().lint_actions(actions)


def _main(argv: Optional[List[str]] = None) -> int:
    """CLI entry point — ``python -m je_auto_control.utils.action_lint FILE``."""
    import sys
    args = list(argv if argv is not None else sys.argv[1:])
    if not args:
        print("usage: python -m je_auto_control.utils.action_lint FILE",
              file=sys.stderr)
        return 2
    exit_code = 0
    for path in args:
        target = Path(path)
        try:
            actions = json.loads(target.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError) as error:
            print(f"{target}: {error}", file=sys.stderr)
            exit_code = 1
            continue
        for issue in lint_actions(actions):
            print(
                f"{target}:{issue.index}: {issue.severity}: "
                f"{issue.code}: {issue.message}",
            )
            if issue.severity == LintSeverity.ERROR:
                exit_code = 1
    return exit_code


__all__ = [
    "ActionLinter", "LintIssue", "LintSeverity", "lint_actions",
]
