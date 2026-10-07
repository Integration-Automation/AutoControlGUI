"""Owned GlobalShortcuts stop sessions on a single cancellable portal connection.

Registration is explicit and may show the compositor's shortcut consent dialog.
This is a stop shortcut, not a global key-state query or input recording hook.
The compositor may change the preferred trigger; expose its actual description.
"""
from __future__ import annotations

import atexit
from dataclasses import dataclass
import math
import re
import threading
import time
from typing import Any, Callable, Optional
import uuid

from je_auto_control.linux_wayland import _dbus_client as dbus
from je_auto_control.linux_wayland.portal import PORTAL_BUS, PORTAL_PATH, REQUEST_INTERFACE
from je_auto_control.utils.exception.exceptions import AutoControlException


_INTERFACE = 'org.freedesktop.portal.GlobalShortcuts'
_SESSION_INTERFACE = 'org.freedesktop.portal.Session'
_DBUS_INTERFACE = 'org.freedesktop.DBus'
_OWNER_RULE = ("type='signal',sender='org.freedesktop.DBus',path='/org/freedesktop/DBus',"
               "interface='org.freedesktop.DBus',member='NameOwnerChanged',"
               f"arg0='{PORTAL_BUS}'")
_SHORTCUT_ID = 'autocontrol-stop'
_REQUEST_SECONDS = 30.0
_POLL_SECONDS = 0.1
_CLOSE_SECONDS = 0.5
_MAX_PENDING = 32


class ShortcutUnavailable(AutoControlException):
    """A stop shortcut has no usable portal grant; GUI Stop remains available."""

    capability = 'global_stop'
    has_recovery_instruction = True

    def __init__(self, reason: str, *, state: str = 'unsupported') -> None:
        self.state = state
        self.reason = reason
        self.recovery = ('Use GUI Actions > Diagnostics > Stop input control, or the caller-owned stop event. '
                         'Close this shortcut session before explicitly retrying authorization on a supported portal.')
        super().__init__(f'{reason}. {self.recovery}')


@dataclass
class _Runtime:
    bus: Optional[dbus.SessionBus] = None
    thread: Optional[threading.Thread] = None
    session: str = ''
    state: str = 'closed'
    error: Optional[ShortcutUnavailable] = None
    trigger: str = ''
    pressed: bool = False


def _path(value: Any) -> str:
    if not isinstance(value, str) or re.fullmatch(r'/[A-Za-z0-9_/]+', value) is None:
        raise ShortcutUnavailable('portal returned an invalid object path')
    return value


def _rule(path: str, interface: str) -> str:
    return f"type='signal',sender='{PORTAL_BUS}',path='{path}',interface='{interface}'"


def _is_response(message: dbus.Message, paths: set[str]) -> bool:
    return (message.type == dbus.SIGNAL and message.path in paths
            and message.interface == REQUEST_INTERFACE and message.member == 'Response')


def _response_result(message: dbus.Message) -> dict[str, Any]:
    if len(message.body) != 2 or not isinstance(message.body[1], dict):
        raise ShortcutUnavailable('portal returned an invalid shortcut response')
    if message.body[0] != 0:
        raise ShortcutUnavailable('stop shortcut authorization was refused or cancelled', state='needs_permission')
    return message.body[1]


def _valid_text(value: str, limit: int, *, allow_empty: bool = False) -> bool:
    return isinstance(value, str) and (bool(value) or allow_empty) and len(value) <= limit and '\x00' not in value


def _owner_lost(message: dbus.Message) -> bool:
    return (message.path == '/org/freedesktop/DBus' and message.interface == _DBUS_INTERFACE
            and message.member == 'NameOwnerChanged' and message.fields.get(dbus.FIELD_SENDER) == _DBUS_INTERFACE
            and len(message.body) == 3 and message.body[0] == PORTAL_BUS
            and bool(message.body[1]) and message.body[1] != message.body[2])


class StopShortcutSession:
    """Register one stop shortcut asynchronously and release only its own grant.

    The callback runs on the session worker and should only signal cancellation
    or stop input control. Closing prevents subsequent callbacks, cancels an
    unanswered request and joins the worker. A failed start is not retried until
    explicit close/start. No portal request occurs merely by constructing this.
    """

    def __init__(self, *, _bus_factory: Optional[Callable[[], dbus.SessionBus]] = None) -> None:
        self._factory = _bus_factory if _bus_factory is not None else dbus.SessionBus
        self._live = _Runtime()
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._ready = threading.Event()
        self._callback: Callable[[], None] = lambda: None
        self._pending: list[dbus.Message] = []

    @property
    def state(self) -> str:
        """Return local registration evidence, independent of input permission."""
        with self._lock:
            return self._live.state

    @property
    def error(self) -> Optional[ShortcutUnavailable]:
        """Return the retained grant/connection failure, if any."""
        with self._lock:
            return self._live.error

    @property
    def trigger_description(self) -> str:
        """Describe the compositor's actual binding, which may differ from the preference."""
        with self._lock:
            return self._live.trigger

    def start(self, on_stop: Callable[[], None], *, preferred_trigger: str = 'F7', parent_window: str = '') -> None:
        """Explicitly request registration; UI consent never blocks the caller thread."""
        if not callable(on_stop) or not _valid_text(preferred_trigger, 128):
            raise ShortcutUnavailable('choose a nonempty preferred shortcut and a stop callback')
        if not _valid_text(parent_window, 256, allow_empty=True):
            raise ShortcutUnavailable('parent window must be bounded text without NUL')
        with self._lock:
            if self._live.thread is not None:
                raise ShortcutUnavailable('close the previous stop shortcut before starting another')
            self._stop.clear()
            self._ready.clear()
            self._pending.clear()
            self._live = _Runtime(state='needs_permission')
            self._callback = on_stop
            worker = threading.Thread(target=self._run, args=(preferred_trigger, parent_window),
                                      name='autocontrol-stop-shortcut', daemon=True)
            self._live.thread = worker
            try:
                worker.start()
            except BaseException:  # reason: an unstarted worker must not prevent a subsequent explicit retry
                self._live.thread = None
                self._live.state = 'closed'
                raise
            atexit.register(self.close)

    def wait_ready(self, timeout: float = _REQUEST_SECONDS) -> bool:
        """Wait for grant/refusal with a deadline; raise the retained typed failure."""
        if not math.isfinite(timeout) or timeout < 0:
            raise ShortcutUnavailable('shortcut wait timeout must be finite and nonnegative')
        if not self._ready.wait(timeout):
            return False
        with self._lock:
            if self._live.error is not None:
                raise self._live.error
            return self._live.state == 'available'

    def _run(self, preferred: str, parent: str) -> None:
        bus: Optional[dbus.SessionBus] = None
        try:
            bus = self._factory()
            with self._lock:
                self._live.bus = bus
            if self._stop.is_set():
                return
            bus.connect()
            bus.add_match(_OWNER_RULE)
            self._negotiate(bus, preferred, parent)
            with self._lock:
                if not self._stop.is_set():
                    self._live.state = 'available'
            self._ready.set()
            self._listen(bus)
        except ShortcutUnavailable as failure:
            self._failed(failure)
        except dbus.DBusError as failure:
            self._failed(ShortcutUnavailable(f'GlobalShortcuts portal connection failed: {failure}',
                                            state='needs_dependency'))
        # pylint: disable-next=broad-exception-caught  # reason: worker failures must revoke this owned stop registration
        except Exception as failure:  # reason: callback/protocol failures cannot leave a falsely available stop session
            self._failed(ShortcutUnavailable(f'stop shortcut worker failed: {type(failure).__name__}'))
        finally:
            if bus is not None:
                self._close_session(bus)
                bus.close()
            with self._lock:
                self._live.bus = None
                if self._stop.is_set():
                    self._live.state = 'closed'
            self._ready.set()

    def _failed(self, failure: ShortcutUnavailable) -> None:
        with self._lock:
            if self._stop.is_set():
                return
            lost_grant = self._live.state == 'available'
            self._live.error = failure
            self._live.state = failure.state
        if lost_grant:
            try:
                self._invoke_stop()
            except ShortcutUnavailable as callback_failure:
                with self._lock:
                    self._live.error = callback_failure
                    self._live.state = callback_failure.state

    def _invoke_stop(self) -> None:
        with self._lock:
            if self._stop.is_set():
                return
            callback = self._callback
        try:
            callback()
        # pylint: disable-next=broad-exception-caught  # reason: a failed user stop callback must not be retried
        except Exception as failure:  # reason: report callback failure and close its grant without invoking it twice
            error = ShortcutUnavailable(f'stop callback failed: {type(failure).__name__}')
            with self._lock:
                self._live.error = error
                self._live.state = error.state
            raise error from failure

    def _negotiate(self, bus: dbus.SessionBus, preferred: str, parent: str) -> None:
        token = 'ac_' + uuid.uuid4().hex
        self._live.session = f'/org/freedesktop/portal/desktop/session/{bus.sender_token}/{token}'
        options = {'session_handle_token': dbus.Variant('s', token)}
        result = self._request(bus, 'CreateSession', 'a{sv}', [options])
        self._live.session = _path(result.get('session_handle'))
        bus.add_match(_rule(PORTAL_PATH, _INTERFACE))
        bus.add_match(_rule(self._live.session, _SESSION_INTERFACE))
        shortcuts = [(_SHORTCUT_ID, {'description': dbus.Variant('s', 'Stop AutoControl input control'),
                                  'preferred_trigger': dbus.Variant('s', preferred)})]
        result = self._request(bus, 'BindShortcuts', 'oa(sa{sv})sa{sv}',
                               [self._live.session, shortcuts, parent, {}])
        bindings = result.get('shortcuts', [])
        for identifier, properties in bindings:
            if identifier == _SHORTCUT_ID:
                self._live.trigger = str(properties.get('trigger_description', ''))
                return
        raise ShortcutUnavailable('portal did not bind the requested stop shortcut', state='needs_permission')

    def _request(self, bus: dbus.SessionBus, member: str, signature: str, body: list[Any]) -> dict[str, Any]:
        token = 'ac_' + uuid.uuid4().hex
        options = body[-1]
        options['handle_token'] = dbus.Variant('s', token)
        predicted = f'/org/freedesktop/portal/desktop/request/{bus.sender_token}/{token}'
        bus.add_match(_rule(predicted, REQUEST_INTERFACE))
        handle = predicted
        try:
            response = bus.call(PORTAL_BUS, PORTAL_PATH, _INTERFACE, member, signature, body,
                                timeout=_REQUEST_SECONDS)
            handle = _path(response[0]) if response else predicted
            if handle != predicted:
                bus.add_match(_rule(handle, REQUEST_INTERFACE))
            return self._response(bus, {predicted, handle})
        except (dbus.DBusError, ShortcutUnavailable):
            try:
                bus.call(PORTAL_BUS, handle, REQUEST_INTERFACE, 'Close', '', [], timeout=_CLOSE_SECONDS)
            except dbus.DBusError:
                # Dropping the private connection below also revokes its requests/sessions.
                pass
            raise

    def _response(self, bus: dbus.SessionBus, paths: set[str]) -> dict[str, Any]:
        deadline = time.monotonic() + _REQUEST_SECONDS
        queued = bus.take_pending_messages()
        while not self._stop.is_set() and time.monotonic() < deadline:
            if queued:
                message = queued.pop(0)
            else:
                try:
                    message = bus.read_message(min(deadline, time.monotonic() + _POLL_SECONDS))
                except dbus.DBusTimeout:
                    continue
            if self._is_revocation(message):
                raise ShortcutUnavailable('stop shortcut grant was revoked', state='needs_permission')
            if _is_response(message, paths):
                # Signals after the Response retain their order for the active listener.
                for pending in queued:
                    self._defer(pending)
                return _response_result(message)
            self._defer(message)
        raise ShortcutUnavailable('stop shortcut request was cancelled or timed out', state='needs_permission')

    def _defer(self, message: dbus.Message) -> None:
        if message.interface not in (_INTERFACE, _SESSION_INTERFACE, _DBUS_INTERFACE):
            return
        if len(self._pending) >= _MAX_PENDING:
            raise ShortcutUnavailable('stop shortcut pending signal budget exceeded')
        self._pending.append(message)

    def _listen(self, bus: dbus.SessionBus) -> None:
        for pending in bus.take_pending_messages():
            self._defer(pending)
        while not self._stop.is_set():
            if self._pending:
                message = self._pending.pop(0)
            else:
                try:
                    message = bus.read_message(time.monotonic() + _POLL_SECONDS)
                except dbus.DBusTimeout:
                    continue
            self._dispatch(message)

    def _dispatch(self, message: dbus.Message) -> None:
        if message.type != dbus.SIGNAL:
            return
        if self._is_revocation(message):
            raise ShortcutUnavailable('stop shortcut grant was revoked', state='needs_permission')
        if not self._is_own_shortcut(message):
            return
        with self._lock:
            if self._stop.is_set():
                return
            if message.member == 'Deactivated':
                self._live.pressed = False
            elif message.member == 'Activated' and not self._live.pressed:
                self._live.pressed = True
            else:
                return
        if message.member == 'Activated':
            self._invoke_stop()

    def _is_revocation(self, message: dbus.Message) -> bool:
        return (message.type == dbus.SIGNAL and
                (_owner_lost(message) or (message.path == self._live.session
                                         and message.interface == _SESSION_INTERFACE
                                         and message.member == 'Closed')))

    def _is_own_shortcut(self, message: dbus.Message) -> bool:
        return (message.path == PORTAL_PATH and message.interface == _INTERFACE
                and len(message.body) == 4 and message.body[:2] == [self._live.session, _SHORTCUT_ID])

    def _close_session(self, bus: dbus.SessionBus) -> None:
        if not self._live.session:
            return
        try:
            bus.call(PORTAL_BUS, self._live.session, _SESSION_INTERFACE, 'Close', '', [], timeout=_CLOSE_SECONDS)
        except dbus.DBusError:
            # A closed bus revokes its owned session; retain any earlier failure.
            pass

    def close(self) -> None:
        """Cancel, release the owned grant and join; retain cleanup for retry if blocked."""
        with self._lock:
            self._stop.set()
            worker = self._live.thread
        if worker is threading.current_thread():
            # This worker still owns its grant until its finally block finishes.
            # Retain it so reentrant close/start cannot replace another session.
            return
        if worker is not None and worker is not threading.current_thread():
            worker.join(1.0)
            if worker.is_alive():
                with self._lock:
                    bus = self._live.bus
                if bus is not None:
                    bus.abort()
                worker.join(1.0)
            if worker.is_alive():
                error = ShortcutUnavailable('stop shortcut worker has not stopped; retry cleanup')
                with self._lock:
                    self._live.state = error.state
                    self._live.error = error
                raise error
        with self._lock:
            self._live.thread = None
            self._live.state = 'closed'
        atexit.unregister(self.close)
