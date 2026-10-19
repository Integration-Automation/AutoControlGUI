"""Private JSON command adapters capture, merge, resolve and materialize inert causal definition profiles."""
from dataclasses import asdict
from typing import Callable, Optional

from je_auto_control.utils.config_sync.adapter_factory import adapter_from_profile
from je_auto_control.utils.config_sync.adapter_schema import KINDS
from je_auto_control.utils.config_sync.adapter_profiles import materialize_sync_profile
from je_auto_control.utils.config_sync.asset_commands import _checkpoint, _root
from je_auto_control.utils.config_sync.contract import ConfigSyncError
from je_auto_control.utils.config_sync.versions import SyncEntry
from je_auto_control.utils.path_guard import PathPolicy

_Cancelled = Optional[Callable[[], bool]]


def _snapshot_sync_adapter(profile: dict[str, object], *, path_policy: Optional[PathPolicy] = None,
                             cancelled: _Cancelled = None) -> dict[str, object]:
    """Capture source changes and return portable heads without activating anything."""
    adapter = adapter_from_profile(profile, path_policy=path_policy, cancelled=cancelled)
    return {'kind': adapter.kind, 'entries': {key: entry.to_dict() for key, entry in adapter.snapshot().items()}}


def _apply_sync_adapter(profile: dict[str, object], entries: dict[str, dict[str, object]], *,
                          path_policy: Optional[PathPolicy] = None, cancelled: _Cancelled = None) -> dict[str, object]:
    """Persist incoming portable versions as an inert profile, preserving all parallel alternatives."""
    _checkpoint((), path_policy, cancelled)
    values = _entries(entries)
    adapter = adapter_from_profile(profile, path_policy=path_policy, cancelled=cancelled)
    return asdict(adapter.apply(values))


def _resolve_sync_adapter(profile: dict[str, object], entry_id: str, value: dict[str, object], observed: list[str],
                            is_deleted: bool = False, *, path_policy: Optional[PathPolicy] = None,
                            cancelled: _Cancelled = None) -> dict[str, object]:
    """Resolve exactly the reviewed alternatives into a value or tombstone; runtime sources stay untouched."""
    adapter = adapter_from_profile(profile, path_policy=path_policy, cancelled=cancelled)
    return adapter.resolve(entry_id, value, observed=observed, is_deleted=is_deleted).to_dict()


def _materialize_sync_profile(profiles: list[dict[str, object]], target_root: str, *,
                                path_policy: Optional[PathPolicy] = None,
                                cancelled: _Cancelled = None) -> dict[str, object]:
    """Publish one complete ready local profile generation without replacing active workspace files."""
    _checkpoint((), path_policy, cancelled)
    if not isinstance(profiles, list) or not 1 <= len(profiles) <= len(KINDS):
        raise ConfigSyncError(f'materialization requires 1–{len(KINDS)} explicit adapter profiles')
    target = _root(target_root, path_policy)
    adapters = tuple(adapter_from_profile(item, path_policy=path_policy, cancelled=cancelled) for item in profiles)
    result = materialize_sync_profile(adapters, target,
        cancelled=lambda: _checkpoint((target,), path_policy, cancelled))
    reply = asdict(result)
    reply['directory'] = str(result.directory)
    return reply


def _entries(raw: dict[str, dict[str, object]]) -> dict[str, SyncEntry]:
    if not isinstance(raw, dict) or len(raw) > 1024:
        raise ConfigSyncError('adapter entries must be a bounded change-ID mapping')
    return {key: SyncEntry.from_dict(value) for key, value in raw.items()}
