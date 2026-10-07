"""Explicit mobile ownership must never mutate or fall back to device defaults."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError
import importlib
import subprocess
import sys
from threading import Barrier, Event
from types import ModuleType, SimpleNamespace

import pytest


def _api():
    return importlib.import_module('je_auto_control.wrapper.device_context')


@pytest.fixture
def sdk(monkeypatch):
    calls = []

    class Android:
        def __init__(self, serial):
            self.serial = serial

        def dump_hierarchy(self):
            return self.jsonrpc_call('dump', None, 60)

        def jsonrpc_call(self, method, params=None, timeout=60):
            calls.append(('android', self.serial, method, timeout))
            return self.serial

    class IOS:
        def __init__(self, url):
            self.url = url

        def tap(self, x, y):
            return self._fetch('POST', 'tap', {'x': x, 'y': y})

        def _fetch(self, method, urlpath, data=None, with_session=False, timeout=None):
            calls.append(('ios', self.url, urlpath, timeout))
            return self.url

    for name, attributes in (
        ('uiautomator2', {'Device': Android, 'connect': Android}),
        ('wda', {'Client': IOS}),
    ):
        module = ModuleType(name)
        module.__dict__.update(attributes)
        monkeypatch.setitem(sys.modules, name, module)
    return SimpleNamespace(calls=calls, android=Android, ios=IOS)


def test_parallel_devices_do_not_change_default(sdk, monkeypatch):
    api = _api()
    from je_auto_control.android import client, find
    original = object()
    monkeypatch.setattr(client, '_DEFAULT_DEVICE', original)
    sessions = [api.open_device(api.DeviceContext('android', name, timeout_s=2)) for name in ('left', 'right')]
    ready = Barrier(2)

    def read(session):
        with session.bind():
            ready.wait(5)
            return find.dump_hierarchy()

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            values = list(pool.map(read, sessions))
        assert values == ['left', 'right']
        assert client._DEFAULT_DEVICE is original
        assert {call[1] for call in sdk.calls} == {'left', 'right'}
    finally:
        for session in sessions:
            session.close()


def test_session_cancel_only_target(sdk):
    api = _api()
    from je_auto_control.android.client import default_ui_device
    left = api.open_device(api.DeviceContext('android', 'left'))
    right = api.open_device(api.DeviceContext('android', 'right'))
    try:
        with left.bind():
            left.cancel()
            with pytest.raises(api.DeviceSessionError, match='closed|cancel'):
                default_ui_device()
        assert right.connected is True
        with right.bind():
            assert default_ui_device().handle.dump_hierarchy() == 'right'
        assert [call[1] for call in sdk.calls] == ['right']
    finally:
        left.close()
        right.close()


def test_device_capability_probe_has_no_input(sdk, monkeypatch):
    api = _api()
    probe_input_calls = []

    def forbidden(*args, **kwargs):
        probe_input_calls.append((args, kwargs))
        raise AssertionError('a passive probe attempted device I/O')

    monkeypatch.setattr(subprocess, 'run', forbidden)
    monkeypatch.setattr(sdk.android, '__init__', forbidden)
    monkeypatch.setattr(sdk.ios, '__init__', forbidden)
    results = api.probe_device_contexts([
        {'platform': 'android', 'serial': 'left'},
        {'platform': 'ios', 'url': 'http://127.0.0.1:8100'},
    ])
    assert len(results) == 2
    assert all(result['capabilities'] for result in results)
    assert probe_input_calls == []
    assert sdk.calls == []


def test_identity_is_frozen_and_timeout_is_finite():
    api = _api()
    context = api.DeviceContext('android', 'left')
    with pytest.raises(FrozenInstanceError):
        context.device_id = 'right'
    for timeout in (0, -1, float('nan'), float('inf'), True):
        with pytest.raises(api.DeviceSessionError):
            api.DeviceContext('android', 'left', timeout_s=timeout)


def test_matrix_implicit_ios_input_targets_each_endpoint(sdk):
    from je_auto_control.utils.device_matrix import run_on_devices
    devices = [{'platform': 'ios', 'url': f'http://127.0.0.1:{port}'} for port in (8101, 8102)]
    report = run_on_devices([['AC_ios_tap', {'x': 1, 'y': 2}]], devices)
    assert report.passed == 2
    assert {call[1] for call in sdk.calls} == {device['url'] for device in devices}


def test_wda_request_timeouts_are_per_context(sdk):
    api = _api()
    from je_auto_control.ios.input import tap
    for port, timeout in ((8101, 2), (8102, 3)):
        with api.open_device(api.DeviceContext('ios', str(port), target=f'http://127.0.0.1:{port}',
                                              timeout_s=timeout)) as session:
            with session.bind():
                tap(1, 2)
    assert [call[3] for call in sdk.calls] == [2, 3]


def test_cancel_does_not_wait_for_pending_sdk_connection(sdk, monkeypatch):
    api = _api()
    from je_auto_control.android.client import default_ui_device
    entered, finish = Event(), Event()
    original = sdk.android.__init__

    def connect(handle, serial):
        entered.set()
        assert finish.wait(5)
        original(handle, serial)

    monkeypatch.setattr(sdk.android, '__init__', connect)
    session = api.open_device(api.DeviceContext('android', 'left'))

    def pending():
        with session.bind():
            return default_ui_device().handle

    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(pending)
            assert entered.wait(5)
            session.cancel()
            assert not session.connected
            finish.set()
            with pytest.raises(api.DeviceSessionError):
                future.result(5)
    finally:
        finish.set()
        session.close()


def test_retained_sdk_calls_cannot_operate_after_cancel(sdk, monkeypatch):
    api = _api()

    def install(handle, path):
        sdk.calls.append(('install', handle.serial, path))

    monkeypatch.setattr(sdk.android, 'app_install', install, raising=False)
    with api.open_device(api.DeviceContext('android', 'left')) as session:
        handle = session.adapter('uiautomator2').handle
        retained_install = handle.app_install
        session.cancel()
        with pytest.raises(api.DeviceSessionError):
            retained_install('app.apk')
        with pytest.raises(api.DeviceSessionError):
            handle.serial
    assert sdk.calls == []


def test_duplicate_matrix_targets_rejected_before_any_input(sdk):
    api = _api()
    from je_auto_control.utils.device_matrix import run_on_devices
    devices = [{'platform': 'ios', 'url': 'http://127.0.0.1:8100', 'device_id': name}
               for name in ('left', 'right')]
    with pytest.raises(api.DeviceSessionError, match='duplicate'):
        run_on_devices([['AC_ios_tap', {'x': 1, 'y': 2}]], devices)
    assert sdk.calls == []


@pytest.mark.parametrize('devices', ['android', [None], [{'platform': 'other'}]])
def test_passive_probe_rejects_malformed_specs(devices):
    api = _api()
    with pytest.raises(api.DeviceSessionError):
        api.probe_device_contexts(devices)


@pytest.mark.parametrize('owned', [True, False])
def test_close_reclaims_only_owned_android_helper_once(sdk, monkeypatch, owned):
    import atexit
    api = _api()
    stops, unregister = [], []
    original = sdk.android.__init__

    def connect(handle, serial):
        original(handle, serial)
        handle._cleanup_serial = serial
        handle._process = object() if owned else None

    def stop(handle, wait=True):
        stops.append((handle._cleanup_serial, wait))
        handle._process = None

    monkeypatch.setattr(sdk.android, '__init__', connect)
    monkeypatch.setattr(sdk.android, 'stop_uiautomator', stop, raising=False)
    monkeypatch.setattr(atexit, 'unregister', unregister.append)
    session = api.open_device(api.DeviceContext('android', 'left'))
    session.adapter('uiautomator2').handle
    session.close()
    session.close()
    assert stops == [('left', False)] if owned else stops == []
    assert unregister


def test_failed_android_bootstrap_reclaims_partial_helper(sdk, monkeypatch):
    api = _api()
    from je_auto_control.android.client import UIAutomatorUnavailableError
    stops = []

    def fail(handle, serial):
        handle._process = object()
        raise OSError('failed bootstrap')

    def stop(handle, wait=True):
        stops.append(wait)

    monkeypatch.setattr(sdk.android, '__init__', fail)
    monkeypatch.setattr(sdk.android, 'stop_uiautomator', stop, raising=False)
    with api.open_device(api.DeviceContext('android', 'left')) as session:
        with pytest.raises(UIAutomatorUnavailableError):
            session.adapter('uiautomator2').handle
    assert stops == [False]


def test_cancelled_late_constructor_reclaims_registered_helper(sdk, monkeypatch):
    import atexit
    api = _api()
    entered, finish = Event(), Event()
    callbacks, removed, stops = [], [], []

    def connect(handle, serial):
        handle._process = object()
        callbacks.append(handle.stop_uiautomator)
        entered.set()
        assert finish.wait(5)

    def stop(handle, wait=True):
        stops.append(wait)
        handle._process = None

    monkeypatch.setattr(sdk.android, '__init__', connect)
    monkeypatch.setattr(sdk.android, 'stop_uiautomator', stop, raising=False)
    monkeypatch.setattr(atexit, 'unregister', removed.append)
    session = api.open_device(api.DeviceContext('android', 'left'))
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(lambda: session.adapter('uiautomator2').handle)
            assert entered.wait(5)
            session.cancel()
            finish.set()
            with pytest.raises(api.DeviceSessionError):
                future.result(5)
        assert stops == [False]
        assert callbacks[0] in removed
    finally:
        finish.set()
        session.close()


def test_close_does_not_delete_borrowed_wda_session(sdk, monkeypatch):
    api = _api()

    def delete(handle):
        sdk.calls.append('delete-session')

    monkeypatch.setattr(sdk.ios, 'close', delete, raising=False)
    with api.open_device(api.DeviceContext('ios', 'phone', target='http://127.0.0.1:8100')) as session:
        session.adapter('wda').handle
    assert sdk.calls == []


def test_nested_context_reset_and_explicit_target_mismatch(sdk):
    api = _api()
    from je_auto_control.android.client import default_ui_device
    from je_auto_control.utils.executor.action_executor import _android_ui_device
    with api.open_device(api.DeviceContext('android', 'left')) as left:
        with api.open_device(api.DeviceContext('android', 'right')) as right:
            with left.bind():
                with right.bind():
                    assert default_ui_device().handle.dump_hierarchy() == 'right'
                assert default_ui_device().handle.dump_hierarchy() == 'left'
                with pytest.raises(api.DeviceSessionError, match='match'):
                    _android_ui_device('right')
    assert [call[1] for call in sdk.calls] == ['right', 'left']
    assert api.bound_device('android') is None


def test_pending_wda_reply_is_rejected_after_cancel(sdk, monkeypatch):
    api = _api()
    entered, finish = Event(), Event()

    def fetch(handle, *args, **kwargs):
        entered.set()
        assert finish.wait(5)
        sdk.calls.append('reply')
        return 'late reply'

    monkeypatch.setattr(sdk.ios, '_fetch', fetch)
    session = api.open_device(api.DeviceContext('ios', 'phone', target='http://127.0.0.1:8100'))
    handle = session.adapter('wda').handle
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(handle.tap, 1, 2)
            assert entered.wait(5)
            session.cancel()
            finish.set()
            with pytest.raises(api.DeviceSessionError):
                future.result(5)
        assert sdk.calls == ['reply']
    finally:
        finish.set()
        session.close()


def test_owned_sdk_error_remains_framework_contained(sdk, monkeypatch):
    api = _api()
    class SDKError(Exception):
        pass

    def fail(handle, x, y):
        raise SDKError('network failure')

    monkeypatch.setattr(sdk.ios, 'tap', fail)
    with api.open_device(api.DeviceContext('ios', 'phone', target='http://127.0.0.1:8100')) as session:
        with pytest.raises(api.DeviceSessionError) as failure:
            session.adapter('wda').handle.tap(1, 2)
        assert isinstance(failure.value.__cause__, SDKError)


def test_passive_probe_has_matching_public_surfaces(sdk):
    import je_auto_control as ac
    from je_auto_control.api import mobile
    from je_auto_control.utils.executor.action_executor import executor
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    from je_auto_control.gui.script_builder.command_schema import COMMAND_SPECS
    for name in mobile.__all__:
        assert getattr(ac, name) is getattr(mobile, name)
    devices = [{'platform': 'android', 'serial': 'left'}]
    expected = ac.probe_device_contexts(devices)
    assert executor.event_dict['AC_probe_mobile_devices'](devices) == expected
    tools = {tool.name: tool for tool in build_default_tool_registry()}
    assert tools['ac_probe_mobile_devices'].handler(devices) == expected
    assert tools['ac_probe_mobile_devices'].annotations.read_only
    assert 'AC_probe_mobile_devices' in COMMAND_SPECS
    assert sdk.calls == []


def test_bound_python_helper_rejects_foreign_explicit_client(sdk):
    api = _api()
    from je_auto_control.ios.client import IOSDevice
    from je_auto_control.ios.input import tap
    foreign = IOSDevice(handle=sdk.ios('http://127.0.0.1:8102'))
    with api.open_device(api.DeviceContext('ios', 'left', target='http://127.0.0.1:8101')) as session:
        with session.bind():
            with pytest.raises(api.DeviceSessionError):
                tap(1, 2, device=foreign)
    assert sdk.calls == []


def test_matrix_implicit_adb_uses_owned_serial_and_timeout(monkeypatch):
    from je_auto_control.utils.device_matrix import run_on_devices
    from je_auto_control.utils.executor import action_executor as module
    calls, cache = [], dict(module._android_client_cache)

    def run(argv, **kwargs):
        calls.append((argv, kwargs['timeout']))
        return subprocess.CompletedProcess(argv, 0, stdout=b'', stderr=b'')

    monkeypatch.setattr(subprocess, 'run', run)
    devices = [{'platform': 'android', 'serial': name, 'adb_path': 'fake-adb', 'timeout_s': timeout}
               for name, timeout in (('left', 2), ('right', 3))]
    report = run_on_devices([['AC_android_tap', {'x': 1, 'y': 2}]], devices)
    assert report.passed == 2
    assert {(argv[2], timeout) for argv, timeout in calls} == {('left', 2), ('right', 3)}
    assert all(argv[:2] == ['fake-adb', '-s'] for argv, _ in calls)
    assert module._android_client_cache == cache
