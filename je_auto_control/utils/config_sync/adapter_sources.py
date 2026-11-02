"""Capture actual domain sources as data, excluding runtime enablement, counters, credentials and device handles."""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
from typing import Mapping, Protocol, Sequence, cast

from je_auto_control.utils.config_sync.asset_models import AssetFile, AssetManifest
from je_auto_control.utils.config_sync.assets import _asset_path
from je_auto_control.utils.config_sync.contract import ConfigSyncError, _encoded


# pylint: disable-next=too-few-public-methods  # reason: a structural seam for the existing repository's one data view
class LocatorSource(Protocol):
    """The existing named locator repository's data-only seam."""

    def all(self) -> Mapping[str, Mapping[str, object]]:
        """Copy named native locator filters without querying a device."""


# pylint: disable-next=too-few-public-methods  # reason: a structural seam for registrations without backend control
class HotkeySource(Protocol):
    """The existing hotkey daemon's registration view; no backend listener is started."""

    def list_bindings(self) -> Sequence[object]:
        """Return registered binding definitions."""


# pylint: disable-next=too-few-public-methods  # reason: only the existing engine's data view is required
class TriggerSource(Protocol):
    """The existing engine's trigger view; reading it does not poll or arm a trigger."""

    def list_triggers(self) -> Sequence[object]:
        """Return trigger objects for definition capture."""


# pylint: disable-next=too-few-public-methods  # reason: saved-host data does not need connection methods
class AddressBookSource(Protocol):
    """The existing saved-address store's data-only seam."""

    def list_entries(self) -> Sequence[dict[str, object]]:
        """Copy saved address records without connecting to them."""


def read_json(path: Path) -> object:
    """Read one bounded JSON document, refusing damaged or oversized source data."""
    try:
        if not path.is_file() or path.stat().st_size > 1024 * 1024:
            raise ConfigSyncError('adapter source exceeds one MiB')
        with path.open('r', encoding='utf-8-sig') as stream:
            raw = stream.read(1024 * 1024 + 1)
        if len(raw.encode('utf-8')) > 1024 * 1024:
            raise ConfigSyncError('adapter source exceeds one MiB')
        return json.loads(raw)
    except (OSError, ValueError, RecursionError) as error:
        raise ConfigSyncError('adapter source could not be read as finite JSON') from error


def script_records(root: Path, paths: tuple[str, ...]) -> dict[str, dict[str, object]]:
    """Read selected real action files; a missing root is an error rather than mass deletion."""
    if not root.is_dir():
        raise ConfigSyncError('selected script root is not available')
    if paths:
        AssetManifest(tuple(AssetFile(name, '0' * 64, 0) for name in paths))
    result = {}
    for name in paths:
        path = _asset_path(root, AssetFile(name, '0' * 64, 0))
        if path.exists():
            result[name] = {'actions': read_json(path)}
    return result


def locator_records(source: LocatorSource) -> dict[str, dict[str, object]]:
    """Read native accessibility locator filters without importing a platform backend."""
    return {key: dict(value) for key, value in source.all().items()}


def hotkey_records(source: HotkeySource) -> dict[str, dict[str, object]]:
    """Capture combinations and script references, excluding enablement, authority and fired counts."""
    return {cast(str, getattr(item, 'binding_id')):
            {'combo': getattr(item, 'combo'), 'script_path': getattr(item, 'script_path')}
            for item in source.list_bindings()}


_TRIGGER_TYPES = {'FilePathTrigger': 'file', 'ImageAppearsTrigger': 'image', 'WindowAppearsTrigger': 'window',
                  'PixelColorTrigger': 'pixel', 'CronTrigger': 'cron', 'AllOfTrigger': 'all',
                  'AnyOfTrigger': 'any', 'SequenceTrigger': 'sequence'}
_TRIGGER_FIELDS = {'file': ('watch_path',), 'image': ('image_path', 'threshold'),
                   'window': ('title_substring', 'case_sensitive'), 'pixel': ('x', 'y', 'target_rgb', 'tolerance'),
                   'cron': ('cron',)}


def trigger_records(source: TriggerSource) -> dict[str, dict[str, object]]:
    """Capture supported real trigger conditions without evaluating them or reading runtime state."""
    return {cast(str, getattr(item, 'trigger_id')): _trigger_record(item, set(), 0)
            for item in source.list_triggers()}


def _trigger_record(trigger: object, active: set[int], depth: int) -> dict[str, object]:
    kind = _TRIGGER_TYPES.get(type(trigger).__name__)
    if kind is None or depth > 16 or id(trigger) in active:
        raise ConfigSyncError('unsupported or cyclic trigger definition')
    active.add(id(trigger))
    value: dict[str, object] = {'kind': kind, 'script_path': getattr(trigger, 'script_path'),
                                'repeat': getattr(trigger, 'repeat'),
                                'cooldown_seconds': getattr(trigger, 'cooldown_seconds')}
    if kind in _TRIGGER_FIELDS:
        value['condition'] = {name: getattr(trigger, name) for name in _TRIGGER_FIELDS[kind]}
    else:
        value['children'] = [_trigger_record(child, active, depth + 1) for child in getattr(trigger, 'children')]
    active.remove(id(trigger))
    return cast(dict[str, object], json.loads(_encoded(value)))


def address_records(source: AddressBookSource) -> dict[str, dict[str, object]]:
    """Read saved remote addresses, excluding last-use times, local wake settings and live connection state."""
    return address_record_values(source.list_entries())


def address_record_values(entries: Sequence[dict[str, object]]) -> dict[str, dict[str, object]]:
    """Project the existing address-book JSON schema without local connection metadata."""
    result = {}
    for item in entries:
        value = {'host_id': item.get('host_id'), 'server_url': item.get('server_url'),
                 'label': item.get('label', ''), 'favorite': item.get('favorite', False), 'tags': item.get('tags', [])}
        identity = {'host_id': value['host_id'], 'server_url': value['server_url']}
        result[sha256(_encoded(identity).encode('ascii')).hexdigest()] = value
    return result
