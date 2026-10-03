"""Definition-only adapters; receiving never executes scripts or starts listeners."""
from __future__ import annotations

import uuid
import json
from dataclasses import dataclass
from typing import Any, Dict, Mapping, MutableMapping, Optional, Protocol, Tuple

from .definition_privacy import portable_definition, resolve_definition
from .models import ConfigSyncError
from .versions import SyncEntry


@dataclass(frozen=True)
class ApplyReport:
    """Explicitly applied identifiers and unresolved definitions retained for review."""
    applied: Tuple[str, ...] = ()
    unresolved: Tuple[str, ...] = ()


class SyncAdapter(Protocol):
    """Snapshot portable causal definitions and apply explicitly selected entries."""

    def snapshot(self) -> Mapping[str, SyncEntry]:
        """Return values without confidential local literals or runtime state."""

    def apply(self, entries: Mapping[str, SyncEntry]) -> ApplyReport:
        """Apply selected data without activating its behavior."""


class JsonDefinitionAdapter:
    """JSON script/locator definitions with stable causal identities between unchanged reads.

    Supply a durable ``state`` mapping when reconstructing an adapter across runs.
    This mapping contains only portable values. Local definitions retain secrets.
    """

    def __init__(self, section: str, definitions: MutableMapping[str, Dict[str, Any]], *, device_id: str,
                 state: Optional[MutableMapping[str, SyncEntry]] = None) -> None:
        if not section or not device_id:
            raise ConfigSyncError('adapter requires section and device identity')
        self.section = section
        self._definitions = definitions
        self._device = device_id
        self._state = state if state is not None else {}

    def _edit(self, entry_id: str, value: Mapping[str, object], deleted: bool = False) -> SyncEntry:
        prior = self._state.get(entry_id)
        vector = dict(prior.version) if prior else {}
        vector[self._device] = vector.get(self._device, 0) + 1
        entry = SyncEntry(value, vector, self._device, uuid.uuid4().hex, deleted)
        self._state[entry_id] = entry
        return entry

    def snapshot(self) -> Mapping[str, SyncEntry]:
        """Advance versions only for changed portable values or actual deletions."""
        for entry_id, value in self._definitions.items():
            portable = portable_definition(value)
            prior = self._state.get(entry_id)
            changed = (prior is None or
                       json.dumps(dict(prior.value), sort_keys=True) != json.dumps(portable, sort_keys=True))
            if changed or (prior is not None and prior.is_deleted):
                self._edit(entry_id, portable)
        for entry_id, prior in list(self._state.items()):
            if entry_id not in self._definitions and not prior.is_deleted:
                self._edit(entry_id, {}, deleted=True)
        return dict(self._state)

    def apply(self, entries: Mapping[str, SyncEntry]) -> ApplyReport:
        """Apply an explicit selection, preserving local references and unresolved entries."""
        applied, unresolved = [], []
        for entry_id, entry in entries.items():
            try:
                if entry.is_deleted:
                    self._definitions.pop(entry_id, None)
                else:
                    value = resolve_definition(entry.value, self._definitions.get(entry_id, {}))
                    self._definitions[entry_id] = value
                self._state[entry_id] = entry
                applied.append(entry_id)
            except ConfigSyncError:
                unresolved.append(entry_id)
        return ApplyReport(tuple(applied), tuple(unresolved))


class ScriptSyncAdapter(JsonDefinitionAdapter):
    """Portable JSON action definitions, never evaluated or imported."""

    def __init__(self, definitions: MutableMapping[str, Dict[str, Any]], *, device_id: str,
                 state: Optional[MutableMapping[str, SyncEntry]] = None) -> None:
        super().__init__('scripts', definitions, device_id=device_id, state=state)


class LocatorSyncAdapter(JsonDefinitionAdapter):
    """Portable locator definitions; image files travel through the checked asset service."""

    def __init__(self, definitions: MutableMapping[str, Dict[str, Any]], *, device_id: str,
                 state: Optional[MutableMapping[str, SyncEntry]] = None) -> None:
        super().__init__('locators', definitions, device_id=device_id, state=state)
