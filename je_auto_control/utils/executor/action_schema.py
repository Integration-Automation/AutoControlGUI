"""
Structural validation for action lists.

Validates the outer shape (``[name]`` / ``[name, params]``), that names are in the
executor allowlist, and that flow-control nested bodies are themselves valid lists.

Names a list brings in itself. ``AC_add_package_to_executor`` registers a
package's members as ``<package>_<member>`` commands when it runs, which is
after validation: a list that loaded a package and then used it was rejected
for an unknown command before its first action. A validator given a
``loadable`` predicate (the package gate's verdict, without importing
anything) therefore leaves such a name to run time -- but only a name that
starts with ``<package>_``, only after a load command that names that
package literally, earlier in the walk, and only if the gate would let the
load through. Every other unknown name is rejected up front as before, and
so is a deferred name that turns out not to exist, when its action runs.
"""
from typing import Any, Callable, Iterable, Iterator, List, Optional, Tuple

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
    "AC_run_stoppable": ("body",),
}

# Arguments a block command reads unconditionally (``args["key"]`` in its
# handler in flow_control.py); a missing one is a KeyError at run time.
# ``test_action_lint_blocks`` re-derives this table from the handlers' source
# so the two cannot drift apart.
BLOCK_REQUIRED_KEYS = {
    "AC_if_image_found": ("image",),
    "AC_if_pixel": ("x", "y", "rgb"),
    "AC_if_var": ("name",),
    "AC_wait_image": ("image",),
    "AC_wait_pixel": ("x", "y", "rgb"),
    "AC_sleep": ("seconds",),
    "AC_loop": ("times",),
    "AC_while_image": ("image",),
    "AC_while_var": ("name",),
    "AC_set_var": ("name",),
    "AC_get_var": ("name",),
    "AC_inc_var": ("name",),
    "AC_for_each": ("items",),
    "AC_define_macro": ("name",),
    "AC_call_macro": ("name",),
    "AC_read_file_to_var": ("path",),
    "AC_pdf_to_var": ("path",),
    "AC_otp_to_var": ("secret",),
    "AC_sql_to_var": ("database", "query"),
    "AC_assert_db": ("database", "query"),
    "AC_http_to_var": ("url",),
    "AC_transform_var": ("name",),
    "AC_assert_var": ("name",),
}

# Keys whose value is a LIST OF action lists — one nesting level deeper than
# FLOW_BODY_KEYS. Validating these as if they were flat would reject every
# valid action, since each element is itself a list rather than a name.
FLOW_BRANCH_LIST_KEYS = {
    "AC_parallel": ("branches",),
}


#: Commands that register a package's members on the executor when they run.
PACKAGE_LOAD_COMMANDS = frozenset({"AC_add_package_to_executor"})


class _SelfLoadedNames:
    """Command names the list being walked will register by loading a package."""

    def __init__(self, loadable: Optional[Callable[[str], bool]]) -> None:
        self._loadable = loadable
        self._prefixes: List[str] = []

    def note(self, name: Any, action: list) -> None:
        """Remember the package ``action`` loads, if it is a load the gate allows."""
        if self._loadable is None or name not in PACKAGE_LOAD_COMMANDS:
            return
        package = _literal_package(action)
        if package is not None and self._loadable(package):
            self._prefixes.append(package + "_")

    def covers(self, name: str) -> bool:
        """Whether ``name`` could be a member of a package loaded so far."""
        return any(name.startswith(prefix) and len(name) > len(prefix)
                   for prefix in self._prefixes)


def _literal_package(action: list) -> Optional[str]:
    """The package a load command names: ``[name, [pkg]]`` or ``[name, {"package": pkg}]``."""
    if len(action) != 2:
        return None
    params = action[1]
    if isinstance(params, dict):
        package = params.get("package")
    elif isinstance(params, list) and len(params) == 1:
        package = params[0]
    else:
        return None
    return package if isinstance(package, str) else None


def validate_actions(actions: Any, known_commands: Iterable[str],
                     loadable: Optional[Callable[[str], bool]] = None) -> None:
    """Validate an action list recursively; raise on the first problem.

    ``loadable`` says whether the package gate would let the list load a
    package; with it, names of a package the list itself loads earlier are
    left to run time (see the module docstring). Without it every name must
    be in ``known_commands``.
    """
    known = set(known_commands)
    self_loaded = _SelfLoadedNames(loadable)
    for trail, name, action in _iter_actions(actions, "root"):
        if not isinstance(name, str) or (name not in known and not self_loaded.covers(name)):
            raise AutoControlActionException(f"{trail}: unknown command {name!r}")
        self_loaded.note(name, action)


def unknown_command_names(actions: Any,
                          known_commands: Iterable[str],
                          loadable: Optional[Callable[[str], bool]] = None,
                          ) -> List[str]:
    """Return every unrecognised command name in ``actions``, in order.

    Structural problems still raise, exactly as :func:`validate_actions` does;
    the only difference is that an unknown *name* is collected instead of
    ending the walk. A boundary that has to answer a caller — the REST API —
    reports the whole list, so a client fixes every typo in one round trip
    rather than one per request. ``loadable`` is as in :func:`validate_actions`.
    """
    known = set(known_commands)
    self_loaded = _SelfLoadedNames(loadable)
    unknown: List[str] = []
    for _trail, name, action in _iter_actions(actions, "root"):
        if isinstance(name, str) and (name in known or self_loaded.covers(name)):
            self_loaded.note(name, action)
            continue
        label = name if isinstance(name, str) else repr(name)
        if label not in unknown:
            unknown.append(label)
    return unknown


def _iter_actions(actions: Any, trail: str) -> Iterator[Tuple[str, Any, list]]:
    """Yield ``(trail, command_name, action)`` for every action in the tree, in order.

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
        yield node, action[0], action
        if len(action) == 2 and not isinstance(action[1], (dict, list)):
            raise AutoControlActionException(
                f"{node}: params must be dict or list"
            )
        yield from _iter_nested_actions(action[0], action, node)


def _iter_nested_actions(name: Any, action: list,
                         trail: str) -> Iterator[Tuple[str, Any, list]]:
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
    "BLOCK_REQUIRED_KEYS",
    "FLOW_BODY_KEYS", "FLOW_BRANCH_LIST_KEYS", "PACKAGE_LOAD_COMMANDS",
    "validate_actions", "unknown_command_names",
]
