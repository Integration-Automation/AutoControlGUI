"""Explicit task scopes, rooted data paths and secret-safe durable payloads."""
from __future__ import annotations

from typing import Any, Mapping

from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from je_auto_control.utils.agent_runtime.models import AgentTaskSpec, detached
from je_auto_control.utils.path_guard.policy import PathPolicy
from je_auto_control.utils.path_guard.path_guard import PathNotAllowedError

_FORBIDDEN = ("AC_shell", "AC_execute_process", "AC_add_package", "AC_load_plugins", "AC_run_agent",
              "AC_computer_use", "AC_secret_", "AC_egress_", "AC_rest_api_", "AC_start_", "AC_stop_",
              "AC_agent_", "AC_webhook_", "AC_launch_process")
_PATH_NAMES = frozenset({"path", "file_path", "output_path", "source", "destination", "directory",
                         "root", "watch_path", "script_path", "bundle_path"})


class TaskPolicy:
    """Intersect offered tools and data roots without treating GUI control as an OS sandbox."""

    def __init__(self, spec: AgentTaskSpec) -> None:
        self.spec = spec
        self.paths = PathPolicy(spec.roots)
        if any(name.startswith(_FORBIDDEN) for name in spec.allowed_tools):
            raise AgentTaskError("tool is not allowed in the managed task profile")
        for criterion in spec.success_criteria:
            if criterion.get("kind", "").startswith("file_"):
                self.path(criterion.get("path"))
        for action in spec.actions:
            self.check(action.get("tool", ""), action.get("arguments", {}))

    def path(self, value: Any) -> str:
        """Canonicalize a task data path, refusing unrestricted or escaped paths."""
        if not self.spec.roots or not isinstance(value, str):
            raise AgentTaskError("file operations require explicit task roots")
        try:
            return str(self.paths.validate(value, operation="agent task root"))
        except (OSError, ValueError, PathNotAllowedError) as error:
            raise AgentTaskError("path is outside the allowed task roots") from error

    def check(self, name: str, arguments: Any) -> None:
        """Guard every resolved command, including commands nested in action scripts."""
        if name not in self.spec.allowed_tools:
            raise AgentTaskError(f"tool {name!r} is not allowed by this task")
        if not isinstance(arguments, Mapping):
            raise AgentTaskError("managed commands require named arguments")
        if any(not isinstance(key, str) or key.startswith("_") for key in arguments):
            raise AgentTaskError("private command arguments are not allowed")
        self._walk_paths(arguments)

    def _walk_paths(self, value: Any) -> None:
        if isinstance(value, Mapping):
            for key, item in value.items():
                if key in _PATH_NAMES and isinstance(item, str):
                    self.path(item)
                else:
                    self._walk_paths(item)
        elif isinstance(value, (tuple, list)):
            for item in value:
                self._walk_paths(item)


def durable_payload(value: Any) -> Any:
    """Snapshot JSON outcomes and scrub known secret values before durable publication."""
    from je_auto_control.utils.logging.secret_scope import scrub_secret_text
    value = detached(value)
    if isinstance(value, str):
        return scrub_secret_text(value)
    if isinstance(value, dict):
        return {scrub_secret_text(key): durable_payload(item) for key, item in value.items()}
    if isinstance(value, list):
        return [durable_payload(item) for item in value]
    return value
