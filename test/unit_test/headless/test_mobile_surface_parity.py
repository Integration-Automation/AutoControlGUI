"""Every mobile capability is reachable without desktop fallback or input probes."""
import importlib
import subprocess
import sys
from types import ModuleType, SimpleNamespace

import pytest


def _api():
    return importlib.import_module('je_auto_control.api.mobile')


@pytest.fixture
def setup_sdk(monkeypatch):
    calls = []
    sdk = ModuleType('wda')

    def http(url, method='GET', data=None, timeout=None):
        calls.append((url, method, data, timeout))
        return SimpleNamespace(sessionId=None, value={'ready': True, 'build': {'version': 'controlled-2.0'}})

    sdk._unsafe_httpdo = http
    monkeypatch.setitem(sys.modules, 'wda', sdk)
    monkeypatch.setattr('importlib.metadata.version', lambda name: 'controlled-1.0')
    return calls


def test_every_mobile_capability_has_api_command_gui_schema(setup_sdk):
    api = _api()
    import je_auto_control as ac
    from je_auto_control.utils.executor.action_executor import executor
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    from je_auto_control.gui.script_builder.command_schema import COMMAND_SPECS
    matrix = api.mobile_surface_matrix()
    commands = set(executor.known_commands())
    tools = {tool.name for tool in build_default_tool_registry()}
    missing_surface_commands = set()
    for row in matrix['operations']:
        if not (callable(getattr(api, row['api'], None)) and callable(getattr(ac, row['api'], None))
                and row['command'] in commands and row['command'] in COMMAND_SPECS
                and row['mcp'] in tools and row['gui_action']):
            missing_surface_commands.add(row['operation'])
    assert missing_surface_commands == set()
    operations = {row['operation'] for row in matrix['operations']}
    with api.open_device(api.DeviceContext('ios', 'phone', target='http://wda.example:8100')) as session:
        assert set(session.capabilities) - {'wda'} == operations
    assert all(row['state'] == 'unsupported' and row['alternative'] for row in matrix['desktop_limits'])
    assert setup_sdk == []


def test_matrix_inventories_every_executor_command_and_catalog_enums():
    from je_auto_control.utils.executor.action_executor import executor
    from je_auto_control.gui.script_builder.command_schema import COMMAND_SPECS
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    matrix = _api().mobile_surface_matrix()
    assert {row['command'] for row in matrix['executor_commands']} == set(executor.known_commands())
    assert all(row['reason'] and row['alternative'] for row in matrix['executor_commands'])
    operations = {row['operation'] for row in matrix['operations']}
    tools = {tool.name: tool for tool in build_default_tool_registry()}
    for name in ('AC_android_mobile_action', 'AC_ios_mobile_action'):
        field = next(field for field in COMMAND_SPECS[name].fields if field.name == 'operation')
        assert set(field.choices) == operations
        assert set(tools['ac_' + name[3:]].input_schema['properties']['operation']['enum']) == operations


def test_private_mobile_results_are_masked_in_plain_logs_but_returned_to_caller(monkeypatch):
    from je_auto_control.utils.executor import action_executor as module
    runner = module.Executor()
    runner.event_dict['AC_mobile_extension'] = lambda operation, options: 'controlled-clipboard-secret'
    logged = []
    monkeypatch.setattr(module.autocontrol_logger, 'info', lambda fmt, *args: logged.append(str(args)))
    monkeypatch.delenv('JE_AUTOCONTROL_JOURNAL', raising=False)
    result = runner.execute_action([['AC_mobile_extension', {'operation': 'clipboard', 'options': {}}]])
    assert list(result.values()) == ['controlled-clipboard-secret']
    assert 'controlled-clipboard-secret' not in ''.join(logged)


def test_valid_mobile_batch_keeps_owner_and_input_immutable(monkeypatch):
    api = _api()
    from je_auto_control.wrapper._mobile_binding import active_device
    calls = []
    def dispatch(self, action):
        calls.append(active_device())
        action[1]['connect'] = 'changed'
        return 'controlled'
    monkeypatch.setattr('je_auto_control.utils.executor.action_executor.Executor._execute_event', dispatch)
    actions = [['AC_mobile_setup', {'connect': False}]]
    with api.open_device(api.DeviceContext('android', 'phone', adb_path='fake-adb')) as session:
        assert api.run_mobile_actions(session, actions) == ['controlled']
        assert calls == [session]
    assert actions == [['AC_mobile_setup', {'connect': False}]]


def test_wda_remote_endpoint_setup(setup_sdk):
    api = _api()
    context = api.DeviceContext('ios', 'remote-phone', target='http://wda.example:8100', timeout_s=2)
    with api.open_device(context) as session:
        passive = api.inspect_device_setup(session)
        assert passive.backend_version
        assert setup_sdk == []
        device_setup_report = api.inspect_device_setup(session, connect=True)
        assert device_setup_report.backend_version == 'controlled-2.0'
        assert device_setup_report.authorization.state == 'available'
        assert device_setup_report.endpoint_idle is True
    assert setup_sdk == [('http://wda.example:8100/status', 'GET', None, 2)]


def test_android_authorization_error(monkeypatch):
    api = _api()
    unauthorized_input_calls = []
    calls = []

    def run(self, args, **kwargs):
        calls.append(args)
        if args != ['get-state']:
            unauthorized_input_calls.append(args)
        return subprocess.CompletedProcess(args, 1, b'', b'device unauthorized')

    monkeypatch.setattr('je_auto_control.wrapper._mobile_adb.OwnedAdbClient.run', run)
    with api.open_device(api.DeviceContext('android', 'phone', adb_path='fake-adb')) as session:
        with pytest.raises(api.DeviceSessionError, match='authorization'):
            api.inspect_device_setup(session, connect=True)
    assert unauthorized_input_calls == []
    assert calls == [['get-state']]


def test_platform_alias_rejects_mismatched_device_before_native_io(setup_sdk):
    api = _api()
    with pytest.raises(api.DeviceSessionError, match='platform'):
        api.android_mobile_action('app_state', {'app_id': 'com.example.demo'},
                                 {'platform': 'ios', 'url': 'http://wda.example:8100'})
    assert setup_sdk == []


def test_platform_alias_dispatches_same_setup_service_and_rejects_invalid_options(setup_sdk):
    api = _api()
    device = {'platform': 'ios', 'url': 'http://wda.example:8100'}
    result = api.ios_mobile_action('device_setup', {'connect': True}, device)
    assert result['verified_connection'] is True
    assert len(setup_sdk) == 1
    with pytest.raises(api.DeviceSessionError, match='schema'):
        api.ios_mobile_action('device_setup', {'unknown': True}, device)
    assert len(setup_sdk) == 1


def test_mobile_action_batch_rejects_desktop_commands_before_any_input(monkeypatch):
    api = _api()
    called = []
    monkeypatch.setattr('je_auto_control.utils.executor.action_executor.Executor._execute_event',
                        lambda self, action: called.append(action))
    with api.open_device(api.DeviceContext('android', 'phone', adb_path='fake-adb')) as session:
        with pytest.raises(api.DeviceSessionError, match='mobile'):
            api.run_mobile_actions(session, [['AC_mobile_type_text', {'text': 'safe'}],
                                             ['AC_click_mouse', {'x': 1, 'y': 1}]])
    assert called == []


def test_invalid_second_mobile_signature_rejects_whole_batch_before_input(monkeypatch):
    api = _api()
    called = []
    monkeypatch.setattr('je_auto_control.utils.executor.action_executor.Executor._execute_event',
                        lambda self, action: called.append(action))
    with api.open_device(api.DeviceContext('android', 'phone', adb_path='fake-adb')) as session:
        with pytest.raises(api.DeviceSessionError, match='schema'):
            api.run_mobile_actions(session, [['AC_mobile_type_text', {'text': 'first'}],
                                             ['AC_mobile_setup', {'unknown': True}]])
    assert called == []


def test_revocation_does_not_wait_for_native_cleanup(monkeypatch):
    api = _api()
    session = api.open_device(api.DeviceContext('android', 'phone', adb_path='fake-adb'))
    calls = []
    session._adapters['uiautomator2'] = SimpleNamespace(close=lambda: calls.append('cleanup'))
    session.revoke()
    assert session.connected is False
    assert calls == []
    session.close()
    assert calls == ['cleanup']


def test_panel_owner_revokes_immediately_and_retries_cleanup():
    from threading import Event
    owner = importlib.import_module('je_auto_control.wrapper._mobile_panel_owner').MobilePanelOwner()
    owner.open({'platform': 'android', 'serial': 'phone', 'adb_path': 'fake-adb'})
    session = owner.session
    entered, release = Event(), Event()
    attempts = []

    def close():
        entered.set()
        release.wait(2)
        attempts.append(1)
        if len(attempts) == 1:
            raise _api().DeviceSessionError('controlled cleanup failure')

    session._adapters['uiautomator2'] = SimpleNamespace(close=close)
    owner.request_close()
    assert session.connected is False
    assert entered.wait(1)
    assert owner.snapshot()['cleanup_running'] is True
    with pytest.raises(_api().DeviceSessionError):
        owner.open({'platform': 'android', 'serial': 'other', 'adb_path': 'fake-adb'})
    release.set()
    assert owner.wait_cleanup(2)
    assert owner.snapshot()['cleanup_error']
    owner.request_close()
    assert owner.wait_cleanup(2)
    assert attempts == [1, 1]
    assert owner.snapshot()['device'] is None


def test_mobile_panel_menu_and_operation_catalog_in_child_process():
    pytest.importorskip('PySide6.QtWidgets', exc_type=ImportError)
    import os
    probe = r"""
import json
from PySide6.QtWidgets import QApplication
from je_auto_control.gui.mobile_tab import MobileTab
from je_auto_control.wrapper.mobile_surfaces import mobile_surface_matrix
app = QApplication([])
tab = MobileTab()
assert tab._owner.snapshot()['device'] is None
assert {tab._operation.itemData(i) for i in range(tab._operation.count())} == {
    row['operation'] for row in mobile_surface_matrix()['operations']}
actions = dict(tab.menu_actions())
assert 'mobile_run_operation' in actions and all(callable(fn) for fn in actions.values())
tab._target.setText('controlled-phone')
tab._adb_path.setText('fake-adb')
tab._on_open()
assert tab._owner.session.context.target == 'controlled-phone'
tab._job_generation = tab._owner.snapshot()['generation']
tab._on_close_owner()
closing = tab._output.toPlainText()
tab._done({'stale': True})
tab._worker_failed('stale error')
assert tab._output.toPlainText() == closing
tab.close()
assert tab._owner.wait_cleanup(2)
app.processEvents()
print(json.dumps({'actions': len(actions)}))
"""
    env = dict(os.environ, QT_QPA_PLATFORM='offscreen')
    result = subprocess.run([sys.executable, '-c', probe], capture_output=True, text=True, env=env, timeout=30)
    assert result.returncode == 0, result.stderr
