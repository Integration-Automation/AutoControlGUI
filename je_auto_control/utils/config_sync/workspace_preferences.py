"""Read and render a portable whitelist of native workspace preferences without importing Qt."""
from __future__ import annotations

from configparser import ConfigParser, Error as IniError
import json
from pathlib import Path
import sys
from types import MappingProxyType
from typing import Mapping, cast

from je_auto_control.utils.config_sync.contract import ConfigSyncError
from je_auto_control.utils.exception.control_signals import raise_caused_run_interruption

_DEFAULTS: Mapping[str, object] = MappingProxyType({
    'theme': 'dark', 'font_pt': 0, 'navigation_visible': True, 'navigation_width': 260,
})
_FONTS = frozenset({0, 10, 12, 14, 16, 20})
_MAX_INI_BYTES = 1024 * 1024
_CASE_INSENSITIVE = sys.platform == 'win32'


class _WorkspaceIni(ConfigParser):
    """Follow local native key case while using the bounded INI reader."""

    def optionxform(self, optionstr: str) -> str:
        """Normalize Windows INI keys and preserve Unix key spelling, matching QSettings."""
        return optionstr.casefold() if _CASE_INSENSITIVE else optionstr


def _coerce_preference(name: str, raw: object) -> object:
    """Match the GUI's tolerant native-setting defaults while retaining canonical scalar types."""
    if name == 'theme':
        return str(raw) if str(raw) in {'dark', 'light'} else _DEFAULTS[name]
    if name == 'navigation_visible':
        return str(raw).lower() not in {'false', '0'}
    try:
        number = int(cast(str, raw))
    except (ValueError, TypeError, OverflowError):
        return _DEFAULTS[name]
    valid = number in _FONTS if name == 'font_pt' else 200 <= number <= 1200
    return number if valid else _DEFAULTS[name]


def _validate_workspace_record(name: str, value: dict[str, object], *, deleted: bool = False) -> None:
    """Refuse unsupported keys and noncanonical remote values before causal profile I/O."""
    if name not in _DEFAULTS:
        raise ConfigSyncError('unsupported workspace preference key')
    if deleted and not value:
        return
    if set(value) != {'value'} or not _valid_preference(name, value['value']):
        raise ConfigSyncError('invalid workspace preference value or native type')


def _valid_preference(name: str, value: object) -> bool:
    if name == 'theme':
        return isinstance(value, str) and value in {'dark', 'light'}
    if name == 'navigation_visible':
        return isinstance(value, bool)
    if isinstance(value, bool) or not isinstance(value, int):
        return False
    return value in _FONTS if name == 'font_pt' else 200 <= value <= 1200


def _read_workspace_preferences(path: Path) -> dict[str, dict[str, object]]:
    """Read only explicitly stored portable workspace keys; missing files contain no local edits."""
    if not path.parent.is_dir():
        raise ConfigSyncError('workspace preference source parent directory is unavailable')
    if not path.exists():
        return {}
    try:
        with path.open('rb') as stream:
            data = stream.read(_MAX_INI_BYTES + 1)
        if len(data) > _MAX_INI_BYTES:
            raise ConfigSyncError('workspace preference file exceeds one MiB')
        parser = _WorkspaceIni(default_section='', interpolation=None, delimiters=('=',), empty_lines_in_values=False)
        parser.read_string(data.decode('utf-8-sig'))
    except IniError as error:
        raise_caused_run_interruption(error)
        raise ConfigSyncError('invalid workspace preference source file') from None
    except (OSError, UnicodeError) as error:
        raise ConfigSyncError('invalid workspace preference source file') from error
    section = _workspace_section(parser)
    return {name: {'value': _coerce_preference(name, _native_text(section[name]))}
            for name in _DEFAULTS if name in section}


def _workspace_section(parser: ConfigParser) -> Mapping[str, str]:
    names = [name for name in parser.sections()
             if (name.casefold() if _CASE_INSENSITIVE else name) == 'workspace']
    if len(names) > 1:
        raise ConfigSyncError('ambiguous native workspace section aliases')
    return parser[names[0]] if names else {}


def _native_text(value: str) -> str:
    if value.startswith('"') and value.endswith('"'):
        try:
            decoded = json.loads(value)
        except (ValueError, RecursionError):
            return value
        return decoded if isinstance(decoded, str) else value
    return value


def _workspace_ini(values: Mapping[str, dict[str, object]]) -> bytes:
    """Render complete inert native INI data, using safe defaults for absent or deleted preferences."""
    resolved = dict(_DEFAULTS)
    for name, record in values.items():
        _validate_workspace_record(name, record)
        resolved[name] = record['value']
    lines = ['[workspace]']
    for name in sorted(resolved):
        value = resolved[name]
        lines.append(name + '=' + (str(value).lower() if isinstance(value, bool) else str(value)))
    return ('\n'.join(lines) + '\n').encode('ascii')
