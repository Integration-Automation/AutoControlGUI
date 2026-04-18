"""Load ``AC_*`` callables from user-supplied Python plugin files.

A plugin file is any ``*.py`` containing top-level functions whose names
start with ``AC_``. Each such callable is registered into the executor's
``event_dict`` under its function name, so it becomes usable from JSON
action files and the socket/REST servers without any further plumbing.

Security: plugin files execute arbitrary Python — only load from a trusted
directory under the user's control.
"""
import importlib.util
import os
import pathlib
import uuid
from types import ModuleType
from typing import Dict, List

from je_auto_control.utils.logging.logging_instance import autocontrol_logger


def load_plugin_file(path: str) -> Dict[str, callable]:
    """Import ``path`` and return a mapping of ``AC_*`` callables it defines."""
    resolved = os.path.realpath(path)
    if not os.path.isfile(resolved):
        raise FileNotFoundError(f"plugin file not found: {resolved}")
    module = _import_isolated_module(resolved)
    return discover_plugin_commands(module)


def load_plugin_directory(directory: str) -> Dict[str, callable]:
    """Load every ``*.py`` in ``directory`` and merge their AC_* callables."""
    root = pathlib.Path(os.path.realpath(directory))
    if not root.is_dir():
        raise NotADirectoryError(f"plugin directory not found: {root}")
    merged: Dict[str, callable] = {}
    for file_path in sorted(root.glob("*.py")):
        if file_path.name.startswith("_"):
            continue
        try:
            commands = load_plugin_file(str(file_path))
        except (OSError, ImportError, SyntaxError) as error:
            autocontrol_logger.error("plugin %s failed to load: %r",
                                     file_path, error)
            continue
        merged.update(commands)
    return merged


def discover_plugin_commands(module: ModuleType) -> Dict[str, callable]:
    """Return every ``AC_*`` callable defined on ``module``."""
    commands: Dict[str, callable] = {}
    for attr_name in dir(module):
        if not attr_name.startswith("AC_"):
            continue
        attr = getattr(module, attr_name)
        if callable(attr):
            commands[attr_name] = attr
    return commands


def register_plugin_commands(commands: Dict[str, callable]) -> List[str]:
    """Register ``commands`` into the global executor and return their names."""
    from je_auto_control.utils.executor.action_executor import executor
    for name, func in commands.items():
        executor.event_dict[name] = func
    return sorted(commands.keys())


def _import_isolated_module(file_path: str) -> ModuleType:
    """Import a .py file without touching ``sys.modules`` namespace collisions."""
    module_name = f"je_auto_control_plugin_{uuid.uuid4().hex}"
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load plugin spec for {file_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
