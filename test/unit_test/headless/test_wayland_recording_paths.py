"""Recording and the stop shortcut on Wayland, against fakes.

Two different things were always called "record": what this program executed,
and what the user physically did. The first needs no hook on any platform; the
second needs kernel devices and is opt-in. These tests keep the two apart, and
pin the three rules the physical reader lives by — it reads only what it was
told to, never a virtual device, and never with borrowed privilege.

Nothing here opens a real device or a real bus. Whether ``/sys`` really
parents uinput devices where :class:`InputDevice` looks, and whether a real
portal implements GlobalShortcuts, are Linux questions; the manual checklist
in ``test/manual_test/wayland_authorisation_checklist.md`` covers them.
"""
import threading

import pytest

from je_auto_control.linux_wayland import _dbus_client
from je_auto_control.linux_wayland import global_shortcuts as shortcuts
from je_auto_control.linux_wayland import input_events as events_mod
from je_auto_control.linux_wayland import listener as wl_listener
from je_auto_control.linux_wayland.input_events import (
    InputStepLog, EV_KEY, InputDevice, InputEvent, InputPermissionError,
    InputRecordingError, PhysicalRecorder,
)
from je_auto_control.linux_wayland.record import wayland_recorder
from je_auto_control.utils.exception.exceptions import AutoControlException

KEYBOARD = InputDevice(
    "/dev/input/event3", name="AT Translated Set 2 keyboard",
    phys="isa0060/serio0/input0", bustype=0x11,
    sysfs="/sys/devices/platform/i8042/serio0/input/input3/event3")
YDOTOOL = InputDevice(
    "/dev/input/event19", name="ydotoold virtual device", bustype=0x06,
    sysfs="/sys/devices/virtual/input/input23/event19")
BLUETOOTH = InputDevice(
    "/dev/input/event21", name="Keychron K2", bustype=0x05,
    sysfs="/sys/devices/virtual/misc/uhid/0005:05AC:024F.0003/input/input25/"
          "event21")
KEY_A = 30


class FakeSource:
    """An opened device that hands out one scripted burst, then nothing."""

    def __init__(self, path, burst):
        self.path = path
        self._burst = list(burst)
        self.closed = False
        self.delivered = threading.Event()

    def read_events(self, _timeout):
        if self._burst:
            burst, self._burst = self._burst, []
            self.delivered.set()
            return burst
        self.delivered.set()
        return []

    def close(self):
        self.closed = True


def _opener(bursts, opened):
    def open_device(path):
        opened.append(FakeSource(path, bursts.get(path, ())))
        return opened[-1]
    return open_device


# === the four behaviours the plan names =====================================

def test_action_recording_needs_no_global_hook(monkeypatch):
    """What the program executed is journalled with nothing read from input."""
    from je_auto_control.utils.executor.action_executor import executor

    def no_hook(*_args, **_kwargs):
        raise AssertionError("journalling must not install or use a hook")

    monkeypatch.setattr(wl_listener, "hook_keyboard", no_hook)
    monkeypatch.setattr(wl_listener, "check_key_press", no_hook)
    monkeypatch.setattr(PhysicalRecorder, "start", no_hook)
    done = []
    monkeypatch.setitem(executor.event_dict, "AC_journal_probe",
                        lambda **params: done.append(params))
    expected_steps = [["AC_journal_probe", {"step": 1}],
                      ["AC_journal_probe", {"step": 2}]]

    journal = InputStepLog()
    journal.run([list(step) for step in expected_steps])

    executor_journal_steps = journal.steps
    assert executor_journal_steps == expected_steps
    assert done == [{"step": 1}, {"step": 2}]
    # A copy: the caller cannot rewrite history by mutating what came back.
    executor_journal_steps[0][1]["step"] = 99
    assert journal.steps == expected_steps
    journal.clear()
    assert journal.steps == []


def test_physical_reader_excludes_virtual_device():
    """This program's own ydotool output is never recorded as the user's."""
    typed = [InputEvent(EV_KEY, KEY_A, 1, 1.0, KEYBOARD.path),
             InputEvent(EV_KEY, KEY_A, 0, 1.1, KEYBOARD.path)]
    injected = [InputEvent(EV_KEY, 48, 1, 1.2, YDOTOOL.path)]
    opened = []
    recorder = PhysicalRecorder(
        opener=_opener({KEYBOARD.path: typed, YDOTOOL.path: injected}, opened),
        poll_s=0.01)

    recorder.start([KEYBOARD, YDOTOOL])
    assert opened[0].delivered.wait(5)
    recorded = recorder.stop()

    injected_events = [event for event in recorded
                       if event.device == YDOTOOL.path]
    assert injected_events == []
    assert recorded == typed
    assert [source.path for source in opened] == [KEYBOARD.path]
    assert recorder.excluded == [YDOTOOL]
    assert opened[0].closed is True
    assert recorder.is_recording is False

    assert YDOTOOL.is_virtual
    assert not KEYBOARD.is_virtual
    # A Bluetooth keyboard sits under /devices/virtual too, and is real.
    assert BLUETOOTH.is_virtual is False
    # A uinput device that does not admit to BUS_VIRTUAL is still caught.
    assert InputDevice("/dev/input/event9", bustype=0x03,
                       sysfs=YDOTOOL.sysfs).is_virtual


def test_permission_denial_is_actionable():
    """No access is a typed error that says what to do — and not "use root"."""
    opened = []

    def deny_second(path):
        if path == BLUETOOTH.path:
            raise PermissionError(13, "Permission denied", path)
        opened.append(FakeSource(path, ()))
        return opened[-1]

    recorder = PhysicalRecorder(opener=deny_second, poll_s=0.01)
    with pytest.raises(InputPermissionError) as denied:
        recorder.start([KEYBOARD, BLUETOOTH])

    permission_error = denied.value
    assert permission_error.has_recovery_instruction
    assert permission_error.path == BLUETOOTH.path
    assert "`input` group" in permission_error.recovery
    assert "Do not run the whole program as root" in str(permission_error)
    assert isinstance(permission_error, AutoControlException)
    # All or nothing: the device that did open was closed again.
    assert [source.closed for source in opened] == [True]
    assert recorder.is_recording is False
    assert recorder.stop() == []


def test_shortcut_session_closes():
    """The registration ends when the session is closed, exactly once."""
    bus = FakeBus()
    stops = []
    session = shortcuts.StopShortcutSession(
        lambda: stops.append("stop"), bus_factory=lambda: bus,
        preferred_trigger="CTRL+ALT+F12")

    session.open(timeout=1.0)
    assert session.is_open
    assert [call[2] for call in bus.calls] == ["CreateSession",
                                               "BindShortcuts"]
    bound = bus.calls[1][4]
    assert bound[0] == bus.session_handle
    assert [item[0] for item in bound[1]] == [shortcuts.STOP_SHORTCUT_ID]
    assert bound[1][0][1]["preferred_trigger"].value == "CTRL+ALT+F12"

    assert session.wait(0.01) is False
    bus.signals.append([bus.session_handle, "something-else", 1, {}])
    assert session.wait(0.01) is False
    bus.signals.append(["/another/session", shortcuts.STOP_SHORTCUT_ID, 1, {}])
    assert session.wait(0.01) is False
    bus.signals.append([bus.session_handle, shortcuts.STOP_SHORTCUT_ID, 2, {}])
    assert session.wait(0.01) is True
    assert stops == ["stop"]

    session.close()
    session.close()
    closes = [call for call in bus.calls if call[2] == "Close"]
    assert len(closes) == 1
    assert closes[0][0] == bus.session_handle
    assert closes[0][1] == shortcuts.SESSION_INTERFACE
    assert bus.closed == 1
    assert session.is_open is False
    assert session.wait(0.01) is False


# === the physical reader's other rules ======================================

def test_recording_is_opt_in_per_device():
    recorder = PhysicalRecorder(opener=_opener({}, []), poll_s=0.01)
    with pytest.raises(InputRecordingError) as unnamed:
        recorder.start([])
    assert "opt-in" in str(unnamed.value)
    devices = [YDOTOOL, InputDevice("/dev/input/event7")]
    with pytest.raises(InputRecordingError) as nothing_physical:
        recorder.start(devices)
    assert "virtual or of unknown origin" in str(nothing_physical.value)
    assert recorder.is_recording is False


def test_a_second_recording_is_refused_and_the_buffer_is_bounded():
    burst = [InputEvent(EV_KEY, KEY_A, index % 2, 0.0, KEYBOARD.path)
             for index in range(10)]
    opened = []
    recorder = PhysicalRecorder(opener=_opener({KEYBOARD.path: burst}, opened),
                                max_events=4, poll_s=0.01)
    recorder.start([KEYBOARD])
    with pytest.raises(InputRecordingError):
        recorder.start([KEYBOARD])
    assert opened[0].delivered.wait(5)
    recorded = recorder.stop()
    assert recorded == burst[:4]
    assert recorder.truncated is True


def test_events_are_decoded_in_the_native_layout():
    packed = (events_mod._EVENT.pack(10, 500_000, EV_KEY, KEY_A, 1)
              + events_mod._EVENT.pack(11, 0, EV_KEY, KEY_A, 0)
              + b"\x00\x01")                 # a truncated tail is dropped
    decoded = events_mod.decode_events(packed, "/dev/input/event3")
    assert decoded == [
        InputEvent(EV_KEY, KEY_A, 1, 10.5, "/dev/input/event3"),
        InputEvent(EV_KEY, KEY_A, 0, 11.0, "/dev/input/event3")]


def test_a_device_is_described_from_sysfs_without_opening_it(tmp_path):
    virtual_root = tmp_path / "devices" / "virtual" / "input"
    node = virtual_root / "event19" / "device"
    (node / "id").mkdir(parents=True)
    (node / "name").write_text("ydotoold virtual device\n", encoding="utf-8")
    (node / "id" / "bustype").write_text("0006\n", encoding="utf-8")

    described = events_mod.describe_device("/dev/input/event19",
                                           str(virtual_root))
    assert described.name == "ydotoold virtual device"
    assert described.bustype == events_mod.BUS_VIRTUAL
    assert described.origin_known
    assert described.is_virtual

    listed = events_mod.list_input_devices(str(virtual_root), "/dev/input")
    assert [device.path for device in listed] == ["/dev/input/event19"]
    unknown = events_mod.describe_device("/dev/input/event99",
                                         str(virtual_root))
    assert unknown.origin_known is False
    assert events_mod.list_input_devices(str(tmp_path / "absent")) == []


def test_the_opt_in_setting_is_a_list_of_paths():
    env = {events_mod.RECORD_DEVICES_ENV: " /dev/input/event3 ,,/dev/input/event5"}
    assert events_mod.configured_record_devices(env) == (
        "/dev/input/event3", "/dev/input/event5")
    assert events_mod.configured_record_devices({}) == ()


def test_the_global_recorder_still_refuses_and_now_says_what_works():
    """The seam's recorder is unchanged in kind: it names the alternatives."""
    with pytest.raises(NotImplementedError) as refused:
        wayland_recorder.record()
    message = str(refused.value)
    assert "InputStepLog" in message
    assert "PhysicalRecorder" in message
    assert wl_listener.check_key_is_press(KEY_A) is False


# === the stop shortcut's other paths ========================================

class FakeBus:
    """A session bus whose portal answers GlobalShortcuts as scripted."""

    sender_token = "1_42"
    session_handle = "/org/freedesktop/portal/desktop/session/1_42/stop"

    def __init__(self, bind_response=0, create_results=None):
        self.calls = []
        self.matches = []
        self.signals = []
        self.responses = []
        self.closed = 0
        self._bind_response = bind_response
        self._create_results = (create_results if create_results is not None
                                else {"session_handle": self.session_handle})

    def add_match(self, rule):
        self.matches.append(rule)

    def call(self, destination, path, interface, member, signature, body,
             timeout=25.0):
        self.calls.append((path, interface, member, signature, body))
        if member == "Close":
            return []
        token = body[-1]["handle_token"].value
        request = (f"{shortcuts.PORTAL_PATH}/request/{self.sender_token}/"
                   f"{token}")
        answer = ([0, self._create_results] if member == "CreateSession"
                  else [self._bind_response, {}])
        self.responses.append((request, answer))
        return [request]

    def wait_for_signal(self, paths, interface, member, timeout):
        if member == "Response":
            for index, (path, answer) in enumerate(self.responses):
                if path in paths:
                    del self.responses[index]
                    return answer
        elif self.signals:
            return self.signals.pop(0)
        raise _dbus_client.DBusError("the session bus did not answer in time")

    def close(self):
        self.closed += 1


def test_a_declined_shortcut_is_actionable_and_leaves_nothing_open():
    bus = FakeBus(bind_response=1)
    session = shortcuts.StopShortcutSession(lambda: None,
                                            bus_factory=lambda: bus)
    with pytest.raises(shortcuts.ShortcutPermissionError) as declined:
        session.open(timeout=1.0)
    assert declined.value.has_recovery_instruction
    assert "GUI's stop control" in declined.value.recovery
    assert isinstance(declined.value, AutoControlException)
    # The half-made session was closed, not left registered.
    assert [call[2] for call in bus.calls][-1] == "Close"
    assert bus.closed == 1
    assert session.is_open is False


def test_a_portal_without_global_shortcuts_is_unavailable_not_a_crash():
    class NoInterface(FakeBus):
        def call(self, *args, **kwargs):
            raise _dbus_client.DBusError(
                "org.freedesktop.DBus.Error.UnknownMethod: no such interface")

    bus = NoInterface()
    session = shortcuts.StopShortcutSession(lambda: None,
                                            bus_factory=lambda: bus)
    with pytest.raises(shortcuts.ShortcutUnavailable) as missing:
        session.open(timeout=1.0)
    assert not isinstance(missing.value, shortcuts.ShortcutPermissionError)
    assert missing.value.has_recovery_instruction
    assert bus.closed == 1


def test_the_listener_thread_stops_when_the_session_closes():
    bus = FakeBus()
    pressed = threading.Event()
    session = shortcuts.StopShortcutSession(pressed.set,
                                            bus_factory=lambda: bus,
                                            poll_s=0.01)
    with session:
        session.start()
        bus.signals.append([bus.session_handle, shortcuts.STOP_SHORTCUT_ID,
                            1, {}])
        assert pressed.wait(5)
        listener = session._thread
    assert listener is not None
    assert not listener.is_alive()
    assert bus.closed == 1


def test_a_dead_bus_ends_the_session_instead_of_spinning():
    class Dropped(FakeBus):
        def wait_for_signal(self, paths, interface, member, timeout):
            if member == "Response":
                return super().wait_for_signal(paths, interface, member,
                                               timeout)
            raise _dbus_client.DBusError(
                "the session bus closed the connection")

    session = shortcuts.StopShortcutSession(lambda: None,
                                            bus_factory=Dropped)
    session.open(timeout=1.0)
    assert session.wait(0.01) is False
    assert session.is_open is False
    session.close()


def test_the_bind_request_marshals_with_the_real_writer():
    """The one signature here the portal tier never used: ``a(sa{sv})``."""
    from je_auto_control.utils.dbus_client import session_bus

    bus = FakeBus()
    shortcuts.StopShortcutSession(lambda: None, bus_factory=lambda: bus,
                                  preferred_trigger="CTRL+ALT+F12",
                                  ).open(timeout=1.0)
    _path, _interface, _member, signature, body = bus.calls[1]
    payload = session_bus._Writer()
    for code, value in session_bus.body_pairs(signature, body):
        payload.value(code, value)
    assert signature == "oa(sa{sv})sa{sv}"
    assert b"preferred_trigger" in payload.data
    assert shortcuts.STOP_SHORTCUT_ID.encode() in payload.data
