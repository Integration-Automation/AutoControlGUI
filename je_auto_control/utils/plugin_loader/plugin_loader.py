"""Load ``AC_*`` callables from user-supplied Python plugin files.

A plugin file is any ``*.py`` containing top-level functions whose names
start with ``AC_``. Each such callable is registered into the executor's
``event_dict`` under its function name, so it becomes usable from JSON
action files and the socket/REST servers without any further plumbing.

Security: plugin files execute arbitrary Python — only load from a trusted
directory under the user's control. A plugin cannot replace a built-in
command (``AC_click_mouse`` and the like) unless the caller opts in.
"""
import importlib.util
import os
import pathlib
import sys
import types
import uuid
from types import ModuleType
from typing import Any, Callable, Dict, List, Set

from je_auto_control.utils.logging.logging_instance import autocontrol_logger


def load_plugin_file(path: str) -> Dict[str, Callable[..., Any]]:
    """Import ``path`` and return a mapping of ``AC_*`` callables it defines."""
    resolved = os.path.realpath(path)
    if not os.path.isfile(resolved):
        raise FileNotFoundError(f"plugin file not found: {resolved}")
    module = _import_isolated_module(resolved)
    return discover_plugin_commands(module)


def _inside(root: pathlib.Path, file_path: pathlib.Path) -> bool:
    """Whether ``file_path`` resolves to a file under ``root``."""
    resolved = os.path.realpath(file_path)
    try:
        return os.path.commonpath([str(root), resolved]) == str(root)
    except ValueError:  # another drive
        return False


def load_plugin_directory(directory: str) -> Dict[str, Callable[..., Any]]:
    """Load every ``*.py`` in ``directory`` and merge their AC_* callables."""
    root = pathlib.Path(os.path.realpath(directory))
    if not root.is_dir():
        raise NotADirectoryError(f"plugin directory not found: {root}")
    merged: Dict[str, Callable[..., Any]] = {}
    for file_path in sorted(root.glob("*.py")):
        if file_path.name.startswith("_"):
            continue
        if not _inside(root, file_path):
            # A symlink to /tmp/x.py was imported (run) like any plugin.
            autocontrol_logger.error("plugin %s resolves outside %s; skipped",
                                     file_path, root)
            continue
        try:
            commands = load_plugin_file(str(file_path))
        except Exception as error:  # noqa: BLE001  # reason: plugin code is untrusted and may raise anything; one broken file must not stop the rest of the directory loading
            autocontrol_logger.error("plugin %s failed to load: %r",
                                     file_path, error)
            continue
        merged.update(commands)
    return merged


def discover_plugin_commands(module: ModuleType) -> Dict[str, Callable[..., Any]]:
    """Return every ``AC_*`` callable defined on ``module``."""
    commands: Dict[str, Callable[..., Any]] = {}
    for attr_name in dir(module):
        if not attr_name.startswith("AC_"):
            continue
        attr = getattr(module, attr_name)
        if callable(attr):
            commands[attr_name] = attr
    return commands


#: Command names a plugin registered; a plugin may replace these (a reload),
#: but not a command that was there before any plugin.
_PLUGIN_OWNED: Set[str] = set()


def register_plugin_commands(commands: Dict[str, Callable[..., Any]], *,
                             allow_override: bool = False) -> List[str]:
    """Register ``commands`` into the global executor and return the names registered.

    A name that is not a string, a value that is not a function or method,
    and -- unless ``allow_override`` -- a name that already belongs to a
    built-in or user command are skipped and logged: a plugin defining
    ``AC_click_mouse`` silently replaced the real one.
    """
    from je_auto_control.utils.executor.action_executor import executor
    registered: List[str] = []
    for name, func in commands.items():
        reason = _refusal(name, func, executor.event_dict, allow_override)
        if reason:
            autocontrol_logger.warning("plugin command %r skipped: %s", name, reason)
            continue
        executor.event_dict[name] = func
        _PLUGIN_OWNED.add(name)
        registered.append(name)
    return sorted(registered)


def _refusal(name: Any, func: Any, event_dict: Dict[str, Any], allow_override: bool) -> str:
    """Why ``name`` / ``func`` cannot be registered, or ``""``."""
    if not isinstance(name, str) or not name:
        return "the name is not a string"
    if not isinstance(func, (types.FunctionType, types.MethodType)):
        return f"{type(func).__name__} is not a function"
    if name in event_dict and name not in _PLUGIN_OWNED and not allow_override:
        return "it would replace a built-in command"
    from je_auto_control.utils.executor.flow_control import BLOCK_COMMANDS
    if name in BLOCK_COMMANDS:
        # The executor looks block commands up first, so such a plugin was
        # "registered" and never ran -- allow_override cannot change that.
        return "it is the name of a block command"
    return ""


def _import_isolated_module(file_path: str) -> ModuleType:
    """Import a .py file under a unique module name.

    The module is in ``sys.modules`` while it executes -- ``dataclasses``
    (with postponed annotations) looks its module up there -- and stays
    there, as imported modules do; the UUID name keeps files apart.
    """
    module_name = f"je_auto_control_plugin_{uuid.uuid4().hex}"
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load plugin spec for {file_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(module_name, None)
        raise
    return module
