"""Safe regressions for the whole-A review; no device or desktop mutations."""
import json
import sys
import threading
from types import SimpleNamespace

import pytest

from je_auto_control.utils.rbac.authorization import (
    AuthorizationContext, authorization_scope, required_capability,
)
from je_auto_control.utils.rbac.users import Capability


@pytest.mark.parametrize('name', [
    'ac_launch_process', 'AC_terminate_process', 'ac_run_device_matrix',
    'AC_run_suite', 'AC_run_resumable', 'ac_read_document',
    'ac_unclassified_review_command',
])
def test_unreviewed_or_host_operations_fail_closed(name):
    assert required_capability(name, read_only=True) == Capability.MANAGE_HOSTS


def test_audit_tool_alias_uses_audit_capability():
    assert required_capability('ac_list_run_history', read_only=True) == Capability.READ_AUDIT


def test_screenshot_saving_requires_host_capability():
    assert required_capability('ac_screenshot', arguments={'file_path': 'output.png'}) == Capability.MANAGE_HOSTS
    assert required_capability('ac_screenshot', arguments={}) == Capability.READ_SCREEN


@pytest.fixture
def bridge(tmp_path, monkeypatch):
    from je_auto_control.utils.mcp_server.server import MCPServer
    from je_auto_control.utils.mcp_server.audit import AuditLogger
    from je_auto_control.utils.mcp_server import _tool_calls
    monkeypatch.setattr(_tool_calls, '_capture_error_screenshot', lambda ctx: None)
    return MCPServer(audit_logger=AuditLogger(str(tmp_path / 'audit.jsonl')))


def test_remote_adapter_variables_do_not_cross_callers(bridge):
    for user, action in [('first', ['AC_set_var', {'name': 'review_marker', 'value': 'caller-one'}]),
                         ('second', ['AC_get_var', {'name': 'review_marker'}])]:
        with bridge.connection_scope(authorization=AuthorizationContext(user, 'admin')):
            result = bridge._handle_tools_call(1, {'name': 'ac_circuit_call', 'arguments': {
                'name': user + '-review-isolation', 'actions': [action]}})
    assert 'caller-one' not in json.dumps(result)


def test_device_worker_inherits_authorization(monkeypatch):
    from je_auto_control.utils.device_matrix import run_on_devices
    from je_auto_control.utils.executor.action_executor import Executor
    original = Executor.__init__
    calls = []

    def initialize(self):
        original(self)
        self.event_dict['AC_shell'] = lambda command: calls.append(command)

    monkeypatch.setattr(Executor, '__init__', initialize)
    with authorization_scope(AuthorizationContext('operator', 'operator')):
        report = run_on_devices([['AC_shell', {'command': 'not-executed'}]],
                                [{'serial': 'fake', 'platform': 'fake'}])
    assert report.failed == 1
    assert calls == []


@pytest.mark.parametrize('positional', [False, True])
def test_nested_executor_enforces_root_after_interpolation(tmp_path, monkeypatch, positional):
    from je_auto_control.utils.executor.action_executor import Executor
    from je_auto_control.utils.path_guard.policy import PathPolicy, path_policy_scope
    from je_auto_control.utils.path_guard.path_guard import PathNotAllowedError
    from je_auto_control.utils.script_vars.scope import execution_scope
    allowed = tmp_path / 'allowed'
    allowed.mkdir()
    calls = []
    executor = Executor()
    executor.event_dict['AC_load_data'] = lambda source: calls.append(source)
    source = {'kind': 'json', 'path': '${outside}'}
    args = [source] if positional else {'source': source}
    with path_policy_scope(PathPolicy([allowed])), execution_scope({'outside': str(tmp_path / 'outside.json')}):
        with pytest.raises(PathNotAllowedError):
            executor.execute_action([['AC_loop', {'times': 1, 'body': [['AC_load_data', args]]}]],
                                    raise_on_error=True)
    assert calls == []


def test_nested_root_validation_normalizes_allowed_paths(tmp_path):
    from je_auto_control.utils.executor.action_executor import Executor
    from je_auto_control.utils.path_guard.policy import PathPolicy, path_policy_scope
    calls = []
    executor = Executor()
    executor.event_dict['AC_load_data'] = lambda source: calls.append(source)
    with path_policy_scope(PathPolicy([tmp_path])):
        executor.execute_action([['AC_load_data', {'source': {'kind': 'json', 'path': 'data.json'}}]],
                                raise_on_error=True)
    assert calls[0]['path'] == str(tmp_path / 'data.json')


def test_signing_default_key_file_obeys_request_roots(tmp_path, monkeypatch):
    from je_auto_control.utils.action_signing.signer import _key_material
    from je_auto_control.utils.path_guard.policy import PathPolicy, path_policy_scope
    from je_auto_control.utils.path_guard.path_guard import PathNotAllowedError
    allowed = tmp_path / 'allowed'
    allowed.mkdir()
    key = tmp_path / 'outside.pem'
    key.write_bytes(b'not-a-real-key')
    monkeypatch.setenv('REVIEW_KEY_FILE', str(key))
    with path_policy_scope(PathPolicy([allowed])), pytest.raises(PathNotAllowedError):
        _key_material(None, None, 'REVIEW_KEY_FILE', 'public')


def test_nested_pathlike_argument_cannot_escape(tmp_path):
    from je_auto_control.utils.executor.action_executor import Executor
    from je_auto_control.utils.path_guard.policy import PathPolicy, path_policy_scope
    from je_auto_control.utils.path_guard.path_guard import PathNotAllowedError
    executor = Executor()
    executor.event_dict['AC_load_data'] = lambda source: None
    allowed = tmp_path / 'allowed'
    allowed.mkdir()
    with path_policy_scope(PathPolicy([allowed])), pytest.raises(PathNotAllowedError):
        executor._execute_event(['AC_load_data', {'source': {
            'kind': 'json', 'path': tmp_path / 'outside.json'}}])


def test_loaded_action_file_keeps_nested_roots(bridge, tmp_path, monkeypatch):
    from je_auto_control.utils.executor.action_executor import executor
    from je_auto_control.utils.path_guard.policy import PathPolicy
    allowed = tmp_path / 'allowed'
    allowed.mkdir()
    path = allowed / 'script.json'
    path.write_text(json.dumps([['AC_load_data', {'source': {
        'kind': 'json', 'path': str(tmp_path / 'outside.json')}}]]), encoding='utf-8')
    calls = []
    monkeypatch.setitem(executor.event_dict, 'AC_load_data', lambda source: calls.append(source))
    bridge._path_policy = PathPolicy([allowed])
    result = bridge._handle_tools_call(1, {'name': 'ac_execute_action_file', 'arguments': {
        'file_path': str(path)}})
    assert calls == []
    assert 'outside the allowed roots' in json.dumps(result)


def test_parallel_workers_keep_scoped_roots(tmp_path, monkeypatch):
    from je_auto_control.utils.executor.action_executor import Executor
    from je_auto_control.utils.path_guard.policy import PathPolicy, path_policy_scope
    from je_auto_control.utils.exception.exceptions import AutoControlException
    original = Executor.__init__
    calls = []
    def initialize(self):
        original(self)
        self.event_dict['AC_load_data'] = lambda source: calls.append(source)
    monkeypatch.setattr(Executor, '__init__', initialize)
    allowed = tmp_path / 'allowed'
    allowed.mkdir()
    with path_policy_scope(PathPolicy([allowed])), pytest.raises(AutoControlException):
        Executor().execute_action([['AC_parallel', {'branches': [
            [['AC_load_data', {'source': {'kind': 'json', 'path': str(tmp_path / 'outside.json')}}]]
        ]}]], raise_on_error=True)
    assert calls == []


def test_device_worker_inherits_paths(tmp_path, monkeypatch):
    from je_auto_control.utils.device_matrix import run_on_devices
    from je_auto_control.utils.executor.action_executor import Executor
    from je_auto_control.utils.path_guard.policy import PathPolicy, path_policy_scope
    original = Executor.__init__
    calls = []

    def initialize(self):
        original(self)
        self.event_dict['AC_load_data'] = lambda source: calls.append(source)

    monkeypatch.setattr(Executor, '__init__', initialize)
    allowed = tmp_path / 'allowed'
    allowed.mkdir()
    with path_policy_scope(PathPolicy([allowed])):
        actions = [['AC_load_data', {'source': {'kind': 'json', 'path': str(tmp_path / 'outside.json')}}]]
        report = run_on_devices(actions,
                                [{'serial': 'fake', 'platform': 'fake'}])
    assert report.failed == 1
    assert calls == []


def test_deferred_observer_inherits_request_boundaries(monkeypatch):
    from je_auto_control.utils.executor import action_executor
    executor = action_executor.Executor()
    calls = []
    executor.event_dict['AC_shell'] = lambda command: calls.append(command)
    monkeypatch.setattr(action_executor, '_running_executor', lambda: executor)
    with authorization_scope(AuthorizationContext('operator', 'operator')):
        handler = action_executor._observe_handler([['AC_shell', {'command': 'not-executed'}]])
    worker = threading.Thread(target=handler, args=('appear', None))
    worker.start()
    worker.join(timeout=3)
    assert not worker.is_alive()
    assert calls == []


def test_scheduled_job_retains_registration_identity(tmp_path, monkeypatch):
    from je_auto_control.utils.scheduler import scheduler as module
    from je_auto_control.utils.run_history.history_store import HistoryStore
    from je_auto_control.utils.executor.action_executor import Executor
    calls = []
    executor = Executor()
    executor.event_dict['AC_shell'] = lambda command: calls.append(command)
    monkeypatch.setattr(module, 'default_history_store', HistoryStore())
    monkeypatch.setattr(module, 'capture_error_snapshot', lambda run_id: None)
    path = tmp_path / 'scheduled.json'
    path.write_text(json.dumps([['AC_shell', {'command': 'not-executed'}]]), encoding='utf-8')
    scheduler = module.Scheduler(executor=executor.execute_action)
    with authorization_scope(AuthorizationContext('operator', 'operator')):
        job = scheduler.add_job(str(path), 1, repeat=False)
    worker = threading.Thread(target=scheduler._fire, args=(job, 0, 0))
    worker.start()
    worker.join(timeout=3)
    assert not worker.is_alive()
    assert calls == []


def test_deferred_deliveries_keep_independent_variable_snapshots():
    from je_auto_control.utils.executor.request_context import RequestBinding
    from je_auto_control.utils.script_vars.scope import execution_scope, current_execution_scope
    with execution_scope({'items': ['registration']}, isolated=True) as scope:
        binding = RequestBinding.capture()
        scope['items'].append('later')

    def deliver():
        active = current_execution_scope()
        before = list(active['items'])
        active['items'].append('delivery')
        return before

    assert binding.run(deliver) == ['registration']
    assert binding.run(deliver) == ['registration']


def test_default_encryption_key_obeys_active_roots(tmp_path, monkeypatch):
    from je_auto_control.utils.action_signing import cipher
    from je_auto_control.utils.path_guard.policy import PathPolicy, path_policy_scope
    from je_auto_control.utils.path_guard.path_guard import PathNotAllowedError
    allowed = tmp_path / 'allowed'
    allowed.mkdir()
    monkeypatch.setattr(cipher, '_default_key_path', lambda: tmp_path / 'outside-key')
    with path_policy_scope(PathPolicy([allowed])), pytest.raises(PathNotAllowedError):
        cipher._persistent_key()
    assert not (tmp_path / 'outside-key').exists()


def test_block_file_read_enforces_root_after_interpolation(tmp_path):
    from je_auto_control.utils.executor.action_executor import Executor
    from je_auto_control.utils.path_guard.policy import PathPolicy, path_policy_scope
    from je_auto_control.utils.path_guard.path_guard import PathNotAllowedError
    from je_auto_control.utils.script_vars.scope import execution_scope
    allowed = tmp_path / 'allowed'
    allowed.mkdir()
    outside = tmp_path / 'outside.txt'
    outside.write_text('not-sensitive', encoding='utf-8')
    with execution_scope({'file': str(outside)}, isolated=True):
        with path_policy_scope(PathPolicy([allowed])), pytest.raises(PathNotAllowedError):
            Executor().execute_action([
                ['AC_read_file_to_var', {'path': '${file}', 'var': 'content'}],
            ], raise_on_error=True)


def test_clipped_color_coordinates_use_actual_origin(monkeypatch):
    import numpy as np
    from PIL import Image
    from je_auto_control.utils.monitor_layout import logical_frame
    from je_auto_control.utils.color_region import find_color_region
    monkeypatch.setattr(logical_frame, 'logical_virtual_rect', lambda metrics=None: (-4, -4, 8, 8))
    frame = Image.fromarray(np.full((8, 8, 3), [0, 200, 0], dtype=np.uint8))
    monkeypatch.setattr(logical_frame, '_load_image_grab', lambda: SimpleNamespace(grab=lambda **kwargs: frame))
    found = find_color_region((0, 200, 0), region=[-6, -6, -1, -1], min_area=1)
    assert (found['x'], found['y'], found['center']) == (-4, -4, [-3, -3])


def test_clipped_vlm_coordinates_use_actual_origin(monkeypatch):
    from PIL import Image
    from je_auto_control.utils.monitor_layout import logical_frame
    from je_auto_control.utils.vision.vlm_api import locate_by_description
    monkeypatch.setattr(logical_frame, 'logical_virtual_rect', lambda metrics=None: (-4, -4, 8, 8))
    frame = Image.new('RGB', (8, 8), 'white')
    monkeypatch.setattr(logical_frame, '_load_image_grab', lambda: SimpleNamespace(grab=lambda **kwargs: frame))
    backend = SimpleNamespace(available=True, locate=lambda *args, **kwargs: (1, 1))
    assert locate_by_description('target', [-6, -6, -1, -1], backend=backend) == (-3, -3)


@pytest.mark.skipif(sys.platform != 'win32', reason='Win32 ctypes module')
def test_restore_minimized_to_maximized_succeeds(monkeypatch):
    from je_auto_control.windows.window import windows_window_manage as window
    iconic = [True]
    def show(hwnd, command):
        iconic[0] = False
        return True
    monkeypatch.setattr(window, '_user32', SimpleNamespace(
        IsWindow=lambda hwnd: True, ShowWindow=show,
        IsWindowVisible=lambda hwnd: True, IsIconic=lambda hwnd: iconic[0],
        IsZoomed=lambda hwnd: not iconic[0], SetForegroundWindow=lambda hwnd: True))
    assert window.show_window(42, 9) is True

def test_removed_scheduled_job_cannot_fall_back_to_unrestricted_execution(tmp_path, monkeypatch):
    from je_auto_control.utils.scheduler import scheduler as module
    from je_auto_control.utils.run_history.history_store import HistoryStore
    from je_auto_control.utils.executor.action_executor import Executor
    calls = []
    executor = Executor()
    executor.event_dict['AC_shell'] = lambda command: calls.append(command)
    monkeypatch.setattr(module, 'default_history_store', HistoryStore())
    monkeypatch.setattr(module, 'capture_error_snapshot', lambda run_id: None)
    path = tmp_path / 'removed.json'
    path.write_text(json.dumps([['AC_shell', {'command': 'not-executed'}]]), encoding='utf-8')
    scheduler = module.Scheduler(executor=executor.execute_action)
    with authorization_scope(AuthorizationContext('operator', 'operator')):
        job = scheduler.add_job(str(path), 1)
    scheduler.remove_job(job.job_id)
    scheduler._fire(job, 0, 0)
    assert calls == []
