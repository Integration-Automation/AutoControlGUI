"""Reviewed semantic control and document operations within the current task's application scope."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from je_auto_control.utils.agent_runtime.workflow_files import task_policy

_SELECTORS = frozenset({"name", "role", "app_name", "automation_id"})
_DOCUMENTS = frozenset({".txt", ".csv", ".xlsx", ".docx", ".pdf", ".png", ".jpg", ".jpeg"})


def workflow_control(operation: str, selector: dict[str, Any], value: str = "") -> Any:
    """Read, set or invoke one uniquely identified semantic control, refusing password fields."""
    policy = task_policy()
    if not isinstance(selector, dict) or not selector or set(selector) - _SELECTORS:
        raise AgentTaskError("workflow control selector is invalid")
    if not selector.get("name"):
        raise AgentTaskError("workflow controls require a nonempty accessible name")
    if selector.get("app_name", "").casefold() not in {name.casefold() for name in policy.spec.apps}:
        raise AgentTaskError("workflow control application was not preauthorized")
    from je_auto_control.utils.accessibility import accessibility_api as api
    _unique_control(selector)
    state = api.control_get_state(**selector)
    if state is None or state.get("password"):
        raise AgentTaskError("workflow control state is unavailable or sensitive")
    functions = {"get": lambda: api.control_get_value(**selector),
                 "set": lambda: api.control_set_value(value, **selector),
                 "invoke": lambda: api.control_invoke(**selector), "state": lambda: state}
    if operation not in functions:
        raise AgentTaskError("unknown workflow control operation")
    task_policy()
    return functions[operation]()


def _unique_control(selector: dict[str, Any]) -> None:
    from je_auto_control.utils.accessibility import accessibility_api as api
    from je_auto_control.wrapper.auto_control_window import foreground_window_process_id, foreground_window
    foreground = foreground_window()
    if foreground is None:
        raise AgentTaskError("workflow foreground window is unavailable")
    nodes = api.list_accessibility_elements(app_name=selector["app_name"], window_title=foreground[1], max_results=500)
    filters = {key: item for key, item in selector.items() if key != "automation_id"}
    process_id = foreground_window_process_id()
    matches = [node for node in nodes if _matches(node, process_id, filters, selector)]
    if len(nodes) >= 500 or len(matches) != 1 or not matches[0].enabled:
        raise AgentTaskError("workflow control is ambiguous, unavailable or disabled")


def _native_id_matches(node: Any, selector: dict) -> bool:
    return "automation_id" not in selector or node.native_id == selector["automation_id"]


def _matches(node: Any, process_id: int | None, filters: dict, selector: dict) -> bool:
    from je_auto_control.utils.accessibility.element import element_matches
    return node.process_id == process_id and element_matches(node, **filters) and _native_id_matches(node, selector)


def workflow_open(path: str) -> bool:
    """Open one explicitly approved existing document with its registered application."""
    policy = task_policy()
    canonical = policy.path(path)
    if canonical not in policy.spec.options.get("approved_documents", ()):
        raise AgentTaskError("document launch was not preauthorized")
    document = Path(canonical)
    if document.suffix.lower() not in _DOCUMENTS or not document.is_file():
        raise AgentTaskError("workflow launch requires a supported existing document")
    from je_auto_control.utils.shell_open import open_path
    return bool(open_path(canonical))
