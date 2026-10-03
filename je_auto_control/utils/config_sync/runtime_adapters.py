"""Adapt actual hotkey, trigger and address-book stores without starting their runtime."""
from __future__ import annotations

from dataclasses import fields
import hashlib
import json
from typing import TYPE_CHECKING, Any, Dict, Mapping, MutableMapping, Optional

from je_auto_control.utils.remote_desktop.address_book import AddressBook

from .definition_adapter import ApplyReport, JsonDefinitionAdapter
from .models import ConfigSyncError
from .definition_privacy import portable_definition
from .versions import SyncEntry

if TYPE_CHECKING:
    from je_auto_control.utils.hotkey.hotkey_daemon import HotkeyDaemon
    from je_auto_control.utils.triggers import trigger_engine as triggers


class _StoreAdapter(JsonDefinitionAdapter):
    def snapshot(self) -> Mapping[str, SyncEntry]:
        self._definitions.clear()
        self._definitions.update(self._read())
        return super().snapshot()

    def apply(self, entries: Mapping[str, SyncEntry]) -> ApplyReport:
        self._definitions.clear()
        self._definitions.update(self._read())
        previous = dict(self._state)
        report = super().apply(entries)
        applied, unresolved = [], list(report.unresolved)
        for entry_id in report.applied:
            try:
                self._write(entry_id, self._definitions.get(entry_id))
                applied.append(entry_id)
            except (ConfigSyncError, ValueError, TypeError):
                unresolved.append(entry_id)
                self._state.pop(entry_id, None)
                if entry_id in previous:
                    self._state[entry_id] = previous[entry_id]
        return ApplyReport(tuple(applied), tuple(unresolved))

    def _read(self) -> Dict[str, Dict[str, Any]]:
        raise NotImplementedError

    def _write(self, entry_id: str, value: Optional[Dict[str, Any]]) -> None:
        raise NotImplementedError


class HotkeySyncAdapter(_StoreAdapter):
    """Hotkey definitions are inserted disabled, including when the daemon already runs."""

    def __init__(self, daemon: HotkeyDaemon, *, device_id: str,
                 state: Optional[MutableMapping[str, SyncEntry]] = None) -> None:
        super().__init__('hotkeys', {}, device_id=device_id, state=state)
        self._daemon = daemon

    def _read(self) -> Dict[str, Dict[str, Any]]:
        return {item.binding_id: {'combo': item.combo, 'script_path': item.script_path}
                for item in self._daemon.list_bindings()}

    def _write(self, entry_id: str, value: Optional[Dict[str, Any]]) -> None:
        if value is None:
            self._daemon.unbind(entry_id)
        else:
            self._daemon.bind(value['combo'], value['script_path'], entry_id, enabled=False)


_RUNTIME_FIELDS = {'enabled', 'fired', 'trigger_id'}


def _trigger_types() -> Dict[str, Any]:
    # Import only when constructing definitions: default engines import the executor.
    from je_auto_control.utils.triggers import trigger_engine as module  # pylint: disable=import-outside-toplevel
    return {item.__name__: item for item in (
        module.ImageAppearsTrigger, module.WindowAppearsTrigger, module.PixelColorTrigger,
        module.FilePathTrigger, module.CronTrigger, module.AllOfTrigger, module.AnyOfTrigger, module.SequenceTrigger,
    )}


def _trigger_value(trigger: triggers._TriggerBase) -> Dict[str, Any]:  # pylint: disable=protected-access
    value = {field.name: getattr(trigger, field.name) for field in fields(trigger)
             if not field.name.startswith('_') and field.name not in _RUNTIME_FIELDS}
    value['type'] = type(trigger).__name__
    if 'children' in value:
        value['children'] = [_trigger_value(child) for child in trigger.children]  # type: ignore[attr-defined]
    return value


def _make_trigger(entry_id: str, value: Mapping[str, Any]) -> triggers._TriggerBase:  # pylint: disable=protected-access
    definition = dict(value)
    kind = _trigger_types().get(definition.pop('type', ''))
    if kind is None:
        raise ConfigSyncError('unsupported trigger definition')
    allowed = {field.name for field in fields(kind) if not field.name.startswith('_')} - _RUNTIME_FIELDS
    if set(definition) - allowed:
        raise ConfigSyncError('trigger contains runtime or unsupported fields')
    if 'children' in definition:
        definition['children'] = [_make_trigger(f'{entry_id}/{index}', child)
                                  for index, child in enumerate(definition['children'])]
    return kind(trigger_id=entry_id, enabled=False, **definition)


class TriggerSyncAdapter(_StoreAdapter):
    """Trigger definitions retain local paths, exclude counters and arrive disabled."""

    def __init__(self, engine: triggers.TriggerEngine, *, device_id: str,
                 state: Optional[MutableMapping[str, SyncEntry]] = None) -> None:
        super().__init__('triggers', {}, device_id=device_id, state=state)
        self._engine = engine

    def _read(self) -> Dict[str, Dict[str, Any]]:
        return {item.trigger_id: _trigger_value(item) for item in self._engine.list_triggers()}

    def _write(self, entry_id: str, value: Optional[Dict[str, Any]]) -> None:
        if value is None:
            self._engine.remove(entry_id)
        else:
            self._engine.add(_make_trigger(entry_id, value))


class AddressBookSyncAdapter(_StoreAdapter):
    """Saved connection definitions only; no session credentials, recency or connection side effects."""

    def __init__(self, book: AddressBook, *, device_id: str,
                 state: Optional[MutableMapping[str, SyncEntry]] = None) -> None:
        super().__init__('address_book', {}, device_id=device_id, state=state)
        self._book = book

    def _read(self) -> Dict[str, Dict[str, Any]]:
        result = {}
        for item in self._book.list_entries():
            definition = {key: value for key, value in item.items()
                          if key in {'host_id', 'server_url', 'label', 'tags', 'favorite'}}
            portable = portable_definition(definition)
            identity = json.dumps([portable['host_id'], portable['server_url']], sort_keys=True).encode('utf-8')
            result[hashlib.sha256(identity).hexdigest()] = definition
        return result

    def _write(self, entry_id: str, value: Optional[Dict[str, Any]]) -> None:
        if value is None:
            prior = self._read().get(entry_id)
            if prior:
                self._book.remove(host_id=prior['host_id'], server_url=prior['server_url'])
            return
        host_id = value['host_id']
        self._book.upsert(host_id=host_id, server_url=value['server_url'], label=value.get('label', ''))
        self._book.set_tags(host_id=host_id, server_url=value['server_url'], tags=value.get('tags', []))
        existing = next(item for item in self._book.list_entries()
                        if item['host_id'] == host_id and item['server_url'] == value['server_url'])
        if bool(existing.get('favorite')) != bool(value.get('favorite')):
            self._book.toggle_favorite(host_id=host_id, server_url=value['server_url'])
