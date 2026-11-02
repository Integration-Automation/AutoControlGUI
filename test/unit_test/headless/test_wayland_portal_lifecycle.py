"""Abandoned screenshot requests close on their own bus, within a complete D-Bus call budget."""
import asyncio
from concurrent.futures import CancelledError
from threading import Event, Thread
import socket
from types import SimpleNamespace

import pytest

from headless.test_wayland_capture_tiers import _FakeBus, _with_bus
from je_auto_control.linux_wayland import portal
from je_auto_control.utils.dbus_client import session_bus
from je_auto_control.utils.exception.control_signals import OperationCancelledError
from je_auto_control.utils.exception.exceptions import AutoControlScreenException


class PendingBus(_FakeBus):
    def __init__(self, failure=None, *, handle=None, close_failure=None, phase='wait', body=None):
        super().__init__(body=body, handle=handle, error=failure)
        self.failure, self.close_failure, self.phase = failure, close_failure, phase
        self.requests = []

    def call(self, destination, path, interface, member, signature, body, timeout=None):
        self.requests.append((path, interface, member, timeout))
        if member == 'Close':
            self.events.append('request-close')
            if self.close_failure:
                raise self.close_failure
            return []
        if self.phase == 'reply':
            raise self.failure
        return super().call(destination, path, interface, member, signature, body, timeout)

    def add_match(self, rule):
        if self.phase == 'subscribe' or (self.phase == 'alternate' and self.rules):
            raise self.failure
        super().add_match(rule)

    @property
    def closes(self):
        return [call for call in self.requests if call[2] == 'Close']


@pytest.mark.parametrize('phase', ['wait', 'reply', 'alternate'])
def test_abandoned_portal_request_is_closed_before_its_bus_connection(phase):
    error = session_bus.DBusError('controlled missing reply')
    actual = portal.PORTAL_PATH + '/request/1_9/alternate'
    bus = PendingBus(error, phase=phase, handle=actual if phase != 'reply' else None)
    with _with_bus(bus), pytest.raises(AutoControlScreenException):
        portal.capture_png(timeout=0.02)
    assert len(bus.closes) == 1, 'the remote consent request was left open'
    path, interface, _method, budget = bus.closes[0]
    assert path == (actual if phase != 'reply' else bus.rules[0].split("path='")[1].split("'")[0])
    assert interface == portal.REQUEST_INTERFACE and 0 < budget <= 0.5
    assert bus.events[-2:] == ['request-close', 'close']


@pytest.mark.parametrize('original', [KeyboardInterrupt(), SystemExit(7), GeneratorExit(), asyncio.CancelledError(),
                                      CancelledError(), OperationCancelledError('capture')],
                         ids=lambda value: type(value).__name__)
@pytest.mark.parametrize('wrapped', [False, True])
@pytest.mark.parametrize('cleanup_fails', [False, True])
def test_original_capture_controls_survive_request_cleanup(original, wrapped, cleanup_fails):
    failure = session_bus.DBusError('capture wrapper') if wrapped else original
    if wrapped:
        failure.__cause__ = original
    bus = PendingBus(failure, close_failure=session_bus.DBusError('close failed') if cleanup_fails else None)
    with _with_bus(bus), pytest.raises(type(original)) as caught:
        portal.capture_png(timeout=0.02)
    assert caught.value is original
    assert len(bus.closes) == 1 and bus.events[-1] == 'close'


def test_subscription_failure_preserves_wrapped_control_without_creating_or_closing_a_request():
    original = OperationCancelledError('subscribe')
    failure = session_bus.DBusError('subscription wrapper')
    failure.__cause__ = original
    bus = PendingBus(failure, phase='subscribe')
    with _with_bus(bus), pytest.raises(OperationCancelledError) as caught:
        portal.capture_png(timeout=0.02)
    assert caught.value is original and bus.requests == []


def test_cleanup_control_outweighs_an_ordinary_timeout():
    original = OperationCancelledError('close')
    bus = PendingBus(session_bus.DBusError('timeout'), close_failure=original)
    with _with_bus(bus), pytest.raises(OperationCancelledError) as caught:
        portal.capture_png(timeout=0.02)
    assert caught.value is original and len(bus.closes) == 1


def test_original_control_outweighs_a_second_control_during_request_cleanup():
    original = OperationCancelledError('primary capture')
    bus = PendingBus(original, close_failure=SystemExit(9))
    with _with_bus(bus), pytest.raises(OperationCancelledError) as caught:
        portal.capture_png(timeout=0.02)
    assert caught.value is original and len(bus.closes) == 1


@pytest.mark.parametrize('response', [0, 1, 2])
def test_completed_portal_response_does_not_close_an_already_ended_request(monkeypatch, response):
    bus = PendingBus(body=[response, {'uri': 'file:///controlled.png'}])
    monkeypatch.setattr(portal, '_read_and_discard', lambda _path: b'controlled bytes')
    with _with_bus(bus):
        if response:
            with pytest.raises(AutoControlScreenException):
                portal.capture_png(timeout=0.02)
        else:
            assert portal.capture_png(timeout=0.02) == b'controlled bytes'
    assert bus.closes == [] and bus.events[-1] == 'close'


def test_dbus_call_timeout_includes_a_blocked_write_to_an_unresponsive_peer():
    sender, peer = socket.socketpair()
    finished = Event()
    errors = []
    timely = False
    worker = None
    bus = session_bus.SessionBus(address='unused')
    bus._socket = sender
    try:
        sender.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 4096)
        peer.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4096)
        sender.setblocking(False)
        while True:
            try:
                sender.send(b'x' * 4096)
            except BlockingIOError:
                break
        sender.settimeout(None)

        def close_request():
            try:
                bus.call(portal.PORTAL_BUS, '/controlled', portal.REQUEST_INTERFACE, 'Close', '', [], timeout=0.05)
            except BaseException as error:
                errors.append(error)
            finally:
                finished.set()

        worker = Thread(target=close_request)
        worker.start()
        timely = finished.wait(1)
    finally:
        peer.close()
        sender.close()
        if worker is not None:
            worker.join(2)
    assert timely, 'the D-Bus timeout did not bound its write'
    assert not worker.is_alive() and len(errors) == 1 and isinstance(errors[0], session_bus.DBusError)


def test_dbus_reply_uses_the_remaining_budget_after_sending(monkeypatch):
    now = [100.0]
    deadlines = []
    bus = session_bus.SessionBus(address='unused')

    def send(*_args):
        now[0] += 0.2
        return 1

    def read(deadline):
        deadlines.append(deadline)
        return type('Reply', (), {'reply_serial': 1, 'type': session_bus.METHOD_RETURN, 'body': []})()

    monkeypatch.setattr(session_bus, 'time', SimpleNamespace(monotonic=lambda: now[0]))
    monkeypatch.setattr(bus, 'send', send)
    monkeypatch.setattr(bus, 'read_message', read)
    assert bus.call('controlled', '/controlled', 'controlled', 'Close', '', [], timeout=1) == []
    assert deadlines == [101.0], 'sending incorrectly reset the reply deadline'


def test_timeout_configuration_retains_the_original_control_from_a_transport_wrapper():
    original = OperationCancelledError('transport configuration')
    failure = OSError('socket wrapper')
    failure.__cause__ = original

    def interrupted(_timeout):
        raise failure

    bus = session_bus.SessionBus(address='unused')
    bus._socket = SimpleNamespace(settimeout=interrupted)
    with pytest.raises(OperationCancelledError) as caught:
        bus.call('controlled', '/controlled', 'controlled', 'Close', '', [], timeout=1)
    assert caught.value is original


@pytest.mark.parametrize('phase', ['connect', 'authenticate', 'hello'])
@pytest.mark.parametrize('original', [KeyboardInterrupt(), SystemExit(7), GeneratorExit(), asyncio.CancelledError(),
                                      CancelledError(), OperationCancelledError('open bus')],
                         ids=lambda value: type(value).__name__)
def test_cancellation_during_bus_open_closes_the_actual_owned_descriptor(monkeypatch, phase, original):
    sender, peer = socket.socketpair()

    class OwnedSocket:
        def settimeout(self, timeout):
            sender.settimeout(timeout)

        def connect(self, _address):
            if phase == 'connect':
                raise original

        def close(self):
            sender.close()

    def authenticate():
        if phase == 'authenticate':
            raise original

    def hello(*_args, **_kwargs):
        raise original

    owned = OwnedSocket()
    fake_socket = SimpleNamespace(AF_UNIX=getattr(socket, 'AF_UNIX', socket.AF_INET),
                                  SOCK_STREAM=socket.SOCK_STREAM, socket=lambda *_args: owned)
    bus = session_bus.SessionBus(address='unix:path=/controlled')
    monkeypatch.setattr(session_bus, 'socket', fake_socket)
    monkeypatch.setattr(bus, '_authenticate', authenticate)
    monkeypatch.setattr(bus, 'call', hello)
    try:
        with pytest.raises(type(original)) as caught:
            bus.__enter__()
        assert caught.value is original
        assert sender.fileno() == -1 and bus._socket is None, 'a failed __enter__ left its actual descriptor open'
    finally:
        sender.close()
        peer.close()


def test_partial_connection_clears_ownership_before_a_second_cleanup_control(monkeypatch):
    sender, peer = socket.socketpair()
    original = OperationCancelledError('opening')

    def cleanup():
        sender.close()
        raise SystemExit(9)

    bus = session_bus.SessionBus(address='unused')
    bus._socket = SimpleNamespace(close=cleanup)
    try:
        with pytest.raises(OperationCancelledError) as caught:
            bus._close_failed_open(original)
        assert caught.value is original and sender.fileno() == -1
        assert bus._socket is None, 'interrupted close retained ownership of an already retired descriptor'
    finally:
        sender.close()
        peer.close()
