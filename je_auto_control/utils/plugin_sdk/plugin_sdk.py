"""Plugin SDK — discover and load third-party ``AC_*`` commands.

Turns the monolith into an ecosystem: a third-party pip package can register
new executor commands declaratively via a setuptools **entry point** in the
``je_auto_control.commands`` group, and AutoControl discovers them at runtime
(no path hacking, namespaced, install-time discoverable — distinct from the
runtime path loader). Each entry point loads to a *factory* returning a
``{command_name: callable}`` mapping, which is registered into the executor.

Pure standard library (``importlib.metadata``); imports no ``PySide6``. The
entry-point source is injectable, so discovery is unit-testable without
installing a real plugin.
"""
from typing import Any, Callable, Dict, List, Optional

COMMANDS_GROUP = "je_auto_control.commands"


def _entry_points(group: str) -> List[Any]:
    from importlib import metadata
    return list(metadata.entry_points(group=group))


def discover_plugins(group: str = COMMANDS_GROUP,
                     entry_points: Optional[List[Any]] = None
                     ) -> Dict[str, Callable[..., Any]]:
    """Return ``{command_name: handler}`` from every plugin entry point.

    Each entry point loads to a callable factory returning a command
    mapping; broken plugins are skipped (logged), not fatal. Pass
    ``entry_points`` to inject a fake source in tests.
    """
    points = entry_points if entry_points is not None else _entry_points(group)
    commands: Dict[str, Callable[..., Any]] = {}
    for point in points:
        try:
            factory = point.load()
            produced = factory()
        except (ImportError, AttributeError, TypeError, ValueError) as error:
            from je_auto_control.utils.logging.logging_instance import (
                autocontrol_logger)
            autocontrol_logger.warning(
                "plugin entry point %r failed: %r",
                getattr(point, "name", point), error)
            continue
        if isinstance(produced, dict):
            commands.update(produced)
    return commands


def load_plugins(group: str = COMMANDS_GROUP,
                 entry_points: Optional[List[Any]] = None) -> List[str]:
    """Discover plugin commands and register them into the executor.

    Returns the sorted names of the commands that were registered.
    """
    commands = discover_plugins(group, entry_points)
    if commands:
        from je_auto_control.utils.executor.action_executor import (
            add_command_to_executor)
        add_command_to_executor(commands)
    return sorted(commands)
