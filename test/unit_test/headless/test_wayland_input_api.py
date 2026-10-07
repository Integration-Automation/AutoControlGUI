"""Owned Wayland recording/stop adapters share headless, action and MCP behavior."""
from unittest.mock import Mock
import os
import subprocess
import sys

import pytest

from je_auto_control.api.wayland_input import WaylandInputSession
from je_auto_control.linux_wayland.input_events import InputEvent, RecordingUnavailable
from je_auto_control.linux_wayland.global_shortcuts import ShortcutUnavailable


def test_owned_recording_returns_raw_units_and_closes_independently():
    recorder = Mock(running=False, devices=('/dev/input/event4',), error=None)
    recorder.stop.return_value = [InputEvent('/dev/input/event4', 5, 2, 0, -12)]
    shortcut = Mock(state='closed', error=None, trigger_description='')
    session = WaylandInputSession(_recorder=recorder, _shortcut=shortcut)
    other = WaylandInputSession()
    try:
        session.start_physical(['/dev/input/event4'])
        assert recorder.start.call_args.args[0][0].path == '/dev/input/event4'
        events = session.stop_physical()
        assert events == [{'device': '/dev/input/event4', 'timestamp_ns': 5, 'event_type': 2, 'code': 0, 'value': -12}]
        assert other.status()['physical']['state'] == 'closed'
    finally:
        session.close()
        other.close()
    shortcut.close.assert_called_once()


def test_invalid_device_arguments_are_typed_before_open():
    recorder = Mock()
    session = WaylandInputSession(_recorder=recorder)
    for devices in ['/dev/input/event0', [], [42], ['a'] * 17]:
        with pytest.raises(RecordingUnavailable):
            session.start_physical(devices)
    recorder.start.assert_not_called()
    recorder.stop.return_value = []
    session.close()


def test_close_rejects_restart_and_attempts_both_cleanup_paths():
    recorder = Mock()
    recorder.stop.side_effect = RecordingUnavailable('controlled cleanup failure')
    shortcut = Mock()
    session = WaylandInputSession(_recorder=recorder, _shortcut=shortcut)
    with pytest.raises(RecordingUnavailable):
        session.close()
    shortcut.close.assert_called_once()
    with pytest.raises(RecordingUnavailable, match='closed'):
        session.start_physical(['/dev/input/event0'])
    recorder.stop.side_effect = None
    recorder.stop.return_value = []
    session.close()


def test_ac_and_mcp_delegate_to_owned_script_default(monkeypatch):
    from je_auto_control.utils.executor.action_executor import executor
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    from je_auto_control.wrapper import wayland_input
    from je_auto_control.utils.rbac.authorization import required_capability
    from je_auto_control.utils.rbac.users import Capability

    default = Mock()
    default.status.return_value = {'stop_requested': False}
    monkeypatch.setattr(wayland_input, '_SCRIPT_OWNERS', {'default': default})
    tools = {tool.name: tool for tool in build_default_tool_registry()}
    assert executor.event_dict['AC_wayland_input_status']() == {'stop_requested': False}
    assert tools['ac_wayland_input_status'].handler() == {'stop_requested': False}
    assert tools['ac_wayland_input_status'].annotations.read_only
    for name in ['start_physical_recording', 'stop_physical_recording',
                 'start_wayland_stop_shortcut', 'stop_wayland_stop_shortcut', 'wayland_input_status']:
        assert required_capability('AC_' + name) == Capability.MANAGE_HOSTS
        assert 'ac_' + name in tools


def test_shortcut_stop_signals_caller_and_input_backend():
    recorder = Mock(running=False, devices=(), error=None)
    recorder.stop.return_value = []
    shortcut = Mock(state='available', error=None, trigger_description='Ctrl+F7')
    stopped = Mock()
    session = WaylandInputSession(_recorder=recorder, _shortcut=shortcut, _stop_control=stopped)
    session.start_shortcut('F7')
    shortcut.start.call_args.args[0]()
    assert session.stop_event.is_set()
    stopped.assert_called_once()
    assert session.status()['shortcut']['trigger_description'] == 'Ctrl+F7'
    session.close()


def test_rejected_restart_preserves_caller_cancellation():
    shortcut = Mock()
    shortcut.start.side_effect = ShortcutUnavailable('close previous shortcut')
    recorder = Mock()
    recorder.stop.return_value = []
    session = WaylandInputSession(_recorder=recorder, _shortcut=shortcut)
    session.stop_event.set()
    with pytest.raises(ShortcutUnavailable):
        session.start_shortcut()
    assert session.stop_event.is_set()
    session.close()


def test_raw_physical_result_is_not_persisted_in_action_journal(tmp_path):
    from je_auto_control.utils.action_journal import ActionJournal, read_events
    from je_auto_control.utils.executor.action_executor import Executor

    journal = ActionJournal(tmp_path / 'private-raw.jsonl')
    executor = Executor()
    raw = [{'device': '/dev/input/event4', 'timestamp_ns': 99123456789, 'event_type': 1, 'code': 30, 'value': 1}]
    executor.event_dict['AC_stop_physical_recording'] = lambda: raw
    with journal.run():
        result = executor.execute_action([['AC_stop_physical_recording']])
    assert raw in result.values()
    assert read_events(journal.path)[0].outcome == '***'
    assert '99123456789' not in journal.path.read_text(encoding='utf-8')


def test_beta_wayland_input_import_is_qt_free():
    code = """
import sys
import je_auto_control as ac
from je_auto_control.api.wayland_input import WaylandInputSession
session = WaylandInputSession()
assert session.status()['physical']['state'] == 'closed'
assert ac.start_physical_recording is not None
assert not any(name.startswith('PySide6') for name in sys.modules)
session.close()
"""
    result = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True, timeout=30, check=False)
    assert result.returncode == 0, result.stderr


def test_gui_actions_are_async_and_destruction_closes_only_panel_owner():
    pytest.importorskip('PySide6.QtWidgets', exc_type=ImportError)
    code = """
import threading
import time
from unittest.mock import Mock, patch
from PySide6.QtCore import QCoreApplication, QEvent, QTimer
from PySide6.QtWidgets import QApplication
from je_auto_control.gui.wayland_input_panel import WaylandInputPanel
from je_auto_control.wrapper import wayland_input
app = QApplication([])
entered, released = threading.Event(), threading.Event()
main = threading.get_ident()
calls, ticks = [], []
script = Mock()
with patch.object(wayland_input, '_SCRIPT_OWNERS', {'default': script}):
    panel = WaylandInputPanel()
    other = WaylandInputPanel()
    assert panel.session is not other.session
    owner = panel.session
    def start(devices):
        calls.append((devices, threading.get_ident()))
        entered.set()
        assert released.wait(3)
        return {'raw': True}
    with patch.object(owner, 'start_physical', side_effect=start):
        dict(panel.menu_actions())['wl_start_physical']()
        assert entered.wait(2)
        QTimer.singleShot(20, lambda: ticks.append(True))
        deadline = time.monotonic() + 0.4
        while time.monotonic() < deadline:
            app.processEvents()
            time.sleep(0.005)
        assert ticks == [True]
        assert calls == [(['/dev/input/event0'], calls[0][1])] and calls[0][1] != main
        released.set()
        deadline = time.monotonic() + 2
        while panel._worker is not None and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(0.005)
        assert 'raw' in panel.results.toPlainText()
    panel.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    deadline = time.monotonic() + 2
    while not owner.status()['closed'] and time.monotonic() < deadline:
        time.sleep(0.005)
    assert owner.status()['closed']
    assert not other.session.status()['closed']
    script.close.assert_not_called()
    other.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
"""
    result = subprocess.run([sys.executable, '-c', code], env=dict(os.environ, QT_QPA_PLATFORM='offscreen'),
                            capture_output=True, text=True, timeout=30, check=False)
    assert result.returncode == 0, result.stderr
