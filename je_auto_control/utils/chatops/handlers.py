"""Built-in handlers that wrap AutoControl actions for chat-ops use.

Each function takes ``(argv, context)`` and returns a
:class:`CommandResult`. Stitched into a :class:`CommandRouter` by
:func:`register_default_commands` so the bot ships with a usable set
of verbs out of the box (``/run``, ``/stop``, ``/scripts``, ``/status``,
``/screenshot``).

``/run`` is a stoppable run named ``chatops-<script>-<id>``: it is listed by
``AC_list_executions`` and ended by ``AC_stop_execution``, the MCP
``ac_stop_execution`` tool, the GUI's stop-all and ``/stop``. A stop-all that
names no run therefore also ends runs started from chat.
"""
from __future__ import annotations

import json
import os
import re
import tempfile
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from je_auto_control.utils.chatops.router import (
    ChatOpsError, CommandResult, CommandRouter,
)
from je_auto_control.utils.executor.run_control import (
    active_executions, current_stop_token, stop_execution, stoppable_run,
)

#: What the ``run_id`` of every run started by ``/run`` begins with.
CHATOPS_RUN_PREFIX = "chatops-"

_UNSAFE_ID_CHARS = re.compile(r"[^A-Za-z0-9_.-]+")


def chatops_run_id(script_name: str) -> str:
    """A new run id for a ``/run`` of ``script_name``: ``chatops-<stem>-<8 hex>``.

    The stem is reduced to letters, digits, ``_``, ``.`` and ``-`` so the id
    can be typed back as one word (``/stop <run-id>``); the suffix keeps two
    runs of the same script apart.
    """
    stem = _UNSAFE_ID_CHARS.sub("_", Path(script_name).stem).strip("_") or "script"
    return f"{CHATOPS_RUN_PREFIX}{stem[:40]}-{uuid.uuid4().hex[:8]}"


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
    """``/run <script-name>`` — execute one JSON action file as a stoppable run.

    The run is registered as ``chatops-<script>-<id>`` for as long as it
    lasts. Inside a run that is already stoppable (the GUI's Chat-Ops tab
    starts one for its own Stop command) it joins that run instead, so the
    stop that already existed keeps working.
    """
    if not argv:
        raise ChatOpsError("usage: /run <script-name>")
    if len(argv) > 1:
        raise ChatOpsError(
            "/run takes exactly one script name (quote names with spaces)",
        )
    root = _require_script_root(context)
    script_path = _resolve_script(root, argv[0])
    from je_auto_control.utils.executor.action_executor import execute_files
    from je_auto_control.utils.script_vars.execution import execution_scope
    run_id = None if current_stop_token() is not None else chatops_run_id(script_path.name)
    with stoppable_run(run_id) as token, execution_scope():  # one /run, one variable scope
        result = execute_files([str(script_path)])
    return CommandResult(
        text=f"ran {script_path.name}: {len(result)} action(s) executed",
        metadata={"script": str(script_path), "results": _safe(result),
                  "run_id": token.run_id},
    )


def cmd_stop(argv: List[str], context: Dict[str, Any]) -> CommandResult:
    """``/stop [run-id]`` — ask a stoppable run to stop.

    Without an argument only the runs ``/run`` started are asked (their ids
    begin with ``chatops-``); a run started elsewhere has to be named. The
    reply comes at once: a run ends at its next checkpoint, on its own thread.
    """
    if len(argv) > 1:
        raise ChatOpsError("usage: /stop [run-id]")
    named = argv[0] if argv else None
    user = context.get("slack_user")
    reason = f"stopped from chat by {user}" if user else "stopped from chat"
    active = [str(run["run_id"]) for run in active_executions()]
    asked = [run_id for run_id in _stop_targets(named, active)
             if stop_execution(run_id, reason=reason)]
    metadata = {"stopped": asked, "active": active}
    if asked:
        return CommandResult(text="stop requested: " + ", ".join(asked), metadata=metadata)
    return CommandResult(text=_nothing_to_stop(named, active), succeeded=False,
                         metadata=metadata)


def _stop_targets(named: Optional[str], active: List[str]) -> List[str]:
    """The active runs ``/stop`` addresses: the one named, else the chat-started ones."""
    if named is not None:
        return [named] if named in active else []
    return [run_id for run_id in active if run_id.startswith(CHATOPS_RUN_PREFIX)]


def _nothing_to_stop(named: Optional[str], active: List[str]) -> str:
    """The reply when ``/stop`` found no run, naming the runs it did not touch."""
    what = (f"no run named {named!r} is in progress." if named is not None
            else "no chat-started run is in progress.")
    if not active:
        return what
    return f"{what} Other runs in progress: {', '.join(active)} (/stop <run-id>)."


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
        f"@ {row.started_at} ({_format_duration(row.duration_seconds)})"
        for row in rows
    ]
    return CommandResult(text="recent runs:\n" + "\n".join(lines))


def _format_duration(duration_seconds: Any) -> str:
    """Render a run duration, tolerating an in-flight/crashed run's ``None``.

    ``duration_seconds`` is ``None`` while a run is still going or when the
    process died before ``finish_run`` — formatting that with ``:.1f`` raised
    an uncaught ``TypeError`` that took the whole bot poll loop down.
    """
    if duration_seconds is None:
        return "in progress"
    return f"{duration_seconds:.1f}s"


def cmd_screenshot(argv: List[str],
                   context: Dict[str, Any]) -> CommandResult:
    """``/screenshot [name]`` — capture the screen and return the path.

    The file goes into ``context['screenshot_dir']`` (default: a
    ``je_auto_control_chatops`` folder in the temp directory); a given name
    keeps only its last component. The argument used to be a full path taken
    from the chat message, so anyone in the channel could write a PNG to any
    location the bot's account can write.
    """
    directory = Path(context.get("screenshot_dir")
                     or Path(tempfile.gettempdir()) / "je_auto_control_chatops")
    directory.mkdir(parents=True, exist_ok=True)
    if argv:
        name = Path(argv[0]).name
        if name in ("", ".", ".."):
            raise ChatOpsError(f"invalid screenshot name: {argv[0]!r}")
        target = directory / name
    else:
        target = Path(tempfile.NamedTemporaryFile(
            dir=directory, prefix="chatops_", suffix=".png", delete=False,
        ).name)
    from je_auto_control.wrapper.auto_control_screen import screenshot
    screenshot(file_path=str(target))
    return CommandResult(
        text=f"screenshot saved to {target}",
        artifact_path=str(target),
    )


def register_default_commands(router: CommandRouter) -> CommandRouter:
    """Register the five standard handlers in one call."""
    router.register("run", cmd_run,
                    description="Run a script under script_root.")
    router.register("stop", cmd_stop,
                    description="Stop the chat-started runs, or the run named.")
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
    "CHATOPS_RUN_PREFIX", "chatops_run_id",
    "cmd_run", "cmd_scripts", "cmd_screenshot", "cmd_status", "cmd_stop",
    "register_default_commands",
]
