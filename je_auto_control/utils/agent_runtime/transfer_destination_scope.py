"""Injected destination profiles and live origin ceilings confine reviewed import directories."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from je_auto_control.utils.path_guard.path_guard import PathNotAllowedError, validate_path


def _directory(directory: str) -> None:
    if not isinstance(directory, str) or not directory or '\x00' in directory or not Path(directory).is_absolute():
        raise AgentTaskError('destination directory must be an absolute text path')


def destination_scope(profile: Callable, origins: Callable, target: str, directory: str, *,
                      reviewed: dict | None = None, connection: Any = None) -> dict:
    """Recheck host-owned scope without creating output or fabricating an ordinary agent task."""
    _directory(directory)
    configuration = profile(target, connection=connection)
    ceilings = origins(() if reviewed is None else reviewed['origins'])
    try:
        canonical = validate_path(directory, allowed_roots=configuration['roots'])
        for ceiling in ceilings:
            validate_path(canonical, allowed_roots=ceiling['roots'])
    except (PathNotAllowedError, OSError, ValueError) as error:
        raise AgentTaskError('destination directory is outside its current approved scope') from error
    current = {'directory': str(canonical), 'profile': {'name': target, 'digest': configuration['digest']},
               'origins': list(dict.fromkeys(ceiling['id'] for ceiling in ceilings))}
    if reviewed is not None:
        if current['directory'] != reviewed['directory'] or current['profile'] != reviewed['profile']:
            raise AgentTaskError('destination directory or profile changed; review is required')
    return current
