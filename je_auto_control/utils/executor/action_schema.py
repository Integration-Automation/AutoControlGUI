"""
Structural validation for action lists.

Validates the outer shape (``[name]`` / ``[name, params]``), that names are in the
executor allowlist, and that flow-control nested bodies are themselves valid lists.
"""
from typing import Any, Iterable, Iterator, List, Tuple

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
    for trail, name in _iter_actions(actions, "root"):
        if not isinstance(name, str) or name not in known:
            raise AutoControlActionException(f"{trail}: unknown command {name!r}")


def unknown_command_names(actions: Any,
                          known_commands: Iterable[str]) -> List[str]:
    """Return every unrecognised command name in ``actions``, in order.

    Structural problems still raise, exactly as :func:`validate_actions` does;
    the only difference is that an unknown *name* is collected instead of
    ending the walk. A boundary that has to answer a caller — the REST API —
    reports the whole list, so a client fixes every typo in one round trip
    rather than one per request.
    """
    known = set(known_commands)
    unknown: List[str] = []
    for _trail, name in _iter_actions(actions, "root"):
        if isinstance(name, str) and name in known:
            continue
        label = name if isinstance(name, str) else repr(name)
        if label not in unknown:
            unknown.append(label)
    return unknown


def _iter_actions(actions: Any, trail: str) -> Iterator[Tuple[str, Any]]:
    """Yield ``(trail, command_name)`` for every action in the tree, in order.

    Structural problems raise as they are met, but whether the name is in the
    allowlist is left to the caller. That is what lets "reject the first
    unknown name" and "collect every unknown name" share one traversal — and,
    more importantly, one definition of where a nested action list may hide.

    Laziness is load-bearing: the caller inspects the name at the ``yield``
    before this walk goes on to check the params, so the order in which the
    two complaints surface is unchanged from when it was all one function.
    """
    if not isinstance(actions, list):
        raise AutoControlActionException(
            f"{trail}: action list must be a list, got {type(actions).__name__}"
        )
    for idx, action in enumerate(actions):
        node = f"{trail}[{idx}]"
        if not isinstance(action, list) or not 1 <= len(action) <= 2:
            raise AutoControlActionException(
                f"{node}: must be [name] or [name, params]"
            )
        yield node, action[0]
        if len(action) == 2 and not isinstance(action[1], (dict, list)):
            raise AutoControlActionException(
                f"{node}: params must be dict or list"
            )
        yield from _iter_nested_actions(action[0], action, node)


def _iter_nested_actions(name: Any, action: list,
                         trail: str) -> Iterator[Tuple[str, Any]]:
    """Yield the actions held in a flow-control command's nested body keys."""
    # ``name`` arrives unvalidated — the collector does not stop on a bad one —
    # and an unhashable name would blow up the two lookups below.
    if not isinstance(name, str):
        return
    if len(action) < 2 or not isinstance(action[1], dict):
        return
    params = action[1]
    for body_key in FLOW_BODY_KEYS.get(name, ()):
        body = params.get(body_key)
        if body is not None:
            yield from _iter_actions(body, f"{trail}.{body_key}")
    for list_key in FLOW_BRANCH_LIST_KEYS.get(name, ()):
        branches = params.get(list_key)
        # The visual builder may pass a JSON string, which the runtime parses
        # via _as_list. Leave that shape to the runtime rather than reject it.
        if not isinstance(branches, list):
            continue
        for idx, branch in enumerate(branches):
            yield from _iter_actions(branch, f"{trail}.{list_key}[{idx}]")


__all__ = [
    "FLOW_BODY_KEYS", "FLOW_BRANCH_LIST_KEYS",
    "validate_actions", "unknown_command_names",
]
