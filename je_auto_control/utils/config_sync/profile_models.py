"""Own an explicitly loaded native working snapshot without changing global engines, sources or active preferences."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import TYPE_CHECKING, Optional, cast

from je_auto_control.utils.config_sync.adapter_schema import AdapterKind
from je_auto_control.utils.config_sync.asset_commands import _root
from je_auto_control.utils.config_sync.contract import ConfigSyncError
from je_auto_control.utils.path_guard import PathPolicy

if TYPE_CHECKING:
    from je_auto_control.utils.element_repository.element_repository import ElementRepository
    from je_auto_control.utils.hotkey.hotkey_daemon import HotkeyBinding
    from je_auto_control.utils.remote_desktop.address_book import AddressBook
    from je_auto_control.utils.triggers.trigger_engine import _TriggerBase

ProfileRecords = dict[AdapterKind, dict[str, dict[str, object]]]


class LoadedSyncProfile:
    """An independent working snapshot with disabled native definitions and explicitly accessed repository handles."""

    def __init__(self, directory: Path, manifest_digest: str, records: ProfileRecords, *,
                   path_policy: Optional[PathPolicy] = None) -> None:
        # pylint: disable-next=import-outside-toplevel  # reason: native engine defaults depend on the fully initialized executor
        from je_auto_control.utils.config_sync.profile_runtime import native_hotkeys, native_triggers
        self._directory = directory
        self._digest = manifest_digest
        self._records = deepcopy(records)
        self._policy = path_policy
        self._hotkeys = native_hotkeys(records.get('hotkeys', {}))
        self._triggers = native_triggers(records.get('triggers', {}))

    @property
    def directory(self) -> Path:
        """Return the separate mutable working root; the immutable source generation is never edited."""
        return self._directory

    @property
    def manifest_digest(self) -> str:
        """Return the exact source generation digest explicitly reviewed before loading."""
        return self._digest

    def _path(self, name: str = '') -> Path:
        path = self._directory / name
        if _root(self._directory, self._policy) != self._directory or _root(path, self._policy) != path:
            raise ConfigSyncError('loaded workspace paths changed after publication')
        return path

    @property
    def scripts(self) -> dict[str, Path]:
        """Map loaded script names to independent native working files, without executing or rereading them."""
        return {name: self._path('scripts/' + name) for name in self._records.get('scripts', {})}

    def script_actions(self, name: str) -> list[object]:
        """Copy the reviewed loaded script snapshot for explicit editor import; this never executes actions."""
        if name not in self._records.get('scripts', {}):
            raise ConfigSyncError('script is not part of the loaded profile')
        self._path('scripts/' + name)
        return cast(list[object], deepcopy(self._records['scripts'][name]['actions']))

    @property
    def locators(self) -> ElementRepository:
        """Open the working locator repository explicitly; resolving or clicking remains a separate operation."""
        # pylint: disable-next=import-outside-toplevel  # reason: keep native source storage lazy until explicitly requested
        from je_auto_control.utils.element_repository.element_repository import ElementRepository
        if 'locators' not in self._records:
            raise ConfigSyncError('loaded profile has no locator repository')
        return ElementRepository(str(self._path('locators.json')))

    @property
    def address_book(self) -> AddressBook:
        """Open the working native address book without connecting or changing the current user's saved hosts."""
        # pylint: disable-next=import-outside-toplevel  # reason: do not open or initialize native stores during facade import
        from je_auto_control.utils.remote_desktop.address_book import AddressBook
        if 'address_book' not in self._records:
            raise ConfigSyncError('loaded profile has no address book')
        return AddressBook(self._path('address_book.json'))

    @property
    def hotkeys(self) -> tuple[HotkeyBinding, ...]:
        """Return native binding objects created disabled and never installed into a running daemon."""
        self._path()
        return self._hotkeys

    @property
    def triggers(self) -> tuple[_TriggerBase, ...]:
        """Return native condition objects created disabled at every composite depth, without polling."""
        self._path()
        return self._triggers

    @property
    def settings(self) -> dict[str, object]:
        """Copy loaded ordinary setting values; these do not replace process-global configuration."""
        self._path()
        return {name: deepcopy(value['value']) for name, value in self._records.get('settings', {}).items()}

    @property
    def preferences(self) -> dict[str, object]:
        """Copy four loaded GUI preferences without applying them to any window or importing Qt."""
        self._path()
        return {name: value['value'] for name, value in self._records.get('workspace', {}).items()}

    def definitions(self, kind: AdapterKind) -> dict[str, dict[str, object]]:
        """Copy the loaded native definitions for one selected domain, retaining disabled flags."""
        self._path()
        if kind not in self._records:
            raise ConfigSyncError('loaded profile does not select that kind')
        return deepcopy(self._records[kind])

    def to_dict(self) -> dict[str, object]:
        """Project private review metadata without opening sources, vaults, listeners or network connections."""
        self._path()
        return {'directory': str(self.directory), 'manifest_digest': self.manifest_digest,
                'kinds': sorted(self._records), 'counts': {kind: len(values) for kind, values in self._records.items()},
                'scripts': {name: str(path) for name, path in self.scripts.items()},
                'preferences': self.preferences,
                'hotkeys': [{'binding_id': item.binding_id, 'combo': item.combo,
                             'script_path': item.script_path, 'enabled': item.enabled} for item in self.hotkeys],
                'triggers': [{'trigger_id': item.trigger_id, 'kind': type(item).__name__,
                              'script_path': item.script_path, 'enabled': item.enabled} for item in self.triggers]}
