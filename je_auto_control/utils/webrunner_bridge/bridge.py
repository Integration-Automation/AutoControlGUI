"""Delegate ``WR_*`` browser-automation commands to ``je_web_runner``."""
from __future__ import annotations

from typing import Any, List, Mapping


class WebRunnerBridgeError(RuntimeError):
    """Raised when WebRunner isn't installed or a command is malformed."""


_HINT = (
    "je_web_runner is not installed. Install it from "
    "https://pypi.org/project/je-web-runner/ to enable AC_web_* commands."
)


def is_webrunner_available() -> bool:
    """True iff ``je_web_runner`` can be imported in the current process."""
    try:
        import je_web_runner  # noqa: F401
    except ImportError:
        return False
    return True


def _executor():
    try:
        from je_web_runner.utils.executor.action_executor import executor
    except ImportError as exc:  # pragma: no cover - optional dep
        raise WebRunnerBridgeError(_HINT) from exc
    return executor


def list_webrunner_commands() -> List[str]:
    """Sorted list of every ``WR_*`` command exposed by the bridge."""
    return sorted(
        name for name in _executor().event_dict
        if isinstance(name, str) and name.startswith("WR_")
    )


def run_webrunner_action(action: Mapping[str, Any]) -> Any:
    """Run one ``{"action": "WR_*", "params": {...}}`` action.

    Accepts the same shape the JSON action files use for AutoControl
    commands but with a ``WR_*`` name — the bridge unwraps it and
    dispatches through the WebRunner executor.
    """
    if not isinstance(action, Mapping):
        raise WebRunnerBridgeError(
            f"action must be a mapping, got {type(action).__name__}",
        )
    name = action.get("action")
    if not isinstance(name, str) or not name.startswith("WR_"):
        raise WebRunnerBridgeError(
            f"action name must start with WR_, got {name!r}",
        )
    params = action.get("params") or {}
    if not isinstance(params, Mapping):
        raise WebRunnerBridgeError("'params' must be a mapping")
    executor = _executor()
    callable_obj = executor.event_dict.get(name)
    if callable_obj is None:
        raise WebRunnerBridgeError(f"unknown WR_ command: {name}")
    try:
        return callable_obj(**dict(params))
    except TypeError as error:
        raise WebRunnerBridgeError(
            f"{name} rejected params: {error}",
        ) from error


def run_webrunner_actions(actions: List[Mapping[str, Any]]) -> List[Any]:
    """Run a list of WR_* actions in order. Stops at the first error."""
    if not isinstance(actions, list):
        raise WebRunnerBridgeError("actions must be a list")
    return [run_webrunner_action(a) for a in actions]


def web_open(url: str, browser: str = "chrome",
             **driver_kwargs: Any) -> Any:
    """Convenience: start a Selenium driver then navigate to ``url``.

    Equivalent to ``WR_get_webdriver_manager`` + ``WR_to_url`` in one
    call so JSON scripts and MCP clients can begin a browser flow
    without first looking up the WebRunner driver API.
    """
    if not isinstance(url, str) or not url.strip():
        raise WebRunnerBridgeError("web_open requires a non-empty url string")
    if not isinstance(browser, str) or not browser.strip():
        raise WebRunnerBridgeError("web_open requires a browser name")
    run_webrunner_action({
        "action": "WR_get_webdriver_manager",
        "params": {"webdriver_name": browser, **driver_kwargs},
    })
    return run_webrunner_action({
        "action": "WR_to_url", "params": {"url": url},
    })


def web_quit() -> Any:
    """Convenience: tear down every active WebRunner driver session."""
    return run_webrunner_action({"action": "WR_quit"})


def web_screenshot(file_path: str) -> Any:
    """Convenience: save a full-page screenshot of the active browser."""
    if not isinstance(file_path, str) or not file_path.strip():
        raise WebRunnerBridgeError(
            "web_screenshot requires a non-empty file_path",
        )
    return run_webrunner_action({
        "action": "WR_save_screenshot",
        "params": {"file_name": file_path},
    })


def web_current_url() -> Any:
    """Convenience: return the active browser tab's URL."""
    return run_webrunner_action({"action": "WR_get_current_url"})


__all__ = [
    "WebRunnerBridgeError", "is_webrunner_available",
    "list_webrunner_commands", "run_webrunner_action",
    "run_webrunner_actions", "web_current_url", "web_open",
    "web_quit", "web_screenshot",
]
