"""Concrete domain adapters retain causal profiles and local references without activating synchronized work."""
import json

import pytest

import je_auto_control as ac
from je_auto_control.utils.remote_desktop.address_book import AddressBook


def state(tmp_path, origin, name='state.sqlite3'):
    identity = ac.SyncLocalIdentity('https://controlled.invalid', 'alice', origin, 0, 0)
    return ac.SyncAdapterState(tmp_path / name, identity)


def script_adapter(tmp_path, origin, *, bindings=None):
    directory = tmp_path / origin
    directory.mkdir(exist_ok=True)
    return ac.ScriptSyncAdapter(directory, state(tmp_path, origin, origin + '.sqlite3'),
                                paths=('login.json',), bindings=bindings)


def write_script(adapter, value):
    (adapter.source_root / 'login.json').write_text(json.dumps([['AC_log', {'message': value}]]), encoding='utf-8')


def test_real_script_snapshot_is_stable_across_restart_and_materializes_inert_json(tmp_path, monkeypatch):
    sender = script_adapter(tmp_path, 'desktop')
    write_script(sender, 'hello')
    original = sender.snapshot()
    assert len(original) == 1
    assert all(key == value.change_id for key, value in original.items())
    assert script_adapter(tmp_path, 'desktop').snapshot() == original
    receiver = script_adapter(tmp_path, 'laptop')
    monkeypatch.setattr(ac.executor, 'execute_action', lambda *_a, **_k: pytest.fail('sync executed a script'))
    report = receiver.apply(original)
    assert report.stored == ('login.json',) and not report.conflicts
    result = ac.materialize_sync_profile((receiver,), tmp_path / 'profile-cache')
    assert json.loads((result.directory / 'scripts' / 'login.json').read_text()) == [['AC_log', {'message': 'hello'}]]
    assert not (receiver.source_root / 'login.json').exists()
    assert receiver.snapshot() == original


def test_secret_is_local_and_machine_paths_remain_named_references(tmp_path):
    fields = {'login.json': {'/actions/0/1/password': ac.SyncReference('secret', 'LOGIN'),
                             '/actions/0/1/file_path': ac.SyncReference('local', 'downloads')}}
    sender = script_adapter(tmp_path, 'desktop', bindings=ac.SyncBindings(fields=fields))
    actions = [['AC_example', {'password': 'local-password-only', 'file_path': 'C:/private-sender/result.txt'}]]
    (sender.source_root / 'login.json').write_text(json.dumps(actions), encoding='utf-8')
    entries = sender.snapshot()
    wire = json.dumps([entry.to_dict() for entry in entries.values()])
    assert 'local-password-only' not in wire and 'private-sender' not in wire
    assert b'local-password-only' not in (tmp_path / 'desktop.sqlite3').read_bytes()
    receiver = script_adapter(tmp_path, 'laptop',
                               bindings=ac.SyncBindings(local_values={'downloads': '/receiver/result.txt'}))
    assert not receiver.apply(entries).unresolved
    result = ac.materialize_sync_profile((receiver,), tmp_path / 'cache')
    received = json.loads((result.directory / 'scripts' / 'login.json').read_text())[0][1]
    assert received == {'password': '${secrets.LOGIN}', 'file_path': '/receiver/result.txt'}


def test_unbound_secret_or_machine_path_fails_before_creating_state(tmp_path):
    sender = script_adapter(tmp_path, 'desktop')
    for arguments in ({'password': 'do-not-export'}, {'file_path': '/private/path'}):
        (sender.source_root / 'login.json').write_text(json.dumps([['AC_example', arguments]]), encoding='utf-8')
        with pytest.raises(ac.ConfigSyncError):
            sender.snapshot()
        assert not (tmp_path / 'desktop.sqlite3').exists()


def test_sync_never_enables_trigger_or_hotkey_and_keeps_runtime_state_local(tmp_path):
    script = str(tmp_path / 'run.json')
    bindings = ac.SyncBindings(local_values={'script': script})
    engine = ac.TriggerEngine(executor=lambda _actions: pytest.fail('trigger ran'))
    engine.add(ac.FilePathTrigger(trigger_id='watch', script_path=script, watch_path=str(tmp_path / 'watched'),
                                  enabled=True, fired=8))
    trigger_bindings = ac.SyncBindings(local_values={'script': script, 'watch': str(tmp_path / 'watched')})
    sender = ac.TriggerSyncAdapter(engine, state(tmp_path, 'desktop', 'triggers.sqlite3'), bindings=trigger_bindings)
    entries = sender.snapshot()
    assert 'fired' not in json.dumps([entry.to_dict() for entry in entries.values()])
    target = ac.TriggerEngine(executor=lambda _actions: pytest.fail('remote trigger ran'))
    receiver = ac.TriggerSyncAdapter(target, state(tmp_path, 'laptop', 'target-triggers.sqlite3'),
                                     bindings=trigger_bindings)
    receiver.apply(entries)
    assert target.list_triggers() == [] and not target.is_running
    assert all(value['enabled'] is False for value in receiver.definitions().values())
    daemon = ac.HotkeyDaemon(executor=lambda _actions: pytest.fail('hotkey ran'))
    daemon.bind('ctrl+alt+1', script, binding_id='login')
    hotkeys = ac.HotkeySyncAdapter(daemon, state(tmp_path, 'desktop', 'hotkeys.sqlite3'), bindings=bindings)
    empty = ac.HotkeyDaemon(executor=lambda _actions: pytest.fail('remote hotkey ran'))
    received = ac.HotkeySyncAdapter(empty, state(tmp_path, 'laptop', 'target-hotkeys.sqlite3'), bindings=bindings)
    received.apply(hotkeys.snapshot())
    assert empty.list_bindings() == [] and not empty.is_running
    assert received.definitions()['login']['enabled'] is False


def test_locator_and_address_book_profiles_use_real_native_storage_formats(tmp_path):
    repository = ac.ElementRepository(str(tmp_path / 'local-locators.json'))
    repository.save('login.submit', name='Submit', role='button')
    locators = ac.LocatorSyncAdapter(repository, state(tmp_path, 'desktop', 'locator-state.sqlite3'))
    other = ac.LocatorSyncAdapter(ac.ElementRepository(str(tmp_path / 'empty-locators.json')),
                                  state(tmp_path, 'laptop', 'other-locators.sqlite3'))
    other.apply(locators.snapshot())
    book = AddressBook(tmp_path / 'local-book.json')
    book.upsert(host_id='host-one', server_url='https://signal.invalid', label='Office')
    book.set_tags(host_id='host-one', server_url='https://signal.invalid', tags=['work'])
    addresses = ac.AddressBookSyncAdapter(book, state(tmp_path, 'desktop', 'address-state.sqlite3'))
    remote = ac.AddressBookSyncAdapter(AddressBook(tmp_path / 'empty-book.json'),
                                      state(tmp_path, 'laptop', 'other-addresses.sqlite3'))
    remote.apply(addresses.snapshot())
    result = ac.materialize_sync_profile((other, remote), tmp_path / 'cache')
    restored_locators = ac.ElementRepository(str(result.directory / 'locators.json'))
    assert restored_locators.get('login.submit') == repository.get('login.submit')
    restored = AddressBook(result.directory / 'address_book.json').list_entries()
    assert restored[0]['label'] == 'Office' and restored[0]['tags'] == ['work']
    assert 'last_used' not in json.dumps([entry.to_dict() for entry in addresses.snapshot().values()])


def test_parallel_source_edits_require_explicit_resolution_and_survive_restart(tmp_path):
    desktop, laptop = script_adapter(tmp_path, 'desktop'), script_adapter(tmp_path, 'laptop')
    write_script(desktop, 'base')
    laptop.apply(desktop.snapshot())
    write_script(laptop, 'base')
    assert len(laptop.snapshot()) == 1
    write_script(desktop, 'left')
    write_script(laptop, 'right')
    report = laptop.apply(desktop.snapshot())
    assert report.conflicts == ('login.json',)
    heads = laptop.snapshot()
    assert len(heads) == 2
    with pytest.raises(ac.ConfigSyncError):
        ac.materialize_sync_profile((laptop,), tmp_path / 'must-not-publish')
    selected = next(entry for entry in heads.values() if entry.value['actions'][0][1]['message'] == 'left')
    laptop.resolve('login.json', selected.value, observed=tuple(heads))
    reopened = script_adapter(tmp_path, 'laptop')
    assert len(reopened.snapshot()) == 1
    assert next(iter(reopened.snapshot().values())).value == selected.value


def test_missing_reference_persists_portable_entry_but_refuses_partial_materialization(tmp_path):
    source = script_adapter(tmp_path, 'desktop', bindings=ac.SyncBindings(
        fields={'login.json': {'/actions/0/1/file_path': ac.SyncReference('local', 'download')}}))
    (source.source_root / 'login.json').write_text(json.dumps([['AC_example', {'file_path': '/private/file'}]]))
    receiver = script_adapter(tmp_path, 'laptop')
    report = receiver.apply(source.snapshot())
    assert report.unresolved
    assert len(receiver.snapshot()) == 1
    with pytest.raises(ac.ConfigSyncError):
        ac.materialize_sync_profile((receiver,), tmp_path / 'cache')
    assert not (tmp_path / 'cache').exists()


def test_invalid_remote_secret_is_rejected_before_any_local_state_write(tmp_path):
    receiver = script_adapter(tmp_path, 'laptop')
    entry = ac.SyncEntry('scripts', 'login.json', {'actions': [['AC_example', {'password': 'remote-plain'}]]},
                         {'desktop': 1}, 'bad', 'desktop')
    with pytest.raises(ac.ConfigSyncError):
        receiver.apply({entry.change_id: entry})
    assert not (tmp_path / 'laptop.sqlite3').exists()


def test_receiver_edit_of_an_unactivated_old_source_does_not_silently_overwrite_remote(tmp_path):
    desktop, laptop = script_adapter(tmp_path, 'desktop'), script_adapter(tmp_path, 'laptop')
    write_script(desktop, 'base')
    laptop.apply(desktop.snapshot())
    write_script(laptop, 'base')
    laptop.snapshot()
    write_script(desktop, 'new remote value')
    assert not laptop.apply(desktop.snapshot()).conflicts
    assert next(iter(laptop.snapshot().values())).value['actions'][0][1]['message'] == 'new remote value'
    write_script(laptop, 'edit of the old active source')
    assert len(laptop.snapshot()) == 2


def test_source_deletion_is_versioned_but_does_not_delete_a_receivers_active_script(tmp_path):
    desktop, laptop = script_adapter(tmp_path, 'desktop'), script_adapter(tmp_path, 'laptop')
    write_script(desktop, 'base')
    original = desktop.snapshot()
    laptop.apply(original)
    write_script(laptop, 'base')
    laptop.snapshot()
    (desktop.source_root / 'login.json').unlink()
    deleted = desktop.snapshot()
    assert next(iter(deleted.values())).is_deleted
    laptop.apply(deleted)
    laptop.apply(original)
    assert next(iter(laptop.snapshot().values())).is_deleted
    assert (laptop.source_root / 'login.json').is_file()
    assert laptop.definitions() == {}


def test_settings_entry_names_are_sensitive_and_only_references_enter_sync_state(tmp_path):
    path = tmp_path / 'settings.json'
    path.write_text(json.dumps({'password': 'local-only', 'theme': 'dark'}))
    unbound = ac.SettingsSyncAdapter(path, state(tmp_path, 'desktop'))
    with pytest.raises(ac.ConfigSyncError):
        unbound.snapshot()
    assert not (tmp_path / 'state.sqlite3').exists()
    bindings = ac.SyncBindings(fields={'password': {'/value': ac.SyncReference('secret', 'PASSWORD')}})
    adapter = ac.SettingsSyncAdapter(path, state(tmp_path, 'desktop'), bindings=bindings)
    wire = json.dumps([entry.to_dict() for entry in adapter.snapshot().values()])
    assert 'local-only' not in wire
    result = ac.materialize_sync_profile((adapter,), tmp_path / 'cache')
    assert json.loads((result.directory / 'settings.json').read_text())['password'] == '${secrets.PASSWORD}'


def test_same_operation_with_changed_data_is_refused_and_existing_heads_survive(tmp_path):
    sender, receiver = script_adapter(tmp_path, 'desktop'), script_adapter(tmp_path, 'laptop')
    write_script(sender, 'first')
    original = sender.snapshot()
    receiver.apply(original)
    old = next(iter(original.values()))
    changed = ac.SyncEntry(old.section, old.entry_id, {'actions': [['AC_log', {'message': 'changed'}]]},
                           old.version, old.operation_id, old.origin)
    with pytest.raises(ac.ConfigSyncError):
        receiver.apply({changed.change_id: changed})
    assert receiver.snapshot() == original


def test_receipt_or_head_storage_failure_rolls_back_the_complete_batch(tmp_path):
    import sqlite3
    receiver = script_adapter(tmp_path, 'laptop')
    assert receiver.snapshot() == {}
    with sqlite3.connect(tmp_path / 'laptop.sqlite3') as connection:
        connection.execute("CREATE TRIGGER stop_second BEFORE INSERT ON adapter_heads "
                           "WHEN NEW.entry_id='second.json' BEGIN SELECT RAISE(ABORT,'controlled failure'); END")
    entries = [ac.SyncEntry('scripts', name, {'actions': []}, {'desktop': 1}, name, 'desktop')
               for name in ('first.json', 'second.json')]
    with pytest.raises(ac.ConfigStoreError):
        receiver.apply({entry.change_id: entry for entry in entries})
    assert receiver.snapshot() == {}


def test_materialization_refuses_an_escaping_custom_profile_before_creating_files(tmp_path):
    class EscapingProfile:
        kind = 'scripts'
        def checkpoint(self):
            pass
        def profile_files(self):
            return {'../outside.txt': b'not allowed'}
    with pytest.raises(ac.ConfigSyncError):
        ac.materialize_sync_profile((EscapingProfile(),), tmp_path / 'cache')
    assert not (tmp_path / 'outside.txt').exists() and not (tmp_path / 'cache').exists()


def test_delete_edit_conflict_can_be_explicitly_resolved_as_a_tombstone(tmp_path):
    desktop, laptop = script_adapter(tmp_path, 'desktop'), script_adapter(tmp_path, 'laptop')
    write_script(desktop, 'base')
    laptop.apply(desktop.snapshot())
    write_script(laptop, 'base')
    laptop.snapshot()
    (desktop.source_root / 'login.json').unlink()
    write_script(laptop, 'parallel edit')
    assert laptop.apply(desktop.snapshot()).conflicts == ('login.json',)
    heads = laptop.snapshot()
    laptop.resolve('login.json', {}, observed=tuple(heads), is_deleted=True)
    assert next(iter(laptop.snapshot().values())).is_deleted
    assert laptop.definitions() == {}


def test_wrapped_source_cancellation_preserves_its_signal_and_makes_no_state(tmp_path):
    from concurrent.futures import CancelledError
    class InterruptedSource:
        def list_bindings(self):
            raise ac.ConfigSyncError('wrapped source cancellation') from CancelledError()
    adapter = ac.HotkeySyncAdapter(InterruptedSource(), state(tmp_path, 'desktop'))
    with pytest.raises(CancelledError):
        adapter.snapshot()
    assert not (tmp_path / 'state.sqlite3').exists()


def test_corrupted_native_repository_fails_with_typed_error_before_state(tmp_path):
    path = tmp_path / 'locators.json'
    repository = ac.ElementRepository(str(path))
    repository.save('submit', name='Submit')
    adapter = ac.LocatorSyncAdapter(repository, state(tmp_path, 'desktop'))
    path.write_text('[]', encoding='utf-8')
    with pytest.raises(ac.ConfigSyncError, match='source'):
        adapter.snapshot()
    assert not (tmp_path / 'state.sqlite3').exists()
    assert path.read_text(encoding='utf-8') == '[]'


@pytest.mark.parametrize('extreme', [10 ** 400, -10 ** 400])
def test_extreme_integer_condition_is_refused_with_typed_error_before_state(tmp_path, extreme):
    profile = {'schema_version': 1, 'kind': 'triggers', 'state_path': str(tmp_path / 'state.sqlite3'),
               'identity': {'endpoint': 'https://controlled.invalid', 'user_id': 'alice', 'origin': 'desktop'},
               'source': {'records': {'watch': {'kind': 'file', 'script_path': 'run.json', 'repeat': True,
                                              'cooldown_seconds': extreme,
                                              'condition': {'watch_path': 'watched'}}}}}
    adapter = ac.adapter_from_profile(profile)
    with pytest.raises(ac.ConfigSyncError, match='number'):
        adapter.snapshot()
    assert not (tmp_path / 'state.sqlite3').exists()


def test_private_posix_path_binding_is_not_a_high_entropy_credential():
    from je_auto_control.utils.logging.secret_scope import remember_secret, secret_log_scope
    from je_auto_control.utils.secrets_scan.secrets_scan import scan_secrets
    path = '/tmp/pytest-of-runner/pytest-0/test_sync_never_enables_trigger0/watched'
    assert scan_secrets({'value': path})[0]['kind'] == 'high-entropy-string'
    assert ac.SyncBindings(local_values={'watch': path}).local_values['watch'] == path
    for value in ('AbCdEfGhIjKlMnOpQrStUvWxYz0123456789', path + '/AKIA' + 'A1' * 8):
        with pytest.raises(ac.ConfigSyncError):
            ac.SyncBindings(local_values={'watch': value})
    with secret_log_scope():
        remember_secret(path)
        with pytest.raises(ac.ConfigSyncError, match='resolved credentials'):
            ac.SyncBindings(local_values={'watch': path})


def test_non_ascii_corrupt_head_wire_raises_a_framework_storage_error(tmp_path):
    import sqlite3
    adapter = script_adapter(tmp_path, 'desktop')
    write_script(adapter, 'base')
    adapter.snapshot()
    with sqlite3.connect(tmp_path / 'desktop.sqlite3') as connection:
        connection.execute("UPDATE adapter_heads SET wire='壞掉的資料'")
    with pytest.raises(ac.ConfigStoreError):
        adapter.snapshot()


def test_device_connections_are_local_references_and_numeric_bindings_keep_their_type(tmp_path):
    sender = script_adapter(tmp_path, 'desktop')
    actions = [['AC_example', {'device_id': 'sender-device', 'screen_index': 1}]]
    (sender.source_root / 'login.json').write_text(json.dumps(actions))
    with pytest.raises(ac.ConfigSyncError):
        sender.snapshot()
    fields = {'login.json': {'/actions/0/1/device_id': ac.SyncReference('local', 'phone'),
                             '/actions/0/1/screen_index': ac.SyncReference('local', 'display')}}
    sender = script_adapter(tmp_path, 'desktop', bindings=ac.SyncBindings(fields=fields))
    entries = sender.snapshot()
    assert 'sender-device' not in json.dumps([item.to_dict() for item in entries.values()])
    receiver = script_adapter(tmp_path, 'laptop',
                               bindings=ac.SyncBindings(local_values={'phone': 'receiver-device', 'display': 2}))
    receiver.apply(entries)
    result = ac.materialize_sync_profile((receiver,), tmp_path / 'cache')
    arguments = json.loads((result.directory / 'scripts' / 'login.json').read_text())[0][1]
    assert arguments == {'device_id': 'receiver-device', 'screen_index': 2}


def test_positional_secret_commands_cannot_export_a_plaintext_value(tmp_path):
    sender = script_adapter(tmp_path, 'desktop')
    path = sender.source_root / 'login.json'
    for value in ('local-only-password', 0, False):
        path.write_text(json.dumps([['AC_write_secret', [value]]]))
        with pytest.raises(ac.ConfigSyncError):
            sender.snapshot()
    path.write_text(json.dumps([['AC_write_secret', {'secret': '${secrets.LOGIN}'}]]))
    wire = json.dumps([entry.to_dict() for entry in sender.snapshot().values()])
    assert 'local-only-password' not in wire


def test_cancel_after_first_merge_rolls_back_heads_receipts_and_source_baselines(tmp_path, monkeypatch):
    from concurrent.futures import CancelledError
    from threading import Event
    import je_auto_control.utils.config_sync.adapter_state as state_module
    stop = Event()
    def checkpoint():
        if stop.is_set():
            raise CancelledError()
    directory = tmp_path / 'receiver'
    directory.mkdir()
    identity = ac.SyncLocalIdentity('https://controlled.invalid', 'alice', 'receiver', 0, 0)
    ledger = ac.SyncAdapterState(tmp_path / 'cancel.sqlite3', identity, checkpoint=checkpoint)
    adapter = ac.ScriptSyncAdapter(directory, ledger, paths=())
    adapter.snapshot()
    original = state_module.merge_head
    def after_merge(*args):
        result = original(*args)
        stop.set()
        return result
    monkeypatch.setattr(state_module, 'merge_head', after_merge)
    incoming = [ac.SyncEntry('scripts', name, {'actions': []}, {'sender': 1}, name, 'sender')
                for name in ('one.json', 'two.json')]
    with pytest.raises(CancelledError):
        adapter.apply({entry.change_id: entry for entry in incoming})
    stop.clear()
    assert adapter.snapshot() == {}


def test_local_reference_type_errors_are_reported_without_losing_portable_versions(tmp_path):
    engine = ac.TriggerEngine(executor=lambda _actions: None)
    script = str(tmp_path / 'script.json')
    engine.add(ac.WindowAppearsTrigger(trigger_id='window', script_path=script, title_substring='Demo', repeat=True))
    fields = {'window': {'/repeat': ac.SyncReference('local', 'repeatSetting')}}
    sender = ac.TriggerSyncAdapter(engine, state(tmp_path, 'desktop', 'sender.sqlite3'),
                                    bindings=ac.SyncBindings(fields=fields, local_values={'script': script}))
    incoming = sender.snapshot()
    empty = ac.TriggerEngine(executor=lambda _actions: None)
    local_state = state(tmp_path, 'laptop', 'receiver.sqlite3')
    receiver = ac.TriggerSyncAdapter(empty, local_state,
        bindings=ac.SyncBindings(local_values={'script': script, 'repeatSetting': 'wrong-type'}))
    assert receiver.apply(incoming).unresolved == ('window:local-value-type',)
    assert receiver.snapshot() == incoming
    corrected = ac.TriggerSyncAdapter(empty, local_state,
        bindings=ac.SyncBindings(local_values={'script': script, 'repeatSetting': False}))
    assert corrected.definitions()['window']['repeat'] is False
    assert empty.list_triggers() == []


def test_foreign_database_is_refused_without_adding_profile_tables(tmp_path):
    import sqlite3
    path = tmp_path / 'foreign.sqlite3'
    with sqlite3.connect(path) as connection:
        connection.execute('CREATE TABLE important (value TEXT)')
        connection.execute("INSERT INTO important VALUES ('keep')")
    ledger = state(tmp_path, 'desktop', 'foreign.sqlite3')
    with pytest.raises(ac.ConfigStoreError):
        ledger.heads('scripts')
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall() == [('important',)]
        assert connection.execute('SELECT value FROM important').fetchone()[0] == 'keep'


@pytest.mark.parametrize('interrupted', [False, True])
def test_profile_staging_io_failure_is_typed_and_wrapped_cancellation_stays_control_flow(tmp_path, monkeypatch,
                                                                                       interrupted):
    from concurrent.futures import CancelledError
    from pathlib import Path
    adapter = script_adapter(tmp_path, 'desktop')
    write_script(adapter, 'base')
    adapter.snapshot()
    def failed_write(_path, _body):
        if interrupted:
            raise OSError('interrupted write') from CancelledError()
        raise OSError('controlled unavailable storage')
    monkeypatch.setattr(Path, 'write_bytes', failed_write)
    expected = CancelledError if interrupted else ac.ConfigSyncError
    with pytest.raises(expected):
        ac.materialize_sync_profile((adapter,), tmp_path / 'cache')
    assert not (tmp_path / 'cache').exists()
