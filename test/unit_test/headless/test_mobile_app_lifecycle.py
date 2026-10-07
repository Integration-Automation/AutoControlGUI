"""App operations own their sessions, observe state and never fake extension support."""
import importlib
import subprocess
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest


def _api():
    return importlib.import_module('je_auto_control.api.mobile')


@pytest.fixture
def app_sdk(monkeypatch):
    calls = []
    running = set()
    sessions = set()

    class WDA:
        def __init__(self, url, _session_id=None):
            self.url = url
            self.session_id = _session_id or 'borrowed'

        def unregister_callback(self):
            pass

        def _fetch(self, method, path, data=None, with_session=False, timeout=None):
            calls.append((method, path, data, with_session, timeout))
            if path == '/status' and method == 'GET':
                return SimpleNamespace(sessionId=next(iter(sessions), None), value={'ready': True})
            if path == '/session' and method == 'POST':
                sid = f'owned-{len(sessions)}'
                sessions.add(sid)
                return SimpleNamespace(sessionId=sid, value={'sessionId': sid})
            if method == 'DELETE':
                sessions.discard(path.rsplit('/', 1)[-1])
                return SimpleNamespace(value=None)
            bundle = (data or {}).get('bundleId')
            if path.endswith('/launch'):
                running.add(bundle)
            if path.endswith('/terminate'):
                running.discard(bundle)
                return SimpleNamespace(value=True)
            return SimpleNamespace(value=4 if bundle in running else 1)

    wda = ModuleType('wda')
    wda.Client = WDA
    transport_calls = []

    def http(url, method='GET', data=None, timeout=None):
        from urllib.parse import urlsplit
        path = urlsplit(url).path
        transport_calls.append((method, path, timeout))
        if path.startswith('/session/owned-') and method != 'DELETE':
            path = '/' + path.split('/', 3)[-1]
        return WDA(url)._fetch(method, path, data, timeout=timeout)

    wda._unsafe_httpdo = http
    monkeypatch.setitem(sys.modules, 'wda', wda)

    def adb(args, **kwargs):
        calls.append(('adb', args, kwargs))
        if 'monkey' in args:
            running.add(args[args.index('-p') + 1])
        if 'force-stop' in args:
            running.discard(args[-1])
        if 'pidof' in args:
            output = b'123\n' if args[-1] in running else b''
            return subprocess.CompletedProcess(args, 0 if output else 1, output, b'')
        return subprocess.CompletedProcess(args, 0, b'Events injected: 1\n', b'')

    monkeypatch.setattr('je_auto_control.wrapper._mobile_adb.OwnedAdbClient.run', lambda self, args, **kw: adb(args, **kw))
    return SimpleNamespace(calls=calls, running=running, sessions=sessions, transport_calls=transport_calls)


def _open(platform):
    api = _api()
    return api.open_device(api.DeviceContext(platform, 'phone',
                           target='http://127.0.0.1:8100' if platform == 'ios' else 'phone',
                           adb_path='fake-adb', timeout_s=2))


@pytest.mark.parametrize('platform', ['android', 'ios'])
def test_launch_wait_stop(app_sdk, platform):
    api = _api()
    with _open(platform) as session:
        assert api.launch_app(session, 'com.example.demo').state == 'running'
        assert api.wait_for_app(session, 'com.example.demo', timeout_s=1).state == 'running'
        result = api.stop_app(session, 'com.example.demo')
        app_state_after_stop = result.state
        assert app_state_after_stop == 'not_running'
    assert app_sdk.sessions == set()
    if platform == 'ios':
        deletes = [call[1] for call in app_sdk.calls if call[0] == 'DELETE']
        assert deletes == ['/session/owned-0']
        assert all('borrowed' not in path for path in deletes)


def test_alert_accept_and_dismiss(app_sdk):
    api = _api()
    with _open('ios') as session:
        api.handle_mobile_alert(session, 'accept')
        api.handle_mobile_alert(session, 'dismiss')
    posts = [call[1] for call in app_sdk.calls if call[0] == 'POST']
    assert '/alert/accept' in posts
    assert '/alert/dismiss' in posts


def test_clipboard_file_recording_capabilities(app_sdk):
    with _open('android') as android, _open('ios') as ios:
        assert android.capabilities['install'].reason
        assert android.capabilities['files'].reason
        assert android.capabilities['clipboard'].reason
        unsupported_result = ios.capabilities['recording']
        assert unsupported_result.reason
        assert unsupported_result.state == 'needs_dependency'


def test_adapter_absent_reports_dependency(monkeypatch):
    monkeypatch.setitem(sys.modules, 'wda', None)
    api = _api()
    with _open('ios') as session:
        absent_adapter = session.capabilities['wda']
        assert absent_adapter.state == 'needs_dependency'
        assert session.capabilities['install'].state == 'needs_dependency'
    extension = importlib.import_module('je_auto_control.wrapper.mobile_extensions')
    assert extension.MobileExtension


def test_wait_deadline_and_cancel_do_not_leave_polling(app_sdk):
    api = _api()
    with _open('android') as session:
        with pytest.raises(api.DeviceSessionError, match='timed out'):
            api.wait_for_app(session, 'com.example.missing', timeout_s=.02)
        session.cancel()
        before = len(app_sdk.calls)
        with pytest.raises(api.DeviceSessionError, match='closed'):
            api.wait_for_app(session, 'com.example.missing', timeout_s=1)
        assert len(app_sdk.calls) == before


@pytest.mark.parametrize('identifier', ['com.demo;reboot', '', None, 'com.demo/Activity'])
def test_bad_app_id_rejected_before_device_calls(app_sdk, identifier):
    api = _api()
    with _open('android') as session:
        with pytest.raises(api.DeviceSessionError):
            api.launch_app(session, identifier)
    assert app_sdk.calls == []


def test_failed_owner_cleanup_remains_retryable(app_sdk, monkeypatch):
    api = _api()
    session = _open('ios')
    api.launch_app(session, 'com.example.demo')
    adapter = session.adapter('wda_app')
    original = adapter.close
    attempts = []

    def fail_once():
        attempts.append(1)
        if len(attempts) == 1:
            raise api.DeviceSessionError('temporary cleanup failure')
        original()

    monkeypatch.setattr(adapter, 'close', fail_once)
    with pytest.raises(api.DeviceSessionError):
        session.close()
    assert session.connected is False
    session.close()
    assert attempts == [1, 1]
    assert app_sdk.sessions == set()


def test_native_delete_failure_is_retried(app_sdk, monkeypatch):
    api = _api()
    session = _open('ios')
    api.launch_app(session, 'com.example.demo')
    wda = sys.modules['wda']
    original = wda._unsafe_httpdo
    attempts = []

    def fail_once(url, method='GET', data=None, timeout=None):
        if method == 'DELETE':
            attempts.append(url)
            if len(attempts) == 1:
                raise OSError('temporary transport failure')
        return original(url, method, data, timeout)

    monkeypatch.setattr(wda, '_unsafe_httpdo', fail_once)
    with pytest.raises(api.DeviceSessionError):
        session.close()
    assert app_sdk.sessions == {'owned-0'}
    session.close()
    assert app_sdk.sessions == set()
    assert len(attempts) == 2


def test_optional_extension_owned_and_passively_described(app_sdk):
    api = _api()
    from je_auto_control.wrapper.capabilities import CapabilityStatus
    events = []

    class Extension:
        name, version = 'test-adapter', '1.0'
        capabilities = {'clipboard': CapabilityStatus('available', 'test-adapter', 'configured', '', False)}

        def __init__(self, context, guard):
            self.context, self.guard = context, guard
            events.append('create')

        def clipboard(self, text=None):
            self.guard()
            events.append(text)
            return text

        def close(self):
            events.append('close')

    session = _open('ios')
    spec = api.MobileExtensionSpec('test-adapter', '1.0', Extension.capabilities, Extension)
    session.configure_extension(spec)
    assert session.capabilities['clipboard'].backend == 'test-adapter'
    assert events == []
    assert api.run_mobile_extension(session, 'clipboard', {'text': '測試 café 🙂'}) == '測試 café 🙂'
    session.close()
    assert events == ['create', '測試 café 🙂', 'close']
    with pytest.raises(api.DeviceSessionError, match='closed'):
        api.run_mobile_extension(session, 'clipboard', {})


def test_extension_rejects_foreign_owner(app_sdk):
    api = _api()
    from je_auto_control.wrapper.capabilities import CapabilityStatus
    other = _open('android')
    foreign = SimpleNamespace(context=other.context)
    session = _open('ios')
    spec = api.MobileExtensionSpec('test', '1',
        {'clipboard': CapabilityStatus('available', 'test', 'configured', '', False)},
        lambda context, guard: foreign)
    session.configure_extension(spec)
    with pytest.raises(api.DeviceSessionError, match='different device'):
        api.run_mobile_extension(session, 'clipboard', {})
    session.close()
    other.close()


def test_ios_extension_absent_never_runs_adb(app_sdk):
    api = _api()
    with _open('ios') as session:
        with pytest.raises(api.DeviceSessionError, match='needs_dependency'):
            api.run_mobile_extension(session, 'clipboard', {})
    assert app_sdk.calls == []


def test_wda_first_poll_uses_wait_budget(app_sdk):
    api = _api()
    app_sdk.running.add('com.example.demo')
    with _open('ios') as session:
        assert api.wait_for_app(session, 'com.example.demo', timeout_s=.25).state == 'running'
    creation = next(call for call in app_sdk.transport_calls if call[1] == '/session')
    assert 0 < creation[2] <= .25


def test_android_native_install_and_file_arguments(app_sdk, monkeypatch, tmp_path):
    api = _api()
    monkeypatch.setattr('je_auto_control.wrapper.device_context.shutil.which', lambda path: 'fake-adb')
    artifact = tmp_path / 'demo.apk'
    artifact.write_bytes(b'controlled-apk')
    calls = []

    def adb(self, args, **kwargs):
        calls.append((self._context.target, args))
        return subprocess.CompletedProcess(args, 0, b'Success\n', b'')

    monkeypatch.setattr('je_auto_control.wrapper._mobile_adb.OwnedAdbClient.run', adb)
    with _open('android') as session:
        api.run_mobile_extension(session, 'install', {'file_path': str(artifact)})
        api.run_mobile_extension(session, 'files', {'action': 'push', 'local_path': str(artifact),
                                                   'remote_path': '/sdcard/demo.apk'})
        before = len(calls)
        with pytest.raises(api.DeviceSessionError, match='metacharacters'):
            api.run_mobile_extension(session, 'files', {'action': 'push', 'local_path': str(artifact),
                                                       'remote_path': '/sdcard/a;reboot'})
        assert len(calls) == before
    assert calls == [('phone', ['install', '-r', str(artifact)]),
                     ('phone', ['push', str(artifact), '/sdcard/demo.apk'])]


def test_extension_action_masks_text_in_logs_and_journal():
    from je_auto_control.utils.executor.action_redaction import redact_actions
    from je_auto_control.utils.action_journal.privacy import private_input, private_output
    text = '測試 café 🙂'
    named = {'operation': 'clipboard', 'options': {'text': text}}
    positional = ['clipboard', {'text': text}]
    for arguments in (named, positional):
        assert text not in str(redact_actions(['AC_mobile_extension', arguments]))
        sanitized, reasons = private_input('AC_mobile_extension', arguments)
        assert text not in str(sanitized)
        assert reasons
        output, _ = private_output('AC_mobile_extension', sanitized, text)
        assert output == '***'


def test_app_action_surface_dispatch_and_guard(app_sdk):
    api = _api()
    import je_auto_control as ac
    from je_auto_control.utils.executor.action_executor import executor
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    from je_auto_control.gui.script_builder.command_schema import COMMAND_SPECS
    with _open('android') as session, session.bind():
        assert api.mobile_app('launch', 'com.example.demo')['state'] == 'running'
        assert api.mobile_app('stop', 'com.example.demo')['state'] == 'not_running'
    for name in ('mobile_app', 'mobile_alert', 'mobile_extension'):
        assert 'AC_' + name in executor.known_commands()
        assert 'ac_' + name in {tool.name for tool in build_default_tool_registry()}
        assert 'AC_' + name in COMMAND_SPECS
    assert ac.mobile_app is api.mobile_app


def test_late_wda_constructor_cleanup_failure_retained(app_sdk, monkeypatch):
    api = _api()
    session = _open('ios')
    wda = sys.modules['wda']
    original = wda._unsafe_httpdo
    deletes = []

    def transport(url, method='GET', data=None, timeout=None):
        response = original(url, method, data, timeout)
        if method == 'POST' and url.endswith('/session'):
            session.cancel()
        if method == 'DELETE':
            deletes.append(url)
            if len(deletes) == 1:
                app_sdk.sessions.add('owned-0')
                raise OSError('cleanup unavailable')
        return response

    monkeypatch.setattr(wda, '_unsafe_httpdo', transport)
    with pytest.raises(api.DeviceSessionError):
        api.launch_app(session, 'com.example.demo')
    assert session.connected is False
    session.close()
    assert app_sdk.sessions == set()
    assert len(deletes) == 2
    assert not any(call[1].endswith('/launch') for call in app_sdk.calls)


def test_recording_adapter_is_bounded_and_closed(app_sdk, tmp_path):
    api = _api()
    from je_auto_control.wrapper.capabilities import CapabilityStatus
    calls = []

    class Extension:
        def __init__(self, context, guard):
            self.context, self.guard = context, guard

        def recording(self, file_path, duration_s):
            self.guard()
            calls.append((file_path, duration_s))
            Path(file_path).write_bytes(b'controlled-recording')

        def close(self):
            calls.append('closed')

    target = tmp_path / 'clip.mp4'
    with _open('ios') as session:
        session.configure_extension(api.MobileExtensionSpec('controlled', '1',
            {'recording': CapabilityStatus('available', 'controlled', 'configured', '', False)}, Extension))
        api.run_mobile_extension(session, 'recording', {'file_path': str(target), 'duration_s': 1})
        assert session.capabilities['files'].state == 'unsupported'
    assert target.read_bytes() == b'controlled-recording'
    assert calls == [(str(target), 1), 'closed']


def test_wda_failed_input_is_not_automatically_replayed(app_sdk, monkeypatch):
    api = _api()
    session = _open('ios')
    original = sys.modules['wda']._unsafe_httpdo
    attempts = []

    def http(url, method='GET', data=None, timeout=None):
        if url.endswith('/launch'):
            attempts.append(url)
            raise OSError('reply lost after send')
        return original(url, method, data, timeout)

    monkeypatch.setattr(sys.modules['wda'], '_unsafe_httpdo', http)
    with pytest.raises(api.DeviceSessionError, match='unknown'):
        api.launch_app(session, 'com.example.demo')
    assert len(attempts) == 1
    session.close()
    assert app_sdk.sessions == set()


@pytest.mark.parametrize('code,stdout,stderr', [(0, b'', b''), (1, b'123', b''),
                                                (1, b'', b'device unauthorized')])
def test_android_inconsistent_state_is_not_reported_stopped(app_sdk, monkeypatch, code, stdout, stderr):
    api = _api()
    monkeypatch.setattr('je_auto_control.wrapper._mobile_adb.OwnedAdbClient.run',
        lambda self, args, **kw: subprocess.CompletedProcess(args, code, stdout, stderr))
    with _open('android') as session:
        with pytest.raises(api.DeviceSessionError):
            api.app_state(session, 'com.example.demo')


def test_android_sdk_clipboard_preserves_unicode(app_sdk, monkeypatch):
    api = _api()
    monkeypatch.setattr('je_auto_control.wrapper.device_context._sdk_present', lambda name: True)
    values = []

    class Clipboard:
        clipboard = ''

        def set_clipboard(self, text):
            self.clipboard = text
            values.append(text)

    with _open('android') as session:
        session._adapters['uiautomator2'] = SimpleNamespace(handle=Clipboard(), close=lambda: None)
        assert api.run_mobile_extension(session, 'clipboard', {'text': '測試 café 🙂'}) is None
        assert api.run_mobile_extension(session, 'clipboard', {}) == '測試 café 🙂'
    assert values == ['測試 café 🙂']


def test_busy_wda_endpoint_never_creates_or_deletes_foreign_session(app_sdk):
    api = _api()
    app_sdk.sessions.add('borrowed')
    with _open('ios') as session:
        with pytest.raises(api.DeviceSessionError, match='dedicated idle'):
            api.launch_app(session, 'com.example.demo')
    assert app_sdk.sessions == {'borrowed'}
    assert [(method, path) for method, path, _ in app_sdk.transport_calls] == [('GET', '/status')]


def test_unknown_wda_ownership_never_creates_session(app_sdk, monkeypatch):
    api = _api()
    original = sys.modules['wda']._unsafe_httpdo

    def http(url, method='GET', data=None, timeout=None):
        if url.endswith('/status'):
            return SimpleNamespace(value={'ready': True})
        return original(url, method, data, timeout)

    monkeypatch.setattr(sys.modules['wda'], '_unsafe_httpdo', http)
    with _open('ios') as session:
        with pytest.raises(api.DeviceSessionError, match='ownership metadata'):
            api.app_state(session, 'com.example.demo')
    assert app_sdk.transport_calls == []


def test_same_endpoint_pending_creation_cannot_be_superseded(app_sdk, monkeypatch):
    api = _api()
    left, right = _open('ios'), _open('ios')
    original = sys.modules['wda']._unsafe_httpdo
    attempts = []

    def http(url, method='GET', data=None, timeout=None):
        if url.endswith('/status') and not attempts:
            attempts.append(1)
            with pytest.raises(api.DeviceSessionError, match='owned by another'):
                api.launch_app(right, 'com.example.other')
        return original(url, method, data, timeout)

    monkeypatch.setattr(sys.modules['wda'], '_unsafe_httpdo', http)
    api.launch_app(left, 'com.example.demo')
    left.close()
    assert api.launch_app(right, 'com.example.other').state == 'running'
    right.close()
    assert app_sdk.sessions == set()
