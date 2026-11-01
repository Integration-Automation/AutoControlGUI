"""X11 presence counts raw events from real devices only, and reads logind lock state fail-closed."""
import os
import struct
import subprocess
import sys
import threading
from types import SimpleNamespace

import pytest

from je_auto_control.utils.agent_runtime import presence_x11
from je_auto_control.utils.agent_runtime.errors import AgentControlBusy, AgentTaskError
from je_auto_control.utils.agent_runtime.presence_x11 import LogindSession, X11PresenceAPI

OPCODE = 131
KEYBOARD, XTEST = 8, 9


def raw(evtype, source, detail=38):
    return SimpleNamespace(type=35, extension=OPCODE, evtype=evtype,
                           data=struct.pack('=HIIHH', source, 0, detail, source, 0) + bytes(8))


class FakeDisplay:
    def __init__(self, devices=None, version=2):
        self.devices = devices if devices is not None else [
            SimpleNamespace(deviceid=2, use=1, name='Virtual core pointer'),
            SimpleNamespace(deviceid=KEYBOARD, use=4, name='AT keyboard'),
            SimpleNamespace(deviceid=XTEST, use=4, name='Virtual core XTEST keyboard')]
        self.version, self.queue, self.selected, self.closed = version, [], [], False
        self.keymap, self.mask, self.queries = [0] * 32, 0, 0
        root = SimpleNamespace(xinput_select_events=self.selected.append,
                               query_pointer=lambda: SimpleNamespace(mask=self.mask))
        self._screen = SimpleNamespace(root=root)

    def has_extension(self, name):
        return name == 'XInputExtension'

    def xinput_query_version(self):
        return SimpleNamespace(major_version=self.version)

    def get_extension_major(self, _name):
        return OPCODE

    def xinput_query_device(self, _which):
        self.queries += 1
        return SimpleNamespace(devices=self.devices)

    def screen(self):
        return self._screen

    def flush(self):
        pass

    def fileno(self):
        return -1

    def pending_events(self):
        return len(self.queue)

    def next_event(self):
        return self.queue.pop(0)

    def query_keymap(self):
        return self.keymap

    def close(self):
        self.closed = True


@pytest.fixture
def opened(monkeypatch):
    monkeypatch.setattr(presence_x11.select, 'select', lambda read, *_args: (read, [], []))
    display, physical = FakeDisplay(), []
    api = X11PresenceAPI(lambda: display, interactive=lambda: True)
    api.open(lambda: physical.append(1))
    return api, display, physical


def test_open_selects_raw_and_hierarchy_events_for_every_device(opened):
    _api, display, _physical = opened
    assert display.selected == [[(0, presence_x11._MASK)]]
    assert presence_x11._MASK == (1 << 11) | sum(1 << code for code in range(13, 18))


def test_xtest_events_never_count_as_physical(opened):
    api, display, physical = opened
    display.queue[:] = [raw(13, XTEST), raw(17, XTEST)]
    assert api.poll(0) == (True, False)
    assert physical == []


def test_real_device_events_count_and_track_what_is_held(opened):
    api, display, physical = opened
    display.queue[:] = [raw(13, KEYBOARD, 38)]
    assert api.poll(0) == (True, True) and physical == [1]
    display.queue[:] = [raw(14, KEYBOARD, 38)]
    assert api.poll(0) == (True, False) and physical == [1, 1]


def test_core_state_counts_as_held_even_without_a_tracked_press(opened):
    api, display, _physical = opened
    display.keymap = [0] * 31 + [4]
    assert api.poll(0)[1] is True
    display.keymap, display.mask = [0] * 32, 0x100
    assert api.poll(0)[1] is True


def test_an_unknown_source_refreshes_devices_and_counts_once_it_is_a_real_slave(opened):
    api, display, physical = opened
    display.devices.append(SimpleNamespace(deviceid=12, use=3, name='USB mouse'))
    display.queue[:] = [raw(17, 12)]
    api.poll(0)
    assert physical == [1] and display.queries == 2


def test_a_master_device_is_never_a_source(opened):
    api, display, physical = opened
    display.queue[:] = [raw(17, 2)]
    api.poll(0)
    assert physical == []


def test_an_endless_queue_is_busy_rather_than_drained_forever(opened):
    api, display, _physical = opened
    display.queue[:] = [raw(17, XTEST)] * (presence_x11._DRAIN_LIMIT + 1)
    with pytest.raises(AgentControlBusy):
        api.poll(0)


@pytest.mark.parametrize('timeout', [-1, 0.06, float('nan'), True])
def test_poll_deadlines_are_bounded(opened, timeout):
    with pytest.raises(AgentTaskError):
        opened[0].poll(timeout)


def test_xinput_one_and_a_second_open_are_refused():
    with pytest.raises(AgentTaskError, match='could not start|XInput 2'):
        X11PresenceAPI(lambda: FakeDisplay(version=1), interactive=lambda: True).open(lambda: None)
    api = X11PresenceAPI(FakeDisplay, interactive=lambda: True)
    api.open(lambda: None)
    with pytest.raises(AgentTaskError, match='cannot restart'):
        api.open(lambda: None)


def test_close_deselects_closes_and_belongs_to_the_opening_thread(opened):
    api, display, _physical = opened
    outcome = []

    def foreign_close():
        try:
            api.close()
            outcome.append('closed')
        except AgentTaskError:
            outcome.append('refused')
    worker = threading.Thread(target=foreign_close)
    worker.start()
    worker.join()
    assert outcome == ['refused'] and not display.closed
    api.close()
    assert display.selected[-1] == [(0, 0)] and display.closed
    with pytest.raises(AgentTaskError):
        api.poll(0)


def _runner(stdout, returncode=0, calls=None):
    def run(argv, **kwargs):
        if calls is not None:
            calls.append((argv, kwargs))
        return SimpleNamespace(returncode=returncode, stdout=stdout)
    return run


@pytest.mark.parametrize('stdout,returncode,expected', [
    ('Active=yes\nLockedHint=no\n', 0, True),
    ('Active=yes\nLockedHint=yes\n', 0, False),
    ('Active=no\nLockedHint=no\n', 0, False),
    ('', 1, False),
    ('garbage', 0, False),
])
def test_logind_reads_active_and_unlocked_and_doubts_as_locked(monkeypatch, stdout, returncode, expected):
    monkeypatch.setattr(presence_x11.shutil, 'which', lambda _name: '/usr/bin/loginctl')
    assert LogindSession('c2', runner=_runner(stdout, returncode)).interactive() is expected


def test_logind_without_a_session_tool_or_with_a_failing_call_reads_locked(monkeypatch):
    monkeypatch.setattr(presence_x11.shutil, 'which', lambda _name: None)
    assert LogindSession('c2', runner=_runner('Active=yes\nLockedHint=no')).interactive() is False
    monkeypatch.setattr(presence_x11.shutil, 'which', lambda _name: '/usr/bin/loginctl')
    assert LogindSession('', runner=_runner('Active=yes\nLockedHint=no')).interactive() is False
    assert LogindSession('c2; rm', runner=_runner('Active=yes\nLockedHint=no')).interactive() is False

    def failing(*_args, **_kwargs):
        raise subprocess.TimeoutExpired('loginctl', 1)
    assert LogindSession('c2', runner=failing).interactive() is False


def test_logind_is_queried_with_a_fixed_argv_and_cached_for_its_interval(monkeypatch):
    monkeypatch.setattr(presence_x11.shutil, 'which', lambda _name: '/usr/bin/loginctl')
    calls, now = [], [0.0]
    session = LogindSession('c2', runner=_runner('Active=yes\nLockedHint=no', calls=calls), clock=lambda: now[0])
    assert session.interactive() and session.interactive()
    now[0] = 1.5
    session.interactive()
    assert len(calls) == 2
    argv, kwargs = calls[0]
    assert argv == ['/usr/bin/loginctl', 'show-session', 'c2', '-p', 'Active', '-p', 'LockedHint']
    assert kwargs['shell'] is False and kwargs['timeout'] == 1


@pytest.mark.skipif(not sys.platform.startswith('linux') or not os.environ.get('DISPLAY'),
                    reason='needs a real X display (CI runs the suite under Xvfb)')
def test_a_real_x_server_reports_xtest_injection_as_not_physical():
    from Xlib import X, XK, display
    from Xlib.ext import xtest
    physical = []
    api = X11PresenceAPI(interactive=lambda: False)
    api.open(lambda: physical.append(1))
    injector = display.Display()
    try:
        keycode = injector.keysym_to_keycode(XK.string_to_keysym('a'))
        xtest.fake_input(injector, X.KeyPress, keycode)
        xtest.fake_input(injector, X.KeyRelease, keycode)
        xtest.fake_input(injector, X.MotionNotify, x=5, y=5)
        injector.sync()
        for _attempt in range(20):
            api.poll(0.05)
        assert physical == []
    finally:
        injector.close()
        api.close()
