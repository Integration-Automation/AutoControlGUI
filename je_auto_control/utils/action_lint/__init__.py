"""Phase 9.2: linter + JSON Schema generator for action JSON files.

The executor's dispatch table is the source of truth. This module
walks it to produce two artefacts:

  * ``build_action_schema()`` — a JSON Schema (draft 2020-12) listing
    every known ``AC_*`` command as a tuple variant
    ``[command_name, params_object]``. Editors that speak JSON Schema
    (VS Code, JetBrains, Neovim's coc-json) get autocomplete +
    inline validation for free.

  * :class:`ActionLinter` — programmatic linter. ``lint_actions(...)``
    returns a list of :class:`LintIssue`. The CLI entry point
    ``python -m je_auto_control.utils.action_lint <file.json>`` exits
    non-zero on the first issue, so CI can just call it.

A reusable GitHub Actions workflow ships at
``.github/workflows/action-json-lint.yml`` — drop this repo into a
project that hosts AutoControl action JSON and you get PR-level
validation for free.
"""
from je_auto_control.utils.action_lint.linter import (
    ActionLinter, LintIssue, LintSeverity, lint_actions,
)
from je_auto_control.utils.action_lint.schema import (
    build_action_schema, render_schema_json,
)

__all__ = [
    "ActionLinter", "LintIssue", "LintSeverity", "lint_actions",
    "build_action_schema", "render_schema_json",
]
