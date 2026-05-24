"""Built-in handlers that wrap AutoControl actions for chat-ops use.

Each function takes ``(argv, context)`` and returns a
:class:`CommandResult`. Stitched into a :class:`CommandRouter` by
:func:`register_default_commands` so the bot ships with a usable set
of verbs out of the box (``/run``, ``/scripts``, ``/status``,
``/screenshot``).
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, List

from je_auto_control.utils.chatops.router import (
    ChatOpsError, CommandResult, CommandRouter,
)


def _require_script_root(context: Dict[str, Any]) -> Path:
    raw = context.get("script_root") or os.environ.get(
        "JE_AUTOCONTROL_CHATOPS_SCRIPT_ROOT",
    )
    if not raw:
        raise ChatOpsError(
            "script_root not configured (set context['script_root'] or the "
            "JE_AUTOCONTROL_CHATOPS_SCRIPT_ROOT env var)",
        )
    root = Path(str(raw)).expanduser().resolve()
    if not root.is_dir():
        raise ChatOpsError(f"script_root {root!r} is not a directory")
    return root


def _resolve_script(root: Path, name: str) -> Path:
    """Resolve and verify ``name`` lives inside ``root`` (no traversal)."""
    candidate = (root / name).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as error:
        raise ChatOpsError(
            f"script {name!r} resolves outside script_root",
        ) from error
    if not candidate.is_file():
        raise ChatOpsError(f"script {name!r} not found under {root}")
    return candidate


def cmd_run(argv: List[str], context: Dict[str, Any]) -> CommandResult:
    """``/run <script-name>`` — execute one JSON action file."""
    if not argv:
        raise ChatOpsError("usage: /run <script-name>")
    if len(argv) > 1:
        raise ChatOpsError(
            "/run takes exactly one script name (quote names with spaces)",
        )
    root = _require_script_root(context)
    script_path = _resolve_script(root, argv[0])
    from je_auto_control.utils.executor.action_executor import execute_files
    result = execute_files([str(script_path)])
    return CommandResult(
        text=f"ran {script_path.name}: {len(result)} action(s) executed",
        metadata={"script": str(script_path), "results": _safe(result)},
    )


def cmd_scripts(_argv: List[str],
                context: Dict[str, Any]) -> CommandResult:
    """``/scripts`` — list every script available under the configured root."""
    root = _require_script_root(context)
    scripts = sorted(p.name for p in root.glob("*.json"))
    if not scripts:
        return CommandResult(text=f"no scripts found under {root}")
    body = "\n".join(f"  • {name}" for name in scripts)
    return CommandResult(text=f"scripts under {root}:\n{body}")


def cmd_status(_argv: List[str],
               _context: Dict[str, Any]) -> CommandResult:
    """``/status`` — show recent run-history rows + scheduler state."""
    from je_auto_control.utils.run_history.history_store import (
        default_history_store,
    )
    rows = default_history_store.list_runs(limit=5)
    if not rows:
        return CommandResult(text="no recent runs.")
    lines = [
        f"  [{row.status}] {row.source_type}:{row.source_id} "
        f"@ {row.started_at} ({row.duration_seconds:.1f}s)"
        for row in rows
    ]
    return CommandResult(text="recent runs:\n" + "\n".join(lines))


def cmd_screenshot(argv: List[str],
                   _context: Dict[str, Any]) -> CommandResult:
    """``/screenshot [path]`` — capture the screen and return the path."""
    target = Path(argv[0]).expanduser().resolve() if argv else Path(
        tempfile.NamedTemporaryFile(
            prefix="chatops_", suffix=".png", delete=False,
        ).name,
    )
    from je_auto_control.wrapper.auto_control_screen import screenshot
    screenshot(file_path=str(target))
    return CommandResult(
        text=f"screenshot saved to {target}",
        artifact_path=str(target),
    )


def register_default_commands(router: CommandRouter) -> CommandRouter:
    """Register the four standard handlers in one call."""
    router.register("run", cmd_run,
                    description="Run a script under script_root.")
    router.register("scripts", cmd_scripts,
                    description="List every script available to /run.")
    router.register("status", cmd_status,
                    description="Show recent run-history rows.")
    router.register("screenshot", cmd_screenshot,
                    description="Capture the screen to a file.")
    return router


def _safe(value: Any) -> Any:
    """Best-effort JSON-safe conversion for command metadata."""
    try:
        json.dumps(value)
        return value
    except (TypeError, ValueError):
        return repr(value)


__all__ = [
    "cmd_run", "cmd_scripts", "cmd_screenshot", "cmd_status",
    "register_default_commands",
]
