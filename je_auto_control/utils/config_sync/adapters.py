"""Concrete source adapters persist causal inbox profiles without changing a live script, locator or daemon."""
from __future__ import annotations

from collections import defaultdict
from itertools import islice
from pathlib import Path
from typing import Callable, Iterable, Mapping, Optional, cast

from je_auto_control.utils.config_sync.adapter_references import (
    SyncBindings, export_value, resolve_value, validate_portable,
)
from je_auto_control.utils.config_sync.adapter_profiles import profile_files
from je_auto_control.utils.config_sync.adapter_protocol import SyncAdapter
from je_auto_control.utils.config_sync.adapter_schema import AdapterKind, ApplyReport, validate_record
from je_auto_control.utils.config_sync.adapter_sources import (
    AddressBookSource, HotkeySource, LocatorSource, TriggerSource,
    address_records, hotkey_records, locator_records, read_json, script_records, trigger_records,
)
from je_auto_control.utils.config_sync.adapter_state import SyncAdapterState, _validate_incoming, resolution_ids
from je_auto_control.utils.config_sync.adapter_ledger import fingerprint
from je_auto_control.utils.config_sync.causal_state import CausalBucket
from je_auto_control.utils.config_sync.contract import ConfigSyncError, _encoded
from je_auto_control.utils.config_sync.versions import SyncEntry
from je_auto_control.utils.config_sync.workspace_preferences import _read_workspace_preferences
from je_auto_control.utils.config_sync.workspace_models import validate_workspace_snapshot, workspace_frontier
from je_auto_control.utils.exception.control_signals import raise_caused_run_interruption
from je_auto_control.utils.exception.exceptions import AutoControlException

__all__ = ['SyncAdapter', 'ScriptSyncAdapter', 'LocatorSyncAdapter', 'HotkeySyncAdapter',
           'TriggerSyncAdapter', 'AddressBookSyncAdapter', 'SettingsSyncAdapter', 'WorkspaceSettingsSyncAdapter']


class _DomainAdapter:
    """Share causal source observation, explicit conflict resolution and inert profile projection."""

    def __init__(self, kind: AdapterKind, read: Callable[[], dict[str, dict[str, object]]],
                   state: SyncAdapterState, bindings: Optional[SyncBindings]) -> None:
        self._kind = kind
        self._read = read
        self._state = state
        self._bindings = bindings or SyncBindings()

    @property
    def kind(self) -> AdapterKind:
        """Identify this adapter's causal section."""
        return self._kind

    def checkpoint(self) -> None:
        """Keep profile authority live while its captured data is materialized or delivered to another local view."""
        self._state.checkpoint()

    def _sources(self) -> dict[str, dict[str, object]]:
        self._state.checkpoint()
        try:
            raw = self._read()
        except AutoControlException as error:
            raise_caused_run_interruption(error)
            raise
        except (OSError, ValueError, TypeError, AttributeError) as error:
            raise_caused_run_interruption(error)
            raise ConfigSyncError('cannot read adapter source definitions') from error
        self._state.checkpoint()
        if len(raw) > 1000:
            raise ConfigSyncError('adapter source has more than 1000 definitions')
        result = {}
        for entry_id, value in raw.items():
            self._state.checkpoint()
            value = export_value(entry_id, value, self._bindings, root_key=entry_id if self.kind == 'settings' else '')
            validate_record(self.kind, entry_id, value)
            result[entry_id] = value
        return result

    def snapshot(self) -> dict[str, SyncEntry]:
        """Capture actual source changes once, preserving every unresolved causal alternative across restart."""
        heads, _stored = self._state.update(self.kind, self._sources(), {})
        return heads

    def apply(self, entries: Mapping[str, SyncEntry]) -> ApplyReport:
        """Validate the complete batch before I/O, then atomically observe source edits and merge inbox versions."""
        _validate_incoming(self.kind, entries)
        heads, stored = self._state.update(self.kind, self._sources(), entries)
        _ready, conflicts, unresolved = self._project(heads)
        unchanged = tuple(sorted({item.entry_id for item in entries.values()} - set(stored)))
        return ApplyReport(stored, unchanged, conflicts, unresolved)

    def receive_frontier(self, snapshot: CausalBucket) -> None:
        """Merge a complete validated server section, including fences, without observing or activating live sources."""
        validate_workspace_snapshot(snapshot)
        if snapshot.user_id != self._state.identity.user_id:
            raise ConfigSyncError('workspace frontier belongs to another account')
        incoming, compacted = workspace_frontier(snapshot, self.kind)
        self._state.update(self.kind, None, incoming, compacted=compacted)

    def receive_entries(self, entries: Mapping[str, SyncEntry]) -> None:
        """Merge portable queued versions without observing sources or changing operation identities."""
        self._state.update(self.kind, None, entries)

    def source_fingerprints(self) -> dict[str, str]:
        """Capture portable source fingerprints without opening adapter state or serializing raw machine values."""
        return {name: fingerprint(value) for name, value in self._sources().items()}

    def adopt_frontier(self, snapshot: CausalBucket, baseline: Mapping[str, str], *, operation_id: str) -> None:
        """Initialize a confirmed new peer generation once; unchanged pre-resync sources stay retired."""
        validate_workspace_snapshot(snapshot)
        identity = self._state.identity
        if snapshot.user_id != identity.user_id:
            raise ConfigSyncError('workspace adoption belongs to another account')
        snapshot.peers.require_active(identity.origin, epoch=identity.epoch)
        incoming, compacted = workspace_frontier(snapshot, self.kind)
        self._state.adopt(self.kind, incoming, baseline, operation_id=operation_id, compacted=compacted)

    def report(self) -> ApplyReport:
        """Inspect conflicts and unresolved local bindings without reading source files or enabling a runtime."""
        _values, conflicts, unresolved = self._project(self._state.heads(self.kind))
        return ApplyReport((), (), conflicts, unresolved)

    def review(self) -> dict[str, SyncEntry]:
        """Read the exact current portable head set without creating source edits."""
        return self._state.heads(self.kind)

    def adopted_control(self) -> Optional[str]:
        """Return the adopted reset; repeated reconciliation never resets subsequent edits."""
        return self._state.adopted_control(self.kind)

    def resolve(self, entry_id: str, value: dict[str, object], *, observed: Iterable[str],
                  is_deleted: bool = False) -> SyncEntry:
        """Choose a portable value after reviewing the exact head set; a new source edit invalidates stale review."""
        if not isinstance(is_deleted, bool):
            raise ConfigSyncError('resolution deletion flag must be a JSON boolean')
        validate_record(self.kind, entry_id, value, deleted=is_deleted)
        validate_portable(value, root_key=entry_id if self.kind == 'settings' else '')
        expected = resolution_ids(observed)
        self.snapshot()
        return self._state.resolve(self.kind, entry_id, value, observed=expected, is_deleted=is_deleted)

    def _project(self, heads: Mapping[str, SyncEntry]
                    ) -> tuple[dict[str, dict[str, object]], tuple[str, ...], tuple[str, ...]]:
        groups: dict[str, list[SyncEntry]] = defaultdict(list)
        for entry in heads.values():
            groups[entry.entry_id].append(entry)
        records: dict[str, dict[str, object]] = {}
        conflicts: list[str] = []
        unresolved: list[str] = []
        for entry_id, versions in sorted(groups.items()):
            if len(versions) != 1:
                conflicts.append(entry_id)
                continue
            if versions[0].is_deleted:
                continue
            value, missing = resolve_value(versions[0].value, self._bindings)
            if missing:
                unresolved.extend(f'{entry_id}:{name}' for name in missing)
                continue
            try:
                validate_record(self.kind, entry_id, value)
            except ConfigSyncError:
                unresolved.append(entry_id + ':local-value-type')
                continue
            records[entry_id] = _disabled(value) if self.kind in {'hotkeys', 'triggers'} else value
        return records, tuple(conflicts), tuple(sorted(unresolved))

    def definitions(self) -> dict[str, dict[str, object]]:
        """Copy the complete ready profile; no partial result can hide a conflict or missing local reference."""
        values, conflicts, unresolved = self._project(self._state.heads(self.kind))
        if conflicts or unresolved:
            raise ConfigSyncError('adapter profile has unresolved conflicts or local references')
        return values

    def profile_files(self) -> dict[str, bytes]:
        """Serialize one consistent head view in its native data format, retaining exact version IDs in metadata."""
        heads = self._state.heads(self.kind)
        values, conflicts, unresolved = self._project(heads)
        if conflicts or unresolved:
            raise ConfigSyncError('adapter profile has unresolved conflicts or local references')
        return profile_files(self.kind, values, heads)


def _disabled(value: dict[str, object]) -> dict[str, object]:
    result = dict(value, enabled=False)
    if 'children' in result:
        result['children'] = [_disabled(child) for child in cast(list[dict[str, object]], result['children'])]
    return result


class ScriptSyncAdapter(_DomainAdapter):
    """Capture explicitly selected real JSON scripts; received profiles never replace those active source files."""

    def __init__(self, source_root: str | Path, state: SyncAdapterState, *, paths: Iterable[str],
                   bindings: Optional[SyncBindings] = None) -> None:
        self.source_root = Path(source_root).resolve()
        if isinstance(paths, (str, bytes)):
            raise ConfigSyncError('script selection must contain relative paths, not a single string')
        self._paths = tuple(islice(paths, 1001))
        if len(self._paths) > 1000:
            raise ConfigSyncError('script selection exceeds 1000 files')
        super().__init__('scripts', lambda: script_records(self.source_root, self._paths), state, bindings)


class LocatorSyncAdapter(_DomainAdapter):
    """Capture the real named accessibility-locator repository without querying a platform backend."""

    def __init__(self, source: LocatorSource, state: SyncAdapterState, *,
                   bindings: Optional[SyncBindings] = None) -> None:
        super().__init__('locators', lambda: locator_records(source), state, bindings)


class HotkeySyncAdapter(_DomainAdapter):
    """Capture real registered hotkey definitions while retaining all runtime enablement and authority locally."""

    def __init__(self, source: HotkeySource, state: SyncAdapterState, *,
                   bindings: Optional[SyncBindings] = None) -> None:
        super().__init__('hotkeys', lambda: hotkey_records(source), state, bindings)


class TriggerSyncAdapter(_DomainAdapter):
    """Capture real trigger conditions without polling them, registering incoming work or enabling it."""

    def __init__(self, source: TriggerSource, state: SyncAdapterState, *,
                   bindings: Optional[SyncBindings] = None) -> None:
        super().__init__('triggers', lambda: trigger_records(source), state, bindings)


class AddressBookSyncAdapter(_DomainAdapter):
    """Capture actual saved hosts without runtime connections, authentication, last-use state or local wake settings."""

    def __init__(self, source: AddressBookSource, state: SyncAdapterState, *,
                   bindings: Optional[SyncBindings] = None) -> None:
        super().__init__('address_book', lambda: address_records(source), state, bindings)


class SettingsSyncAdapter(_DomainAdapter):
    """Capture explicitly selected JSON working settings, with credential and machine values kept as references."""

    def __init__(self, source_path: str | Path, state: SyncAdapterState, *,
                   bindings: Optional[SyncBindings] = None) -> None:
        path = Path(source_path).resolve()
        super().__init__('settings', lambda: _settings(path), state, bindings)


def _settings(path: Path) -> dict[str, dict[str, object]]:
    value = read_json(path) if path.exists() else {}
    if not isinstance(value, dict):
        raise ConfigSyncError('working settings require a JSON object')
    _encoded(value)
    return {key: {'value': item} for key, item in value.items()}


class WorkspaceSettingsSyncAdapter(_DomainAdapter):
    """Capture four portable native GUI INI preferences; receiving them never changes the current workspace."""

    def __init__(self, source_path: str | Path, state: SyncAdapterState) -> None:
        path = Path(source_path).resolve()
        super().__init__('workspace', lambda: _read_workspace_preferences(path), state, None)
