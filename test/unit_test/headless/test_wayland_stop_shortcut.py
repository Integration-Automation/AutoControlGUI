"""GlobalShortcuts grant/cancellation/session correlation without a real desktop."""
from collections import deque
import threading
import time

import pytest

from je_auto_control.linux_wayland import _dbus_client as dbus
from je_auto_control.linux_wayland.global_shortcuts import StopShortcutSession, ShortcutUnavailable


def signal(path, member, body, interface='org.freedesktop.portal.GlobalShortcuts'):
    return dbus.Message(dbus.SIGNAL, 1, {dbus.FIELD_PATH: path,
        dbus.FIELD_INTERFACE: interface, dbus.FIELD_MEMBER: member}, body)


class PortalBus(dbus.SessionBus):
    def __init__(self, *, refused=False, pending=False):
        super().__init__('unused')
        self.unique_name = ':1.17'
        self.calls = []
        self.messages = deque()
        self.refused = refused
        self.pending = pending
        self.session = '/org/freedesktop/portal/desktop/session/1_17/grant'
        self.closed = False
        self.bind_requested = threading.Event()

    def connect(self):
        pass

    def add_match(self, rule):
        self.calls.append(('AddMatch', rule))

    def call(self, destination, path, interface, member, signature, body, timeout=25):
        self.calls.append((member, path, signature, body))
        if member in ('CreateSession', 'BindShortcuts'):
            options = body[0] if member == 'CreateSession' else body[-1]
            request = '/org/freedesktop/portal/desktop/request/1_17/' + options['handle_token'].value
            if member == 'CreateSession':
                results = {'session_handle': self.session}
            else:
                self.bind_requested.set()
                results = {'shortcuts': [('autocontrol-stop', {'trigger_description': 'F7'})]}
            if not (self.pending and member == 'BindShortcuts'):
                self._queued.append(signal(request, 'Response', [1 if self.refused else 0, results],
                                           'org.freedesktop.portal.Request'))
            return [request]
        return []

    def read_message(self, deadline):
        while time.monotonic() < deadline:
            if self.closed:
                raise dbus.DBusError('closed')
            if self.messages:
                return self.messages.popleft()
            time.sleep(0.001)
        raise dbus.DBusTimeout('expired')

    def close(self):
        self.closed = True

    def abort(self):
        self.closed = True


def test_shortcut_session_closes_and_ignores_foreign_activation():
    bus = PortalBus()
    fired = threading.Event()
    session = StopShortcutSession(_bus_factory=lambda: bus)
    session.start(fired.set)
    assert session.wait_ready(2)
    bus.messages.append(signal('/org/freedesktop/portal/desktop', 'Activated', ['/foreign', 'autocontrol-stop', 1, {}]))
    assert not fired.wait(0.05)
    bus.messages.append(signal('/org/freedesktop/portal/desktop', 'Activated',
                               [bus.session, 'autocontrol-stop', 1, {}]))
    assert fired.wait(2)
    session.close()
    assert bus.closed and session.state == 'closed'
    assert any(call[:2] == ('Close', bus.session) for call in bus.calls)


def test_shortcut_refusal_stops_without_repeated_authorization():
    bus = PortalBus(refused=True)
    session = StopShortcutSession(_bus_factory=lambda: bus)
    session.start(lambda: pytest.fail('refused shortcut fired'))
    with pytest.raises(ShortcutUnavailable) as error:
        session.wait_ready(2)
    assert error.value.state == 'needs_permission'
    assert error.value.has_recovery_instruction
    assert len([item for item in bus.calls if item[0] == 'CreateSession']) == 1
    session.close()
    assert bus.closed


def test_close_cancels_pending_bind_request():
    bus = PortalBus(pending=True)
    session = StopShortcutSession(_bus_factory=lambda: bus)
    session.start(lambda: pytest.fail('cancelled shortcut fired'))
    assert bus.bind_requested.wait(2)
    session.close()
    assert bus.closed and session.state == 'closed'
    requests = [item for item in bus.calls if item[0] == 'Close' and '/request/' in item[1]]
    assert len(requests) == 1


def test_held_shortcut_fires_once_until_deactivated():
    bus = PortalBus()
    fired = []
    session = StopShortcutSession(_bus_factory=lambda: bus)
    session.start(lambda: fired.append(True))
    assert session.wait_ready(2)
    for member in ['Activated', 'Activated', 'Deactivated', 'Activated']:
        bus.messages.append(signal('/org/freedesktop/portal/desktop', member,
                                   [bus.session, 'autocontrol-stop', 1, {}]))
    deadline = time.monotonic() + 2
    while bus.messages and time.monotonic() < deadline:
        time.sleep(0.001)
    session.close()
    assert fired == [True, True]


def test_revoked_grant_stops_control_and_retains_permission_failure():
    bus = PortalBus()
    stopped = threading.Event()
    session = StopShortcutSession(_bus_factory=lambda: bus)
    session.start(stopped.set)
    assert session.wait_ready(2)
    bus.messages.append(signal(bus.session, 'Closed', [], 'org.freedesktop.portal.Session'))
    assert stopped.wait(2)
    with pytest.raises(ShortcutUnavailable, match='revoked'):
        session.wait_ready(2)
    session.close()


def test_callback_failure_is_not_replayed():
    bus = PortalBus()
    invoked = []

    def stop():
        invoked.append(True)
        raise RuntimeError('controlled failure')

    session = StopShortcutSession(_bus_factory=lambda: bus)
    session.start(stop)
    assert session.wait_ready(2)
    bus.messages.append(signal('/org/freedesktop/portal/desktop', 'Activated',
                               [bus.session, 'autocontrol-stop', 1, {}]))
    deadline = time.monotonic() + 2
    while not bus.closed and time.monotonic() < deadline:
        time.sleep(0.001)
    assert invoked == [True]
    assert session.error is not None and 'callback failed' in session.error.reason
    session.close()


def test_reentrant_close_cannot_replace_live_session():
    bus = PortalBus()
    finished = threading.Event()
    rejected = []
    session = StopShortcutSession(_bus_factory=lambda: bus)

    def stop():
        session.close()
        try:
            session.start(lambda: None)
        except ShortcutUnavailable:
            rejected.append(True)
        finished.set()

    session.start(stop)
    assert session.wait_ready(2)
    bus.messages.append(signal('/org/freedesktop/portal/desktop', 'Activated',
                               [bus.session, 'autocontrol-stop', 1, {}]))
    assert finished.wait(2)
    session.close()
    assert rejected == [True]
    assert len([item for item in bus.calls if item[:2] == ('Close', bus.session)]) == 1


def test_unanswered_bind_times_out_and_closes_request(monkeypatch):
    from je_auto_control.linux_wayland import global_shortcuts

    monkeypatch.setattr(global_shortcuts, '_REQUEST_SECONDS', 0.05)
    bus = PortalBus(pending=True)
    session = StopShortcutSession(_bus_factory=lambda: bus)
    session.start(lambda: pytest.fail('timed out shortcut fired'))
    with pytest.raises(ShortcutUnavailable, match='timed out'):
        session.wait_ready(2)
    session.close()
    assert any(item[0] == 'Close' and '/request/' in item[1] for item in bus.calls)


def test_activation_queued_around_bind_response_is_preserved():
    class EarlyPortal(PortalBus):
        def call(self, destination, path, interface, member, signature, body, timeout=25):
            response = super().call(destination, path, interface, member, signature, body, timeout)
            if member == 'BindShortcuts':
                self._queued.insert(0, signal('/org/freedesktop/portal/desktop', 'Activated',
                                             [self.session, 'autocontrol-stop', 1, {}]))
            return response

    bus = EarlyPortal()
    fired = threading.Event()
    session = StopShortcutSession(_bus_factory=lambda: bus)
    session.start(fired.set)
    assert session.wait_ready(2)
    assert fired.wait(2)
    session.close()


@pytest.mark.parametrize('pending', [False, True])
def test_portal_name_loss_revokes_active_or_pending_shortcut(pending):
    bus = PortalBus(pending=pending)
    stopped = threading.Event()
    session = StopShortcutSession(_bus_factory=lambda: bus)
    session.start(stopped.set)
    try:
        assert bus.bind_requested.wait(2)
        if not pending:
            assert session.wait_ready(2)
        lost = signal('/org/freedesktop/DBus', 'NameOwnerChanged',
                      ['org.freedesktop.portal.Desktop', ':1.42', ''], 'org.freedesktop.DBus')
        lost.fields[dbus.FIELD_SENDER] = 'org.freedesktop.DBus'
        bus.messages.append(lost)
        if not pending:
            assert stopped.wait(2), 'portal owner disappeared but the owned stop grant remained available'
        with pytest.raises(ShortcutUnavailable, match='revoked'):
            assert session.wait_ready(2)
        assert session.state == 'needs_permission'
        assert stopped.is_set() is not pending
    finally:
        session.close()


@pytest.mark.parametrize('sender,name,new_owner', [
    (':1.99', 'org.freedesktop.portal.Desktop', ''),
    ('org.freedesktop.DBus', 'org.other.Portal', ''),
    ('org.freedesktop.DBus', 'org.freedesktop.portal.Desktop', ':1.42'),
])
def test_foreign_or_unchanged_bus_owner_does_not_revoke_grant(sender, name, new_owner):
    bus = PortalBus()
    fired = []
    session = StopShortcutSession(_bus_factory=lambda: bus)
    session.start(lambda: fired.append(True))
    try:
        assert session.wait_ready(2)
        message = signal('/org/freedesktop/DBus', 'NameOwnerChanged', [name, ':1.42', new_owner],
                         'org.freedesktop.DBus')
        message.fields[dbus.FIELD_SENDER] = sender
        bus.messages.append(message)
        bus.messages.append(signal('/org/freedesktop/portal/desktop', 'Activated',
                                   [bus.session, 'autocontrol-stop', 1, {}]))
        deadline = time.monotonic() + 2
        while not fired and time.monotonic() < deadline:
            time.sleep(0.001)
        assert fired == [True] and session.state == 'available' and session.error is None
    finally:
        session.close()
