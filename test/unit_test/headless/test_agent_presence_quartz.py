"""macOS presence counts hardware events, errs toward presence and needs the tap permission."""
import sys

import pytest

from je_auto_control.utils.agent_runtime import presence_quartz
from je_auto_control.utils.agent_runtime.errors import AgentControlBusy, AgentTaskError
from je_auto_control.utils.agent_runtime.presence_quartz import QuartzPresenceAPI, is_injected


class FakeQuartz:
    kCGSessionEventTap = 1
    kCGHeadInsertEventTap = 0
    kCGEventTapOptionListenOnly = 1
    kCFRunLoopDefaultMode = 'default'
    kCGEventSourceStateHIDSystemState = 1

    def __init__(self, *, tap=True):
        self.tap = object() if tap else None
        self.callback = None
        self.pending, self.enabled, self.calls = [], True, []
        self.session = {'kCGSSessionOnConsoleKey': True}
        self.buttons, self.keys = set(), set()

    def CGEventTapCreate(self, *args):
        self.callback = args[4]
        return self.tap

    def CFMachPortCreateRunLoopSource(self, *_args):
        return 'source'

    def CFRunLoopGetCurrent(self):
        return 'loop'

    def CFRunLoopAddSource(self, *args):
        self.calls.append(('add',) + args)

    def CFRunLoopRemoveSource(self, *args):
        self.calls.append(('remove',) + args)

    def CGEventTapEnable(self, _tap, enabled):
        self.enabled = enabled
        self.calls.append(('enable', enabled))

    def CGEventTapIsEnabled(self, _tap):
        return self.enabled

    def CFMachPortInvalidate(self, _tap):
        self.calls.append(('invalidate',))

    def CFRunLoopRunInMode(self, _mode, _seconds, _once):
        if not self.pending:
            return 3
        kind, fields = self.pending.pop(0)
        self.callback(None, kind, fields, None)
        return 4

    def CGEventGetIntegerValueField(self, event, field):
        return event.get(field, 0)

    def CGSessionCopyCurrentDictionary(self):
        return self.session

    def CGEventSourceButtonState(self, _state, button):
        return button in self.buttons

    def CGEventSourceKeyState(self, _state, key):
        return key in self.keys


def event(kind, *, pid=0, state=1, keycode=0, button=0):
    return kind, {41: pid, 45: state, 9: keycode, 3: button}


@pytest.fixture
def opened():
    quartz, physical = FakeQuartz(), []
    api = QuartzPresenceAPI(lambda: quartz)
    api.open(lambda: physical.append(1))
    return api, quartz, physical


@pytest.mark.parametrize('pid,state,injected', [
    (0, 1, False), (0, 0, False), (812, 1, False), (812, 0, True), (812, -1, True), (-1, 0, False),
])
def test_only_a_process_posting_from_a_non_hid_state_counts_as_injected(pid, state, injected):
    assert is_injected(pid, state) is injected


def test_hardware_events_count_and_track_held_keys_and_buttons(opened):
    api, quartz, physical = opened
    quartz.pending[:] = [event(10, keycode=4), event(1)]
    assert api.poll(0) == (True, True) and physical == [1, 1]
    quartz.pending[:] = [event(11, keycode=4), event(2)]
    assert api.poll(0) == (True, False)


def test_events_a_process_posted_never_count(opened):
    api, quartz, physical = opened
    quartz.pending[:] = [event(10, pid=4242, state=0, keycode=4), event(5, pid=4242, state=-1)]
    assert api.poll(0) == (True, False) and physical == []


def test_a_key_down_before_the_tap_started_still_counts_as_held(opened):
    api, quartz, _physical = opened
    quartz.keys.add(56)
    assert api.poll(0)[1] is True
    quartz.keys.clear()
    quartz.buttons.add(0)
    assert api.poll(0)[1] is True


@pytest.mark.parametrize('session,interactive', [
    ({'kCGSSessionOnConsoleKey': True}, True),
    ({'kCGSSessionOnConsoleKey': True, 'CGSSessionScreenIsLocked': True}, False),
    ({'kCGSSessionOnConsoleKey': False}, False),
    (None, False),
])
def test_the_console_is_usable_only_on_console_and_unlocked(opened, session, interactive):
    api, quartz, _physical = opened
    quartz.session = session
    assert api.poll(0)[0] is interactive


def test_a_missing_permission_refuses_to_start():
    with pytest.raises(AgentTaskError, match='Accessibility'):
        QuartzPresenceAPI(lambda: FakeQuartz(tap=False)).open(lambda: None)


def test_a_disabled_tap_fails_the_source(opened):
    api, quartz, _physical = opened
    quartz.pending[:] = [(0xFFFFFFFE, {})]
    with pytest.raises(AgentTaskError, match='failed or was disabled'):
        api.poll(0)
    with pytest.raises(AgentTaskError):
        api.poll(0)


def test_an_endless_queue_is_busy(opened):
    api, quartz, _physical = opened
    quartz.pending[:] = [event(5, pid=1, state=0)] * (presence_quartz._DRAIN_LIMIT + 1)
    with pytest.raises(AgentControlBusy):
        api.poll(0)


def test_close_disables_removes_and_invalidates_the_tap(opened):
    api, quartz, _physical = opened
    api.close()
    assert quartz.calls[-3:] == [('enable', False), ('remove', 'loop', 'source', 'default'), ('invalidate',)]
    with pytest.raises(AgentTaskError):
        api.poll(0)


@pytest.mark.skipif(sys.platform != 'darwin', reason='needs a real macOS window server')
def test_a_real_tap_classifies_an_event_this_process_posts_consistently(record_property):
    import Quartz
    seen, physical = [], []

    class Recording(QuartzPresenceAPI):
        def _callback(self, proxy, kind, value, refcon):
            seen.append((kind, int(Quartz.CGEventGetIntegerValueField(value, 41)),
                         int(Quartz.CGEventGetIntegerValueField(value, 45))))
            return super()._callback(proxy, kind, value, refcon)

    api = Recording()
    try:
        api.open(lambda: physical.append(1))
    except AgentTaskError as error:
        pytest.skip(f'this runner grants no event tap: {error}')
    try:
        for position in ((10, 10), (20, 20)):
            moved = Quartz.CGEventCreateMouseEvent(None, Quartz.kCGEventMouseMoved, position, 0)
            Quartz.CGEventPost(Quartz.kCGHIDEventTap, moved)
        for _attempt in range(20):
            api.poll(0.05)
    finally:
        api.close()
    # What a posted event really carries is the evidence this test exists to record.
    record_property('posted_event_fields', repr(seen))
    print('posted_event_fields', seen)
    assert len(physical) == sum(not is_injected(pid, state) for _kind, pid, state in seen)
