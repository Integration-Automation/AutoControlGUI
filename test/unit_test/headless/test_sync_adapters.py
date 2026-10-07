"""Draft C3 contracts to activate only after the C2 closure gate."""
import hashlib
import json
from threading import Event
import pytest

_APPLICATION = None


class MemoryAssets:
    def __init__(self, contents):
        self.contents = contents

    def iter_chunks(self, asset):
        yield self.contents[asset.sha256]


def asset_manifest(root, content=b'template pixels', path='images/template.png'):
    from je_auto_control.utils.config_sync.assets import AssetManifest, AssetSpec
    digest = hashlib.sha256(content).hexdigest()
    return AssetManifest(root=root, assets=(AssetSpec(path, digest, len(content)),)), digest


def test_script_asset_hash_round_trip(tmp_path):
    from je_auto_control.utils.config_sync.assets import sync_assets
    content = b'template pixels'
    manifest, source_hash = asset_manifest(tmp_path / 'received', content)
    result = sync_assets(manifest, MemoryAssets({source_hash: content}))
    received_hash = hashlib.sha256((tmp_path / 'received/images/template.png').read_bytes()).hexdigest()
    assert received_hash == source_hash
    assert len(result.saved) == 1


def test_corrupt_asset_preserves_existing_file(tmp_path):
    from je_auto_control.utils.config_sync.assets import AssetSyncError, sync_assets
    root = tmp_path / 'received'
    (root / 'images').mkdir(parents=True)
    destination = root / 'images/template.png'
    destination.write_bytes(b'existing pixels')
    manifest, digest = asset_manifest(root)
    with pytest.raises(AssetSyncError):
        sync_assets(manifest, MemoryAssets({digest: b'bad bytes'}))
    assert destination.read_bytes() == b'existing pixels'
    assert not list(root.rglob('.sync-*'))


def test_cancelled_asset_does_not_replace_a_partial_file(tmp_path):
    from je_auto_control.utils.config_sync.assets import sync_assets
    manifest, digest = asset_manifest(tmp_path / 'received')
    cancelled = Event()

    class Interrupted:
        def iter_chunks(self, _asset):
            yield b'template '
            cancelled.set()
            yield b'pixels'

    result = sync_assets(manifest, Interrupted(), cancel=cancelled)
    assert result.cancelled is True and result.saved == ()
    assert not (tmp_path / 'received/images/template.png').exists()
    assert not list((tmp_path / 'received').rglob('.sync-*'))


def test_secret_is_local():
    from je_auto_control.utils.config_sync.adapters import JsonDefinitionAdapter
    source = {'one': {'password': 'source-private', 'script_path': 'C:/machine/script.json', 'label': 'shared'}}
    snapshot = JsonDefinitionAdapter('scripts', source, device_id='a').snapshot()
    sync_payload_contains_secret = 'source-private' in json.dumps({k: v.to_dict() for k, v in snapshot.items()})
    assert sync_payload_contains_secret is False
    target = {'one': {'password': 'target-private', 'script_path': 'D:/local/script.json'}}
    received = JsonDefinitionAdapter('scripts', target, device_id='b')
    assert received.apply(snapshot).applied == ('one',)
    assert target['one']['password'] == 'target-private'
    assert target['one']['script_path'] == 'D:/local/script.json'
    assert target['one']['label'] == 'shared'


def test_sync_never_enables_trigger(tmp_path):
    from je_auto_control.utils.triggers.trigger_engine import TriggerEngine, FilePathTrigger
    from je_auto_control.utils.config_sync.adapters import TriggerSyncAdapter
    source = TriggerEngine()
    source.add(FilePathTrigger(script_path=str(tmp_path / 'source.json'), trigger_id='one',
                               watch_path=str(tmp_path / 'source.watch'), enabled=True))
    snapshot = TriggerSyncAdapter(source, device_id='a').snapshot()
    target = TriggerEngine()
    target.add(FilePathTrigger(script_path=str(tmp_path / 'target.json'), trigger_id='one',
                               watch_path=str(tmp_path / 'target.watch'), enabled=False))
    report = TriggerSyncAdapter(target, device_id='b').apply(snapshot)
    enabled_triggers = [trigger for trigger in target.list_triggers() if trigger.enabled]
    assert enabled_triggers == []
    assert report.applied == ('one',)
    assert target.list_triggers()[0].script_path == str(tmp_path / 'target.json')
    assert not target.is_running


def test_clipboard_does_not_echo():
    from je_auto_control.utils.remote_desktop.clipboard_sync import ClipboardLoopGuard
    a, b = ClipboardLoopGuard(origin='a'), ClipboardLoopGuard(origin='b')
    payload = a.encode_text('hello')
    assert payload is not None
    assert b.receive(payload) == ('text', 'hello')
    assert b.encode_text('hello') is None
    assert b.receive(payload) is None
    assert a.receive(payload) is None


@pytest.mark.parametrize('path', ['../outside', '/absolute', 'C:/machine/file', 'folder/../file', 'file:stream'])
def test_asset_rejects_escaping_paths(tmp_path, path):
    from je_auto_control.utils.config_sync.assets import AssetSyncError
    with pytest.raises(AssetSyncError):
        asset_manifest(tmp_path, path=path)


def test_disconnected_asset_preserves_existing_file(tmp_path):
    from je_auto_control.utils.config_sync.assets import AssetSyncError, sync_assets
    manifest, _ = asset_manifest(tmp_path)
    destination = tmp_path / 'images/template.png'
    destination.parent.mkdir()
    destination.write_bytes(b'previous')

    class Disconnected:
        def iter_chunks(self, _asset):
            yield b'template '
            raise OSError('disconnected')

    with pytest.raises(AssetSyncError):
        sync_assets(manifest, Disconnected())
    assert destination.read_bytes() == b'previous'
    assert not list(tmp_path.rglob('.sync-*'))


def test_unchanged_definition_keeps_operation_and_deletion_version():
    from je_auto_control.utils.config_sync.adapters import JsonDefinitionAdapter
    definitions = {'one': {'label': 'one'}}
    state = {}
    adapter = JsonDefinitionAdapter('scripts', definitions, device_id='a', state=state)
    initial = adapter.snapshot()['one']
    assert adapter.snapshot()['one'] == initial
    adapter = JsonDefinitionAdapter('scripts', definitions, device_id='a', state=state)
    assert adapter.snapshot()['one'] == initial
    definitions.clear()
    deleted = adapter.snapshot()['one']
    assert deleted.is_deleted and deleted.version['a'] == 2
    assert adapter.snapshot()['one'] == deleted


def test_script_positional_secret_and_confidential_write_stay_local():
    from je_auto_control.utils.config_sync.adapters import ScriptSyncAdapter
    source = {'one': {'actions': [['AC_write', {'text': 'private-text', 'secret': True}]]}}
    exported = ScriptSyncAdapter(source, device_id='a').snapshot()
    assert 'private-text' not in json.dumps({key: value.to_dict() for key, value in exported.items()})
    receiver = ScriptSyncAdapter({}, device_id='b')
    assert receiver.apply(exported).unresolved == ('one',)


def test_synced_hotkey_is_disabled_before_registration(tmp_path):
    from je_auto_control.utils.config_sync.adapters import HotkeySyncAdapter
    from je_auto_control.utils.hotkey.hotkey_daemon import HotkeyDaemon
    source, target = HotkeyDaemon(), HotkeyDaemon()
    source.bind('ctrl+alt+1', str(tmp_path / 'source.json'), 'one')
    target.bind('ctrl+alt+2', str(tmp_path / 'target.json'), 'one')
    seen = []
    original = target.bind

    def bind(*args, **kwargs):
        seen.append(kwargs.get('enabled'))
        return original(*args, **kwargs)

    target.bind = bind
    report = HotkeySyncAdapter(target, device_id='b').apply(HotkeySyncAdapter(source, device_id='a').snapshot())
    assert report.applied == ('one',) and seen == [False]
    assert not target.list_bindings()[0].enabled
    assert not target.is_running


def test_actual_tcp_viewer_suppresses_received_clipboard_echo():
    from je_auto_control.utils.remote_desktop.viewer import RemoteDesktopViewer
    from je_auto_control.utils.remote_desktop.clipboard_sync import ClipboardLoopGuard
    from unittest.mock import Mock
    viewer = RemoteDesktopViewer('localhost', 4321, 'token', on_clipboard=Mock())
    viewer._connected = True
    viewer._channel = Mock()
    payload = ClipboardLoopGuard(origin='peer').encode_text('incoming')
    viewer._handle_clipboard_payload(payload)
    viewer.send_clipboard_text('incoming')
    viewer._channel.send_typed.assert_not_called()
    viewer._on_clipboard.assert_called_once_with('text', 'incoming')
    viewer._handle_clipboard_payload(payload)
    assert viewer._on_clipboard.call_count == 1


def test_folder_received_content_does_not_echo(tmp_path, monkeypatch):
    from je_auto_control.utils.remote_desktop.file_sync import FolderSyncEngine
    from pathlib import Path
    sent = []
    payloads = []
    completed = Event()
    observed = Event()

    def sender(path, name):
        payloads.append(Path(path).read_bytes())
        sent.append(name)
        completed.set()

    engine = FolderSyncEngine(watch_dir=tmp_path, sender=sender, poll_interval_s=0.5)
    original_push = engine._push_if_changed
    polls = []

    def observe_push(relative, identity, previous, stop):
        original_push(relative, identity, previous, stop)
        if relative == 'received.txt':
            polls.append(relative)
            if len(polls) >= 2:
                observed.set()

    monkeypatch.setattr(engine, '_push_if_changed', observe_push)
    engine.start()
    try:
        assert engine.wait_until_ready()
        path = tmp_path / 'received.txt'
        path.write_bytes(b'incoming bytes')
        engine.mark_received(path)
        # Require actual processing before asserting absence of an echo.
        assert observed.wait(5)
        assert sent == []
        stamp = path.stat().st_mtime_ns
        path.write_bytes(b'local new bytes')
        import os
        os.utime(path, ns=(stamp, stamp))
        assert completed.wait(5)
    finally:
        engine.stop()
    assert sent == ['received.txt']
    assert payloads == [b'local new bytes']


def test_sync_preview_is_explicit_and_keeps_local_credentials(tmp_path, monkeypatch):
    from je_auto_control.utils.config_sync import service
    from je_auto_control.utils.config_sync.models import ConfigBucket
    from je_auto_control.utils.config_sync.causal_bucket import causal_upsert
    definitions = tmp_path / 'definitions.json'
    definitions.write_text(json.dumps({'scripts': {'one': {'password': 'local-password', 'label': 'old'}}}))
    remote = ConfigBucket('account', revision=7)
    causal_upsert(remote, 'scripts', 'one', {'label': 'remote', 'password': {'$local': '/password'}}, device_id='other')
    from unittest.mock import Mock
    client = Mock()
    client.device_id = 'device'
    client.cas_supported = True
    client.last_successful_revision = 0
    client.fetch.return_value = remote
    client.pending_operations.return_value = ()
    client.recovery_status.return_value = {}
    monkeypatch.setattr(service, '_client', lambda *args, **kwargs: client)
    result = service.config_sync_preview(str(definitions), str(tmp_path / 'sync'), 'http://example.test', 'account')
    assert result['revision'] == 7 and not result['offline']
    assert 'local-password' not in json.dumps(result)
    assert json.loads(definitions.read_text())['scripts']['one']['label'] == 'old'
    assert result['conflicts'] == 1
    client.close.assert_called_once()


def test_sync_apply_refuses_changed_local_baseline(tmp_path):
    from je_auto_control.utils.config_sync.service import config_sync_apply
    from je_auto_control.utils.config_sync.models import ConfigSyncError
    definitions = tmp_path / 'definitions.json'
    definitions.write_text('{}')
    preview = tmp_path / 'preview.json'
    preview.write_text(json.dumps({'definitions_sha256': hashlib.sha256(b'previous').hexdigest(),
                                   'sections': {'scripts': {'one': {'label': 'incoming'}}}}))
    with pytest.raises(ConfigSyncError):
        config_sync_apply(str(definitions), str(preview), str(tmp_path / 'state.json'), 'device')
    assert definitions.read_text() == '{}'


def test_sync_panel_cancel_releases_worker_and_client(tmp_path, monkeypatch):
    from je_auto_control.gui.config_sync_tab import ConfigSyncTab
    from je_auto_control.utils.config_sync import service
    entered, released = Event(), Event()

    def preview(*args, cancel, **kwargs):
        entered.set()
        try:
            assert cancel.wait(3)
            return {'cancelled': True, 'pending': 1, 'revision': 0, 'conflicts': 0, 'offline': True}
        finally:
            released.set()

    monkeypatch.setattr(service, 'config_sync_preview', preview)
    from PySide6.QtWidgets import QApplication
    import time
    global _APPLICATION
    _APPLICATION = QApplication.instance() or QApplication([])
    app = _APPLICATION
    tab = ConfigSyncTab()
    tab.definitions.setText(str(tmp_path / 'definitions.json'))
    tab.workspace.setText(str(tmp_path / 'sync'))
    tab.server.setText('http://example.test')
    tab.user.setText('account')
    tab._preview()
    assert entered.wait(3)
    tab._cancel()
    assert released.wait(3)
    deadline = time.monotonic() + 3
    while tab._worker is not None and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    assert tab._worker is None
    assert tab.results.isReadOnly()
    tab.close()
    tab.deleteLater()
    from PySide6.QtCore import QCoreApplication, QEvent
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()


def test_script_positional_service_secret_is_local():
    from je_auto_control.utils.config_sync.adapters import ScriptSyncAdapter
    source = {'one': {'actions': [['AC_config_sync_exchange',
                                  ['definitions.json', 'sync', 'http://example.test', 'account', 'private-secret']]]}}
    snapshot = ScriptSyncAdapter(source, device_id='a').snapshot()
    assert 'private-secret' not in json.dumps({key: value.to_dict() for key, value in snapshot.items()})


def test_definition_boolean_edit_advances_version():
    from je_auto_control.utils.config_sync.adapters import JsonDefinitionAdapter
    definitions = {'one': {'flag': True}}
    adapter = JsonDefinitionAdapter('locators', definitions, device_id='a')
    first = adapter.snapshot()['one']
    definitions['one']['flag'] = 1
    changed = adapter.snapshot()['one']
    assert changed.operation_id != first.operation_id and changed.version['a'] == 2


@pytest.mark.parametrize('path', ['NUL', 'images/CON.png', 'file. ', 'images/file.'])
def test_asset_rejects_windows_redirected_paths(tmp_path, path):
    from je_auto_control.utils.config_sync.assets import AssetSyncError
    with pytest.raises(AssetSyncError):
        asset_manifest(tmp_path, path=path)


def test_apply_conflict_requires_explicit_choice_and_advances_after_both(tmp_path):
    from je_auto_control.utils.config_sync.service import config_sync_apply
    from je_auto_control.utils.config_sync.models import ConfigBucket
    from je_auto_control.utils.config_sync.causal_bucket import causal_upsert, merge_causal_buckets
    from je_auto_control.utils.config_sync.definition_files import read_object
    destination = tmp_path / 'definitions.json'
    destination.write_text(json.dumps({'locators': {'one': {'label': 'local'}}}))
    left, right = ConfigBucket('account'), ConfigBucket('account')
    causal_upsert(left, 'locators', 'one', {'label': 'local'}, device_id='a')
    causal_upsert(right, 'locators', 'one', {'label': 'remote'}, device_id='b')
    merged, _ = merge_causal_buckets(left, right)
    preview = tmp_path / 'preview.json'
    preview.write_text(json.dumps({'bucket': merged.to_dict(), 'device_id': 'a',
                                   'definitions_sha256': hashlib.sha256(destination.read_bytes()).hexdigest()}))
    report = config_sync_apply(str(destination), str(preview), str(tmp_path / 'state.json'), 'a',
                               choices={'locators/one': 1})
    assert report['conflicts'] == 0 and report['applied'] == ['locators/one']
    metadata = read_object(tmp_path / 'state.json')['sections']['locators']['one']['_sync']
    assert metadata['version'] == {'a': 2, 'b': 1}


def test_apply_does_not_publish_definition_before_required_asset_integrity(tmp_path):
    from je_auto_control.utils.config_sync.service import config_sync_apply
    from je_auto_control.utils.config_sync.models import ConfigBucket
    from je_auto_control.utils.config_sync.causal_bucket import causal_upsert
    destination = tmp_path / 'definitions.json'
    destination.write_text('{}')
    original = destination.read_bytes()
    remote = ConfigBucket('account')
    causal_upsert(remote, 'scripts', 'one', {'label': 'requires image', 'assets': [
        {'path': 'images/template.png', 'sha256': hashlib.sha256(b'pixels').hexdigest(), 'size': 6}]}, device_id='b')
    preview = tmp_path / 'preview.json'
    preview.write_text(json.dumps({'bucket': remote.to_dict(), 'device_id': 'a',
                                   'definitions_sha256': hashlib.sha256(original).hexdigest()}))
    report = config_sync_apply(str(destination), str(preview), str(tmp_path / 'state.json'), 'a')
    assert report['unresolved'] == ['scripts/one'] and report['applied'] == []
    assert 'one' not in json.loads(destination.read_text()).get('scripts', {})


def test_address_book_keeps_same_host_at_distinct_endpoints(tmp_path):
    from je_auto_control.utils.config_sync.adapters import AddressBookSyncAdapter
    from je_auto_control.utils.remote_desktop.address_book import AddressBook
    book = AddressBook(tmp_path / 'source.json')
    book.upsert(host_id='host', server_url='http://one.test', label='first')
    book.upsert(host_id='host', server_url='http://two.test', label='second')
    snapshot = AddressBookSyncAdapter(book, device_id='a').snapshot()
    assert len(snapshot) == 2
    target = AddressBook(tmp_path / 'target.json')
    report = AddressBookSyncAdapter(target, device_id='b').apply(snapshot)
    assert len(report.applied) == 2
    assert {item['server_url'] for item in target.list_entries()} == {'http://one.test', 'http://two.test'}


def test_cancelled_causal_exchange_does_not_dispatch_or_enqueue(tmp_path, monkeypatch):
    from je_auto_control.utils.config_sync import ConfigSyncClient, SyncClientOptions, ConfigBucket, ConfigSyncError
    from unittest.mock import Mock
    client = ConfigSyncClient('http://example.test', user_id='account',
                               options=SyncClientOptions(outbox_path=tmp_path / 'outbox.sqlite', device_id='a'))
    request = Mock()
    monkeypatch.setattr(client, '_request', request)
    cancel = Event()
    cancel.set()
    try:
        with pytest.raises(ConfigSyncError):
            client.sync(ConfigBucket('account'), cancel=cancel)
        request.assert_not_called()
        assert client.pending_operations() == ()
    finally:
        client.close()


def test_definition_service_real_protected_exchange_and_local_apply(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from je_auto_control.utils.remote_desktop.signaling_server import create_app
    from je_auto_control.utils.http_client import http_client
    from je_auto_control.utils.config_sync.service import config_sync_exchange, config_sync_preview, config_sync_apply
    source, target = tmp_path / 'source.json', tmp_path / 'target.json'
    source.write_text(json.dumps({'scripts': {'one': {'password': 'source-password', 'label': 'portable'}}}))
    target.write_text(json.dumps({'scripts': {'one': {'password': 'target-password', 'label': 'portable'}}}))
    app = create_app(shared_secret='server-secret', serve_web_viewer=False,
                     config_store_path=tmp_path / 'server.sqlite')
    with TestClient(app) as server:
        def perform(call):
            response = server.request(call['method'], call['url'], headers=call['headers'], content=call['body'])
            return {'status': response.status_code, 'text': response.text}

        monkeypatch.setattr(http_client, 'perform_call', perform)
        outgoing = config_sync_exchange(str(source), str(tmp_path / 'a'), 'http://testserver',
                                        'account', 'server-secret')
        assert outgoing['revision'] == 1 and outgoing['pending'] == 0 and outgoing['cas_supported']
        incoming = config_sync_preview(str(target), str(tmp_path / 'b'), 'http://testserver',
                                       'account', 'server-secret')
        assert incoming['revision'] == 1
        assert 'source-password' not in json.dumps(incoming)
        # Independently registered values have independent causal identities, even if equal.
        choices = {'scripts/one': 0} if incoming['conflicts'] else {}
        report = config_sync_apply(str(target), incoming['preview_path'], incoming['state_path'], incoming['device_id'],
                                   choices=choices)
        assert report['conflicts'] == 0 and report['unresolved'] == []
        assert json.loads(target.read_text())['scripts']['one']['password'] == 'target-password'
        assert b'source-password' not in (tmp_path / 'server.sqlite').read_bytes()
        for database in (tmp_path / 'a').rglob('outbox.sqlite'):
            assert b'server-secret' not in database.read_bytes()


def test_config_sync_surfaces_share_services_and_scoped_paths(tmp_path):
    from je_auto_control.utils.executor.action_executor import executor
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    from je_auto_control.utils.config_sync.service import config_sync_status
    from je_auto_control.utils.path_guard.policy import PathPolicy, path_policy_scope
    from je_auto_control.utils.path_guard.path_guard import PathNotAllowedError
    from je_auto_control.gui.script_builder.command_schema import COMMAND_SPECS
    tools = {tool.name: tool for tool in build_default_tool_registry(aliases=False)}
    assert executor.event_dict['AC_config_sync_status'] is config_sync_status
    assert tools['ac_config_sync_status'].handler is config_sync_status
    assert 'AC_config_sync_status' in COMMAND_SPECS
    with path_policy_scope(PathPolicy([tmp_path / 'allowed'])):
        with pytest.raises(PathNotAllowedError):
            config_sync_status(str(tmp_path / 'outside'), 'http://example.test', 'account')
    assert not (tmp_path / 'outside').exists()


def test_unknown_server_section_cannot_bypass_definition_privacy(tmp_path, monkeypatch):
    from je_auto_control.utils.config_sync import service, ConfigBucket, ConfigSyncError
    from unittest.mock import Mock
    definitions = tmp_path / 'definitions.json'
    definitions.write_text('{}')
    client = Mock()
    client.device_id = 'a'
    client.pending_operations.return_value = ()
    client.last_successful_revision = 0
    client.fetch.return_value = ConfigBucket('account', sections={'unreviewed': {'one': {'password': 'private'}}})
    monkeypatch.setattr(service, '_client', lambda *args: client)
    with pytest.raises(ConfigSyncError):
        service.config_sync_preview(str(definitions), str(tmp_path / 'workspace'), 'http://example.test', 'account')
    assert not list((tmp_path / 'workspace').rglob('preview.json'))
    client.close.assert_called_once()


def test_confidential_literal_echo_is_not_exported_under_another_field():
    from je_auto_control.utils.config_sync.adapters import JsonDefinitionAdapter
    source = {'one': {'password': 'private-literal', 'label': 'echo: private-literal'}}
    payload = JsonDefinitionAdapter('scripts', source, device_id='a').snapshot()
    assert 'private-literal' not in json.dumps({key: value.to_dict() for key, value in payload.items()})


def test_received_disabled_hotkey_never_reaches_listener_snapshot(tmp_path):
    from je_auto_control.utils.hotkey.hotkey_daemon import HotkeyDaemon
    daemon = HotkeyDaemon()
    daemon.bind('ctrl+alt+1', str(tmp_path / 'received.json'), 'received', enabled=False)
    daemon.bind('ctrl+alt+2', str(tmp_path / 'local.json'), 'local')
    assert [binding.binding_id for binding in daemon._active_bindings()] == ['local']
