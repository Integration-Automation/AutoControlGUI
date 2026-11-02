"""A noninteractive target for rooted archive workflows, separate from desktop input."""
from __future__ import annotations

from typing import Any

from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from je_auto_control.utils.agent_runtime.models import AgentTaskSpec

FILE_TOOLS = frozenset({"AC_workflow_download", "AC_workflow_manifest"})


class FileTarget:
    """Operate only reviewed file tools, with no GUI, keyboard, mouse or shell access."""

    def ready(self, spec: AgentTaskSpec) -> tuple[bool, str]:
        """Require explicit roots and file-only commands before processing data."""
        return bool(spec.roots) and set(spec.allowed_tools) <= FILE_TOOLS, "file scope is unavailable"

    def observe(self) -> dict[str, Any]:
        """Return a stable noninteractive identity; data access occurs only in rooted actions."""
        return {"identity": "local-files", "elements": [], "semantic_observation": False, "text_redacted": True}

    def perform(self, name: str, arguments: dict[str, Any]) -> Any:
        """Use the same guarded raw-result executor as every other target."""
        if name not in FILE_TOOLS:
            raise AgentTaskError("command is not a reviewed file workflow")
        from je_auto_control.utils.tool_use_schema import run_tool_call
        return run_tool_call(name, arguments)

    def cleanup(self) -> None:
        """File operations hold no desktop input resources."""

    def validate_input(self, _event: dict) -> None:
        """Refuse any unexpected native input, including inside nested commands."""
        raise AgentTaskError("file tasks cannot drive native input")
