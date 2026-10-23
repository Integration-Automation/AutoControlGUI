"""Pinned browser completion clauses use fresh bounded SDK reads, never agent claims or previews."""
# pylint: disable=import-outside-toplevel  # reason: shared task policy and executor imports must stay cycle-free
from __future__ import annotations

from typing import Any, Mapping

from je_auto_control.utils.agent_runtime.browser_commands import _bounded, _url_origin, browser_session_scope
from je_auto_control.utils.agent_runtime.context import current_operation
from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from je_auto_control.utils.agent_runtime.models import AgentTaskSpec
from je_auto_control.utils.agent_runtime.target_config import browser_origins


def validate_browser_clause(clause: Mapping) -> None:
    """Accept only exact URL/text/value/visibility checks with finite typed locator data."""
    if set(clause) - {"kind", "operation", "selector", "frame", "value"}:
        raise AgentTaskError("browser completion contains unreviewed fields")
    operation = clause.get("operation")
    if not isinstance(operation, str) or operation not in {"url", "text", "value", "visible"}:
        raise AgentTaskError("browser completion requires url, text, value or visible")
    if operation == "url":
        if {"selector", "frame"} & set(clause):
            raise AgentTaskError("URL completion cannot contain a locator")
        _bounded(clause.get("value"), "completion URL", 4096)
        _url_origin(clause["value"])
        return
    _bounded(clause.get("selector"), "completion selector", 4096)
    _bounded(clause.get("frame", ""), "completion frame", 4096, empty=True)
    _expected_value(operation, clause.get("value"))


def _expected_value(operation: str, value: Any) -> None:
    if operation == "visible":
        if not isinstance(value, bool):
            raise AgentTaskError("visibility completion requires a boolean value")
        return
    _bounded(value, "completion value", 8000, empty=True)


def validate_browser_scope(spec: AgentTaskSpec, clause: Mapping) -> None:
    """Completion never adds a read permission, application or network origin to the task."""
    validate_browser_clause(clause)
    if "AC_browser_read" not in spec.allowed_tools or spec.apps:
        raise AgentTaskError("browser completion requires an explicit browser-read grant and no desktop apps")
    origins = browser_origins(spec.options.get("allowed_origins", ()))
    if clause["operation"] == "url" and _url_origin(clause["value"]) not in origins:
        raise AgentTaskError("browser completion URL exceeds task origins")


def evaluate_browser_clause(spec: AgentTaskSpec, session: Any, clause: Mapping) -> bool:
    """Read through the guarded leaf command and compare the full current result exactly."""
    from je_auto_control.utils.agent_runtime.policy import TaskPolicy
    from je_auto_control.utils.tool_use_schema import run_tool_call
    context = current_operation()
    if context is None or context.spec != spec:
        raise AgentTaskError("browser verification requires its owning task operation")
    context.checkpoint()
    validate_browser_scope(spec, clause)
    TaskPolicy(spec).check("AC_browser_read", {})
    current_url = session.url
    _bounded(current_url, "current URL", 4096)
    session.policy.require(current_url)
    if _url_origin(current_url) not in browser_origins(spec.options["allowed_origins"]):
        raise AgentTaskError("browser completion requires a current allowed HTTP(S) page")
    if clause["operation"] == "url":
        session.policy.require(clause["value"])
        result = current_url == clause["value"]
    else:
        with browser_session_scope(session):
            result = _read_condition(clause, run_tool_call)
    if session.url != current_url:
        raise AgentTaskError("browser page changed during completion verification")
    context.checkpoint()
    return result


def _read_condition(clause: Mapping, read: Any) -> bool:
    locator = {"selector": clause["selector"], "frame": clause.get("frame", "")}
    visible = read("AC_browser_read", {**locator, "operation": "visible"})
    if not isinstance(visible, bool):
        raise AgentTaskError("browser visibility readback is invalid")
    if clause["operation"] == "visible":
        return visible is clause["value"]
    if not visible:
        return False
    value = read("AC_browser_read", {**locator, "operation": clause["operation"]})
    _bounded(value, "verification readback", 8000, empty=True)
    return value == clause["value"]
