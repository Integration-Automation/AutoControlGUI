"""Capture six real domain sources and receive complete inert profiles using temporary local files only."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from je_auto_control import (
    AddressBookSyncAdapter, ElementRepository, HotkeyDaemon, HotkeySyncAdapter, LocatorSyncAdapter,
    ScriptSyncAdapter, SettingsSyncAdapter, SyncAdapterState, SyncBindings, SyncLocalIdentity,
    TriggerEngine, TriggerSyncAdapter, WindowAppearsTrigger, materialize_sync_profile,
)
from je_auto_control.utils.remote_desktop.address_book import AddressBook


def _state(root: Path, origin: str) -> SyncAdapterState:
    identity = SyncLocalIdentity('https://controlled.invalid', 'example', origin, 0, 0)
    return SyncAdapterState(root / (origin + '.sqlite3'), identity)


def _never_execute(_actions: list) -> None:
    raise RuntimeError('synchronized work must remain inert')


def main() -> None:
    """Preserve vault/device references without reading a vault, registering OS listeners or running received work."""
    with TemporaryDirectory(prefix='autocontrol-adapters-') as temporary:
        root = Path(temporary)
        source, target = root / 'source', root / 'target'
        source.mkdir()
        target.mkdir()
        script = source / 'login.json'
        script.write_text(json.dumps([['AC_write_secret', {'secret': '${secrets.LOGIN}'}]]), encoding='utf-8')
        settings = source / 'settings.json'
        settings.write_text(json.dumps({'theme': 'dark', 'device_id': 'sender-device'}), encoding='utf-8')
        target_settings = target / 'settings.json'
        target_settings.write_text('{}', encoding='utf-8')
        bindings = SyncBindings(local_values={'script': str(script), 'phone': 'sender-device'})
        receiving = SyncBindings(local_values={'script': 'scripts/login.json', 'phone': 'receiver-device'})
        sender_state, receiver_state = _state(root, 'desktop'), _state(root, 'laptop')
        repository = ElementRepository(str(source / 'locators.json'))
        repository.save('login.submit', name='Submit', role='button')
        daemon, other_daemon = HotkeyDaemon(_never_execute), HotkeyDaemon(_never_execute)
        daemon.bind('ctrl+alt+1', str(script), binding_id='login')
        engine, other_engine = TriggerEngine(_never_execute), TriggerEngine(_never_execute)
        engine.add(WindowAppearsTrigger(trigger_id='demo', script_path=str(script), title_substring='Demo'))
        book, other_book = AddressBook(source / 'addresses.json'), AddressBook(target / 'addresses.json')
        book.upsert(host_id='demo-host', server_url='https://signal.invalid', label='Office')
        adapters = (
            ScriptSyncAdapter(source, sender_state, paths=('login.json',), bindings=bindings),
            LocatorSyncAdapter(repository, sender_state), HotkeySyncAdapter(daemon, sender_state, bindings=bindings),
            TriggerSyncAdapter(engine, sender_state, bindings=bindings), AddressBookSyncAdapter(book, sender_state),
            SettingsSyncAdapter(settings, sender_state, bindings=bindings),
        )
        receivers = (
            ScriptSyncAdapter(target, receiver_state, paths=(), bindings=receiving),
            LocatorSyncAdapter(ElementRepository(str(target / 'locators.json')), receiver_state),
            HotkeySyncAdapter(other_daemon, receiver_state, bindings=receiving),
            TriggerSyncAdapter(other_engine, receiver_state, bindings=receiving),
            AddressBookSyncAdapter(other_book, receiver_state),
            SettingsSyncAdapter(target_settings, receiver_state, bindings=receiving),
        )
        for sender, receiver in zip(adapters, receivers):
            report = receiver.apply(sender.snapshot())
            if report.conflicts or report.unresolved:
                raise RuntimeError('controlled profile was not ready')
        result = materialize_sync_profile(receivers, root / 'cache')
        if other_daemon.list_bindings() or other_engine.list_triggers():
            raise RuntimeError('receiving a profile changed an active runtime')
        print(json.dumps({'kinds': [adapter.kind for adapter in receivers], 'files': result.file_count,
                          'script_executions': 0, 'received_hotkeys_registered': 0,
                          'received_triggers_registered': 0, 'vault_reads': 0, 'network_calls': 0}))


if __name__ == '__main__':
    main()
