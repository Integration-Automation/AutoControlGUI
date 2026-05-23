"""Programmatic linter — what the GitHub Actions workflow shells out to."""
from __future__ import annotations

import inspect
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence


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


class ActionLinter:
    """Walks an action JSON document and reports issues."""

    def __init__(self,
                 *, known_commands: Optional[Dict[str, Any]] = None) -> None:
        self._commands = (
            known_commands if known_commands is not None else _ac_callables()
        )

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

    def _lint_item(self, idx: int, item: Any) -> List[LintIssue]:
        if not isinstance(item, (list, tuple)):
            return [LintIssue(
                idx, LintSeverity.ERROR, "bad-shape",
                "action item must be a list [command_name, params]",
            )]
        if not item:
            return [LintIssue(
                idx, LintSeverity.ERROR, "empty-action",
                "action item is empty",
            )]
        name = item[0]
        params = item[1] if len(item) >= 2 else {}
        if not isinstance(name, str):
            return [LintIssue(
                idx, LintSeverity.ERROR, "bad-name",
                f"command name must be a string, got {type(name).__name__}",
            )]
        if name not in self._commands:
            return [LintIssue(
                idx, LintSeverity.ERROR, "unknown-command",
                f"unknown command {name!r}",
            )]
        if params and not isinstance(params, dict):
            return [LintIssue(
                idx, LintSeverity.ERROR, "bad-params",
                "second element must be a JSON object (dict) of kwargs",
            )]
        return self._check_required(idx, name, params or {})

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
            actions = json.loads(target.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
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
