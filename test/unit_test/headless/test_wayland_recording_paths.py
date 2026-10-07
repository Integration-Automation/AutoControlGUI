"""Explicit physical event capture must exclude injected devices and fail closed."""
from collections import deque
from pathlib import Path
import sys
import threading
import time
from unittest.mock import Mock

import pytest

from je_auto_control.linux_wayland.input_events import (
    InputDevice, PhysicalRecorder, RecordingUnavailable, EVENT_STRUCT,
)


def test_action_recording_needs_no_global_hook(tmp_path, monkeypatch):
    from je_auto_control.utils.action_journal import api
    from je_auto_control.utils.action_journal import read_events
    from je_auto_control.utils.executor import action_executor
    from je_auto_control.utils.run_history.history_store import HistoryStore

    from je_auto_control.linux_wayland import input_events
    injected_events = []
    monkeypatch.setattr(input_events._LinuxReader, 'open', lambda device: injected_events.append(device))
    executor = action_executor.Executor()
    executor.event_dict['AC_record_probe'] = lambda: None
    monkeypatch.setattr(action_executor, 'executor', executor)
    monkeypatch.setattr(api, 'default_history_store', HistoryStore())
    monkeypatch.setattr(PhysicalRecorder, 'start', lambda *args: pytest.fail('opened a physical device'))
    monkeypatch.setattr('je_auto_control.linux_wayland.global_shortcuts.StopShortcutSession.start',
                        lambda *args: pytest.fail('requested a global shortcut'))
    path = tmp_path / 'actions.jsonl'
    api.execute_journaled([['AC_record_probe']], str(path), run_id='without-hook')
    executor_journal_steps = [item.command for item in read_events(path)]
    expected_steps = ['AC_record_probe']
    assert injected_events == []
    assert executor_journal_steps == expected_steps


class DeviceIO:
    def __init__(self, events=(), denied=False):
        self.events = deque(events)
        self.denied = denied
        self.opened = []
        self.closed = []
        self.read_done = threading.Event()

    def open(self, device):
        if 'virtual' in device.path:
            return None
        if self.denied:
            raise PermissionError(device.path)
        handle = len(self.opened) + 10
        self.opened.append(device.path)
        return handle

    def poll(self, handles, timeout):
        if self.events:
            return list(handles)[:1]
        time.sleep(min(timeout, 0.005))
        return []

    def read(self, handle):
        value = self.events.popleft()
        self.read_done.set()
        return value

    def close(self, handle):
        self.closed.append(handle)


def event(kind, code, value):
    return EVENT_STRUCT.pack(10, 2000, kind, code, value)


def test_physical_reader_excludes_virtual_device():
    io = DeviceIO([event(1, 42, 1), event(1, 42, 0)])
    recorder = PhysicalRecorder(_io=io)
    recorder.start([InputDevice('/dev/input/virtual'), InputDevice('/dev/input/physical')])
    assert io.read_done.wait(2)
    while io.events:
        time.sleep(0.001)
    captured = recorder.stop()
    assert [(item.code, item.value) for item in captured] == [(42, 1), (42, 0)]
    assert all(item.device == '/dev/input/physical' for item in captured)
    assert io.opened == ['/dev/input/physical']
    assert io.closed == [10]


def test_permission_denial_is_actionable():
    io = DeviceIO(denied=True)
    with pytest.raises(RecordingUnavailable) as error:
        PhysicalRecorder(_io=io).start([InputDevice('/dev/input/event0')])
    assert error.value.has_recovery_instruction
    assert error.value.state == 'needs_permission'
    assert 'ACL' in error.value.recovery
    assert io.closed == []


def test_partial_struct_is_retained_between_reads():
    raw = event(2, 0, -15)
    io = DeviceIO([raw[:7], raw[7:]])
    recorder = PhysicalRecorder(_io=io)
    recorder.start([InputDevice('/dev/input/physical')])
    while io.events:
        time.sleep(0.001)
    captured = recorder.stop()
    assert len(captured) == 1
    assert captured[0].value == -15
    assert captured[0].timestamp_ns == 10_002_000_000


def test_dropped_events_are_not_reported_as_success():
    io = DeviceIO([event(1, 42, 1) + event(0, 3, 0)])
    recorder = PhysicalRecorder(_io=io)
    recorder.start([InputDevice('/dev/input/physical')])
    assert io.read_done.wait(2)
    with pytest.raises(RecordingUnavailable, match='dropped'):
        recorder.stop()
    assert io.closed == [10]


def test_all_virtual_sources_require_explicit_physical_selection():
    io = DeviceIO()
    with pytest.raises(RecordingUnavailable, match='physical'):
        PhysicalRecorder(_io=io).start([InputDevice('/dev/input/virtual')])
    assert not io.opened and not io.closed


def test_startup_failure_closes_already_opened_sources():
    class PartialIO(DeviceIO):
        def open(self, device):
            if self.opened:
                raise PermissionError(device.path)
            return super().open(device)

    io = PartialIO()
    with pytest.raises(RecordingUnavailable):
        PhysicalRecorder(_io=io).start([InputDevice('/dev/input/one'), InputDevice('/dev/input/two')])
    assert io.closed == [10]


def test_duplicate_sources_are_rejected_before_opening():
    io = DeviceIO()
    with pytest.raises(RecordingUnavailable, match='duplicate'):
        PhysicalRecorder(_io=io).start([InputDevice('/dev/input/one')] * 2)
    assert not io.opened


def test_incomplete_event_at_stop_is_not_success():
    io = DeviceIO([event(1, 42, 1)[:7]])
    recorder = PhysicalRecorder(_io=io)
    recorder.start([InputDevice('/dev/input/physical')])
    assert io.read_done.wait(2)
    with pytest.raises(RecordingUnavailable, match='incomplete'):
        recorder.stop()
    assert io.closed == [10]


def test_event_capacity_rejects_partial_recording(monkeypatch):
    from je_auto_control.linux_wayland import input_events

    monkeypatch.setattr(input_events, 'MAX_EVENTS', 1)
    io = DeviceIO([event(1, 42, 1) + event(1, 42, 0)])
    recorder = PhysicalRecorder(_io=io)
    recorder.start([InputDevice('/dev/input/physical')])
    assert io.read_done.wait(2)
    with pytest.raises(RecordingUnavailable, match='budget'):
        recorder.stop()
    assert io.closed == [10]


def test_default_reader_excludes_kernel_virtual_identity_before_open(monkeypatch):
    from je_auto_control.linux_wayland.input_events import _LinuxReader

    node = Path('/dev/input/event0')
    kernel = Path('/sys/class/input/event0/device')

    def resolve(path, strict=False):
        if path == kernel:
            return Path('/sys/devices/virtual/input/input0')
        return path

    opened = Mock()
    monkeypatch.setattr(sys, 'platform', 'linux')
    monkeypatch.setattr(Path, 'resolve', resolve)
    monkeypatch.setattr('os.open', opened)
    assert _LinuxReader.open(InputDevice(str(node))) is None
    opened.assert_not_called()
