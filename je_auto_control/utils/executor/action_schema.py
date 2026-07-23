"""
Structural validation for action lists.

Validates the outer shape (``[name]`` / ``[name, params]``), that names are in the
executor allowlist, and that flow-control nested bodies are themselves valid lists.
"""
from typing import Any, Iterable, Set

from je_auto_control.utils.exception.exceptions import AutoControlActionException


# Every command that runs a nested action list must appear in one of the two
# maps below. The runners execute those bodies with ``_validated=True``,
# asserting someone already validated them — so a command missing from both
# has its body validated by nobody, and a malformed nested action surfaces as
# a raw IndexError at dispatch instead of a clean rejection.

# Keys whose value is a flat action list: [[name, params], ...]
FLOW_BODY_KEYS = {
    "AC_if_image_found": ("then", "else"),
    "AC_if_pixel": ("then", "else"),
    "AC_if_var": ("then", "else"),
    "AC_loop": ("body",),
    "AC_while_image": ("body",),
    "AC_while_var": ("body",),
    "AC_retry": ("body",),
    "AC_try": ("body", "catch", "finally"),
    "AC_for_each": ("body",),
    "AC_for_each_row": ("body",),
    "AC_assert_duration": ("body",),
    "AC_define_macro": ("body",),
}

# Keys whose value is a LIST OF action lists — one nesting level deeper than
# FLOW_BODY_KEYS. Validating these as if they were flat would reject every
# valid action, since each element is itself a list rather than a name.
FLOW_BRANCH_LIST_KEYS = {
    "AC_parallel": ("branches",),
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
    if len(action) < 2 or not isinstance(action[1], dict):
        return
    params = action[1]
    for body_key in FLOW_BODY_KEYS.get(name, ()):
        body = params.get(body_key)
        if body is not None:
            _validate_list(body, known, f"{trail}.{body_key}")
    for list_key in FLOW_BRANCH_LIST_KEYS.get(name, ()):
        _validate_branch_list(params.get(list_key), known, f"{trail}.{list_key}")


def _validate_branch_list(branches: Any, known: Set[str], trail: str) -> None:
    """Validate a list of action lists (e.g. ``AC_parallel``'s ``branches``)."""
    if branches is None:
        return
    # The visual builder may pass a JSON string, which the runtime parses via
    # _as_list. Leave that shape to the runtime rather than reject it here.
    if not isinstance(branches, list):
        return
    for idx, branch in enumerate(branches):
        _validate_list(branch, known, f"{trail}[{idx}]")
