"""Validate portable domain definitions without importing a backend or activating synchronized behavior."""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Callable, Literal, cast

from je_auto_control.utils.config_sync.adapter_references import _reference
from je_auto_control.utils.config_sync.asset_models import AssetFile
from je_auto_control.utils.config_sync.blob_binding import asset_reference
from je_auto_control.utils.config_sync.contract import ConfigSyncError, _encoded
from je_auto_control.utils.config_sync.outbox_models import normalize_sync_endpoint
from je_auto_control.utils.config_sync.workspace_preferences import _validate_workspace_record
from je_auto_control.utils.executor.action_schema import unknown_command_names, validate_actions
from je_auto_control.utils.exception.exceptions import AutoControlActionException

AdapterKind = Literal['scripts', 'locators', 'hotkeys', 'triggers', 'address_book', 'settings', 'workspace']
KINDS = frozenset({'scripts', 'locators', 'hotkeys', 'triggers', 'address_book', 'settings', 'workspace'})


@dataclass(frozen=True)
class ApplyReport:
    """Persisted definition IDs, unchanged IDs, conflicts and unresolved local names; no active runtime changes."""

    stored: tuple[str, ...]
    unchanged: tuple[str, ...]
    conflicts: tuple[str, ...]
    unresolved: tuple[str, ...]


def validate_record(kind: AdapterKind, entry_id: str, value: dict[str, object], *, deleted: bool = False) -> None:
    """Validate a domain record's exact schema, allowing typed references where a local value is required."""
    if kind not in KINDS or not isinstance(entry_id, str) or not entry_id or len(entry_id) > 512:
        raise ConfigSyncError('invalid adapter kind or definition ID')
    _encoded(value)
    if kind == 'workspace':
        _validate_workspace_record(entry_id, value, deleted=deleted)
        return
    if deleted and not value:
        return
    validators: dict[str, Callable[[str, dict[str, object]], None]] = {
        'scripts': _script, 'locators': _locator, 'hotkeys': _hotkey,
        'triggers': _trigger, 'address_book': _address, 'settings': _setting,
    }
    validators[kind](entry_id, value)


def _fields(value: dict[str, object], required: set[str], optional: frozenset[str] = frozenset()) -> None:
    if not required <= set(value) or not set(value) <= required | optional:
        raise ConfigSyncError('invalid adapter definition fields')


def _text(value: object, *, blank: bool = False) -> None:
    if _local_reference(value):
        return
    if not isinstance(value, str) or len(value) > 4096 or not (blank or value.strip()):
        raise ConfigSyncError('definition requires bounded text or a typed reference')


def _boolean(value: object) -> None:
    if _local_reference(value):
        return
    if not isinstance(value, bool):
        raise ConfigSyncError('definition flags must be JSON booleans')


def _number(value: object, minimum: float, maximum: float) -> None:
    if _local_reference(value):
        return
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigSyncError('definition requires a finite number')
    if not minimum <= value <= maximum or not math.isfinite(value):
        raise ConfigSyncError('definition number is outside its supported range')


def _script(entry_id: str, value: dict[str, object]) -> None:
    AssetFile(entry_id, '0' * 64, 0)
    if not entry_id.lower().endswith('.json'):
        raise ConfigSyncError('synced scripts require a relative JSON filename')
    _fields(value, {'actions'})
    try:
        names = unknown_command_names(value['actions'], ())
        validate_actions(value['actions'], names)
    except AutoControlActionException as error:
        raise ConfigSyncError('invalid synchronized action structure') from error
    if any(not name or not name.isprintable() or len(name) > 512 for name in names):
        raise ConfigSyncError('synchronized command names require bounded printable text')


def _locator(_entry_id: str, value: dict[str, object]) -> None:
    if not value or not set(value) <= {'name', 'role', 'app_name'}:
        raise ConfigSyncError('named accessibility locators require supported filter fields')
    for item in value.values():
        _text(item)


def _hotkey(_entry_id: str, value: dict[str, object]) -> None:
    _fields(value, {'combo', 'script_path'})
    _text(value['combo'])
    _file_text(value['script_path'])
    if not _local_reference(value['combo']) and not isinstance(value['combo'], str):
        raise ConfigSyncError('hotkey combination must be portable literal text')


_CONDITIONS: dict[str, set[str]] = {
    'file': {'watch_path'}, 'image': {'image_path', 'threshold'},
    'window': {'title_substring', 'case_sensitive'}, 'pixel': {'x', 'y', 'target_rgb', 'tolerance'},
    'cron': {'cron'},
}


def _trigger(_entry_id: str, value: dict[str, object]) -> None:
    _trigger_node(value, 0)


def _trigger_node(value: dict[str, object], depth: int) -> None:
    if depth > 16:
        raise ConfigSyncError('trigger definitions exceed the nesting limit')
    kind = value.get('kind')
    if not isinstance(kind, str) or kind not in _CONDITIONS.keys() | {'all', 'any', 'sequence'}:
        raise ConfigSyncError('unsupported synchronized trigger kind')
    composite = kind in {'all', 'any', 'sequence'}
    _fields(value, {'kind', 'script_path', 'repeat', 'cooldown_seconds', 'children' if composite else 'condition'})
    _file_text(value['script_path'], blank=True)
    _boolean(value['repeat'])
    _number(value['cooldown_seconds'], 0, 86400)
    if composite:
        _children(value['children'], depth)
    else:
        _condition(kind, value['condition'])


def _children(value: object, depth: int) -> None:
    if not isinstance(value, list) or not 1 <= len(value) <= 128:
        raise ConfigSyncError('composite triggers require a bounded nonempty child list')
    for child in value:
        if not isinstance(child, dict):
            raise ConfigSyncError('invalid child trigger definition')
        _trigger_node(child, depth + 1)


def _condition(kind: str, raw: object) -> None:
    if not isinstance(raw, dict):
        raise ConfigSyncError('trigger condition must be an object')
    _fields(raw, _CONDITIONS[kind])
    validators: dict[str, Callable[[dict[str, object]], None]] = {
        'file': lambda value: _text(value['watch_path']),
        'image': _image_condition, 'window': _window_condition, 'pixel': _pixel_condition,
        'cron': lambda value: _text(value['cron']),
    }
    validators[kind](raw)


def _image_condition(value: dict[str, object]) -> None:
    _file_text(value['image_path'])
    _number(value['threshold'], 0, 1)


def _window_condition(value: dict[str, object]) -> None:
    _text(value['title_substring'])
    _boolean(value['case_sensitive'])


def _pixel_condition(value: dict[str, object]) -> None:
    rgb = value['target_rgb']
    if not isinstance(rgb, list) or len(rgb) != 3:
        raise ConfigSyncError('pixel triggers require three RGB components')
    for item in (value['x'], value['y'], value['tolerance'], *rgb):
        if _local_reference(item):
            continue
        if isinstance(item, bool) or not isinstance(item, int):
            raise ConfigSyncError('pixel trigger coordinates and colors must be integers')
    _number(value['x'], -2**31, 2**31 - 1)
    _number(value['y'], -2**31, 2**31 - 1)
    for item in (value['tolerance'], *rgb):
        _number(item, 0, 255)


def _address(_entry_id: str, value: dict[str, object]) -> None:
    _fields(value, {'host_id', 'server_url', 'label', 'favorite', 'tags'})
    for field in ('host_id', 'server_url', 'label'):
        _text(value[field], blank=field == 'label')
    reference = _reference(value['server_url'])
    if reference is None:
        normalize_sync_endpoint(cast(str, value['server_url']))
    elif reference.kind != 'local':
        raise ConfigSyncError('address-book endpoints cannot embed vault credentials')
    _boolean(value['favorite'])
    tags = value['tags']
    if not isinstance(tags, list) or len(tags) > 128:
        raise ConfigSyncError('address-book tags require a bounded array')
    for tag in tags:
        _text(tag)


def _setting(_entry_id: str, value: dict[str, object]) -> None:
    _fields(value, {'value'})


def _local_reference(value: object) -> bool:
    reference = _reference(value)
    if reference is None:
        return False
    if reference.kind != 'local':
        raise ConfigSyncError('native definition fields require local references; vault interpolation is data-only')
    return True


def _file_text(value: object, *, blank: bool = False) -> None:
    if asset_reference(value) is None:
        _text(value, blank=blank)
