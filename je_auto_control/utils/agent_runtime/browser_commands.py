"""Closed browser commands operate only inside an owned WebRunner helper session."""
# pylint: disable=import-outside-toplevel  # reason: optional SDK must stay lazy for Qt-free, SDK-free imports
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Iterator
import threading
import time

from je_auto_control.utils.agent_runtime.context import current_operation
from je_auto_control.utils.agent_runtime.errors import AgentTaskError, AgentHumanReview
from je_auto_control.utils.agent_runtime.policy import TaskPolicy

BROWSER_TOOLS = frozenset({"AC_browser_navigate", "AC_browser_click", "AC_browser_fill", "AC_browser_select",
                           "AC_browser_check", "AC_browser_read", "AC_browser_wait"})
BROWSER_ELEMENT_TOOLS = BROWSER_TOOLS - {"AC_browser_navigate"}
_SESSION: ContextVar[Any] = ContextVar("owned_managed_browser", default=None)


@contextmanager
def browser_session_scope(session: Any) -> Iterator[None]:
    """Bind a host-created SDK session for one helper dispatch, never from task arguments."""
    token = _SESSION.set(session)
    try:
        yield
    finally:
        _SESSION.reset(token)


def _bounded(value: str, name: str, maximum: int, *, empty: bool = False) -> None:
    if not isinstance(value, str) or len(value) > maximum or (not value and not empty):
        raise AgentTaskError(f"browser {name} must be bounded text")
    try:
        units = len(value.encode("utf-16-le")) // 2
    except UnicodeError:
        raise AgentTaskError("browser text contains invalid Unicode") from None
    if units > maximum:
        raise AgentTaskError(f"browser {name} exceeds its UTF-16 text limit")


def _execute(name: str, arguments: dict, operation: str, *, timeout: float | None = None) -> Any:
    context, session = current_operation(), _SESSION.get()
    if context is None or session is None:
        raise AgentTaskError("browser command requires its managed WebRunner session")
    context.checkpoint()
    TaskPolicy(context.spec).check(name, arguments)
    try:
        session.set_timeout(min(context.spec.budget.action_seconds, timeout) if timeout is not None
                            else context.spec.budget.action_seconds)
        result = _sdk_call(session, operation, arguments)
    except Exception as error:  # noqa: BLE001 - optional SDK errors have a separate exception hierarchy
        if getattr(error, "reason", "") == "human_review_required":
            raise AgentHumanReview("browser dialog requires human review") from None
        raise AgentTaskError("managed WebRunner operation failed; review its outcome") from None
    context.checkpoint()
    return result


def _sdk_call(session: Any, operation: str, arguments: dict) -> Any:
    if operation == "read":
        if "expected" in arguments and not session.visible(arguments["selector"], arguments["frame"]):
            return None
        functions = {"text": session.text, "value": session.read_value, "visible": session.visible}
        return functions[arguments["operation"]](arguments["selector"], arguments["frame"])
    try:
        from je_web_runner.api.ai import AgentAction
    except ImportError:
        raise AgentTaskError("installed je_web_runner with managed-session support is required") from None
    if operation == "navigate":
        action = AgentAction("navigate", value=arguments["url"])
    else:
        action = AgentAction(operation, selector=arguments["selector"], value=arguments.get("value", ""),
                             frame=arguments["frame"])
    session.perform(action)
    return True


def browser_navigate(url: str) -> bool:
    """Navigate once through the WebRunner origin fence in the current managed browser."""
    _bounded(url, "URL", 4096)
    return bool(_execute("AC_browser_navigate", {"url": url}, "navigate"))


def _element(name: str, operation: str, selector: str, frame: str, value: str = "") -> bool:
    _bounded(selector, "selector", 4096)
    _bounded(frame, "frame", 4096, empty=True)
    _bounded(value, "value", 8000, empty=True)
    return bool(_execute(name, {"selector": selector, "frame": frame, "value": value}, operation))


def browser_click(selector: str, frame: str = "") -> bool:
    """Click one unique visible enabled element once, without retrying submissions."""
    return _element("AC_browser_click", "click", selector, frame)


def browser_fill(selector: str, value: str, frame: str = "") -> bool:
    """Fill one unique element through the owned WebRunner session."""
    return _element("AC_browser_fill", "fill", selector, frame, value)


def browser_select(selector: str, value: str, frame: str = "") -> bool:
    """Select one option through the owned WebRunner session."""
    return _element("AC_browser_select", "select", selector, frame, value)


def browser_check(selector: str, frame: str = "") -> bool:
    """Check one unique enabled checkbox through the owned WebRunner session."""
    return _element("AC_browser_check", "check", selector, frame)


def browser_read(operation: str, selector: str, frame: str = "") -> Any:
    """Read visible text, non-secret form value or visibility without collecting screenshots."""
    if not isinstance(operation, str) or operation not in {"text", "value", "visible"}:
        raise AgentTaskError("browser read operation must be text, value or visible")
    _bounded(selector, "selector", 4096)
    _bounded(frame, "frame", 4096, empty=True)
    return _execute("AC_browser_read", {"operation": operation, "selector": selector, "frame": frame}, "read")


def browser_wait(operation: str, selector: str, expected: str, frame: str = "", timeout_seconds: float = 5) -> str:
    """Poll a read-only text/value postcondition; never repeat a click, fill or submission."""
    from je_auto_control.utils.agent_runtime.models import positive
    positive(timeout_seconds, "browser wait", 60)
    if not isinstance(operation, str) or operation not in {"text", "value"}:
        raise AgentTaskError("browser wait operation must be text or value")
    _bounded(selector, "selector", 4096)
    _bounded(frame, "frame", 4096, empty=True)
    _bounded(expected, "expected", 8000, empty=True)
    arguments = {"operation": operation, "selector": selector, "frame": frame, "expected": expected,
                 "timeout_seconds": timeout_seconds}
    context = current_operation()
    seconds = min(timeout_seconds, context.spec.budget.action_seconds) if context is not None else timeout_seconds
    deadline = time.monotonic() + seconds
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise AgentTaskError("browser read-back deadline exhausted")
        result = _execute("AC_browser_wait", arguments, "read", timeout=remaining)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise AgentTaskError("browser read-back deadline exhausted")
        if result == expected:
            return str(result)
        threading.Event().wait(min(.05, remaining))
