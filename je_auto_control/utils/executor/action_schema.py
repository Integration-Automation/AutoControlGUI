"""
Structural validation for action lists.

Validates the outer shape (``[name]`` / ``[name, params]``), that names are in the
executor allowlist, and that flow-control nested bodies are themselves valid lists.
"""
from typing import Any, Iterable, Set

from je_auto_control.utils.exception.exceptions import AutoControlActionException


FLOW_BODY_KEYS = {
    "AC_if_image_found": ("then", "else"),
    "AC_if_pixel": ("then", "else"),
    "AC_loop": ("body",),
    "AC_while_image": ("body",),
    "AC_retry": ("body",),
}


def validate_actions(actions: Any, known_commands: Iterable[str]) -> None:
    """Validate an action list recursively; raise on the first problem."""
    known = set(known_commands)
    _validate_list(actions, known, trail="root")


def _validate_list(actions: Any, known: Set[str], trail: str) -> None:
    if not isinstance(actions, list):
        raise AutoControlActionException(
            f"{trail}: action list must be a list, got {type(actions).__name__}"
        )
    for idx, action in enumerate(actions):
        _validate_single(action, known, f"{trail}[{idx}]")


def _validate_single(action: Any, known: Set[str], trail: str) -> None:
    if not isinstance(action, list) or not 1 <= len(action) <= 2:
        raise AutoControlActionException(
            f"{trail}: must be [name] or [name, params]"
        )
    name = action[0]
    if not isinstance(name, str) or name not in known:
        raise AutoControlActionException(f"{trail}: unknown command {name!r}")
    if len(action) == 2 and not isinstance(action[1], (dict, list)):
        raise AutoControlActionException(
            f"{trail}: params must be dict or list"
        )
    _validate_nested_bodies(name, action, known, trail)


def _validate_nested_bodies(name: str, action: list, known: Set[str], trail: str) -> None:
    if name not in FLOW_BODY_KEYS or len(action) < 2 or not isinstance(action[1], dict):
        return
    for body_key in FLOW_BODY_KEYS[name]:
        body = action[1].get(body_key)
        if body is None:
            continue
        _validate_list(body, known, f"{trail}.{body_key}")
