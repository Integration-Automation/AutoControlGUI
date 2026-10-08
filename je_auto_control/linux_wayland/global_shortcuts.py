"""A global "stop" key on Wayland, through the GlobalShortcuts portal.

Every other backend stops a runaway script by polling the keyboard: the
critical-exit watcher asks "is F7 down?" on a timer. Wayland will not answer
that question — ``listener.check_key_is_press`` reports ``False`` forever —
so on Wayland the panic key is inert, and a script that has taken the pointer
can only be stopped from the GUI or by killing the process.

``org.freedesktop.portal.GlobalShortcuts`` is the supported way to get one key
back. The application registers a *named* shortcut; the compositor shows the
user what is being asked for, lets them choose the key, and from then on
delivers an ``Activated`` signal when it is pressed. That is all it does and
all this module asks of it: one shortcut, named ``stop``. It is not a key
logger and cannot be made into one — the application never learns about any
key it did not register, which is the point.

**A session has to be closed.** The registration lives as long as the portal
session does, and the session lives as long as the D-Bus connection — so
:meth:`StopShortcutSession.close` both asks the portal to end the session and
drops the connection, and is safe to call from any thread, twice.

Where the portal has no GlobalShortcuts (it is newer than RemoteDesktop and
not every desktop ships it) or the user declines, the caller gets a
:class:`ShortcutUnavailable` whose ``recovery`` names the stop methods that
still work. Nothing here falls back to reading devices.
"""
from __future__ import annotations

import threading
from typing import Any, Callable, Dict, List, Optional

from je_auto_control.linux_wayland import _dbus_client
from je_auto_control.linux_wayland.portal import (
    PORTAL_BUS, PORTAL_PATH, REQUEST_INTERFACE, _handle_token, _match_rule,
    _request_path,
)
from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils.logging.logging_instance import autocontrol_logger

SHORTCUTS_INTERFACE = "org.freedesktop.portal.GlobalShortcuts"
SESSION_INTERFACE = "org.freedesktop.portal.Session"
STOP_SHORTCUT_ID = "stop"

#: The consent dialog is a human in the loop, so this is a human-scale wait.
DEFAULT_TIMEOUT = 30.0
_CALL_TIMEOUT = 10.0

STOP_RECOVERY = (
    "A running script can still be stopped from the GUI's stop control "
    "(Actions menu) or by ending the process. To get a stop key, allow the "
    "shortcut when the desktop asks, or bind one to the stop command in your "
    "desktop's keyboard settings.")

_ACTIVATED_RULE = (f"type='signal',sender='{PORTAL_BUS}',"
                   f"interface='{SHORTCUTS_INTERFACE}',member='Activated'")


class ShortcutUnavailable(AutoControlException):
    """No stop shortcut could be registered; ``recovery`` says what still works."""

    def __init__(self, message: str) -> None:
        self.recovery = STOP_RECOVERY
        super().__init__(f"{message}. {STOP_RECOVERY}")

    @property
    def has_recovery_instruction(self) -> bool:
        """Whether the error tells the operator what to do next."""
        return bool(self.recovery)


class ShortcutPermissionError(ShortcutUnavailable):
    """The user, or the desktop on their behalf, declined the shortcut."""


class StopShortcutSession:
    """One registered stop shortcut, alive until :meth:`close`.

    :param on_stop: called, on the session's own thread, each time the
        shortcut is pressed. Keep it short: set an event, do not do the work.
    :param bus_factory: returns a connected session bus; injected by tests.
    :param preferred_trigger: a hint such as ``"CTRL+ALT+F12"``. The desktop
        may ignore it and the user may change it; it is never a guarantee.
    """

    def __init__(self, on_stop: Callable[[], None], *,
                 bus_factory: Optional[Callable[[], Any]] = None,
                 preferred_trigger: Optional[str] = None,
                 poll_s: float = 0.25) -> None:
        self._on_stop = on_stop
        self._bus_factory = bus_factory or _connected_bus
        self._trigger = preferred_trigger
        self._poll_s = max(0.01, float(poll_s))
        self._bus: Any = None
        self._session_handle = ""
        self._closing = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

    @property
    def is_open(self) -> bool:
        """Whether the shortcut is registered and the session is live."""
        return bool(self._session_handle) and not self._closing.is_set()

    def __enter__(self) -> "StopShortcutSession":
        self.open()
        return self

    def __exit__(self, *_exception: Any) -> None:
        self.close()

    def open(self, timeout: float = DEFAULT_TIMEOUT) -> None:
        """Create the portal session and register the stop shortcut.

        :param timeout: seconds to wait for each portal answer, including the
            time the user spends on the dialog.
        :raises ShortcutPermissionError: the request was declined.
        :raises ShortcutUnavailable: no portal, no GlobalShortcuts interface,
            or no answer in time.
        """
        if self._session_handle:
            return
        self._closing.clear()
        try:
            self._bus = self._bus_factory()
            self._session_handle = self._create_session(timeout)
            self._bind(timeout)
            self._bus.add_match(_ACTIVATED_RULE)
        except _dbus_client.DBusError as error:
            self.close()
            raise ShortcutUnavailable(
                f"the GlobalShortcuts portal could not be used: {error}",
            ) from error
        except BaseException:
            self.close()
            raise

    def wait(self, timeout: float) -> bool:
        """Wait up to ``timeout`` seconds for one press; True if it came.

        ``on_stop`` has already been called when this returns True.
        """
        if not self.is_open:
            return False
        try:
            body = self._bus.wait_for_signal(
                [PORTAL_PATH], SHORTCUTS_INTERFACE, "Activated", timeout)
        except _dbus_client.DBusError as error:
            if not _is_timeout(error):
                autocontrol_logger.warning(
                    "stop shortcut: the portal connection ended: %s", error)
                self._closing.set()
            return False
        if not _is_our_stop(body, self._session_handle):
            return False
        self._on_stop()
        return True

    def start(self) -> None:
        """Listen on a background thread until :meth:`close`."""
        if self._thread is not None or not self.is_open:
            return
        self._thread = threading.Thread(
            target=self._listen, name="wayland-stop-shortcut", daemon=True)
        self._thread.start()

    def close(self) -> None:
        """End the portal session and drop the connection. Idempotent."""
        self._closing.set()
        thread, self._thread = self._thread, None
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=self._poll_s + _CALL_TIMEOUT)
        with self._lock:
            bus, self._bus = self._bus, None
            handle, self._session_handle = self._session_handle, ""
        if bus is None:
            return
        if handle:
            try:
                bus.call(PORTAL_BUS, handle, SESSION_INTERFACE, "Close", "",
                         [], timeout=_CALL_TIMEOUT)
            except _dbus_client.DBusError as error:
                # Dropping the connection below ends the session regardless.
                autocontrol_logger.info(
                    "stop shortcut: Session.Close failed: %s", error)
        bus.close()

    # --- the portal conversation ------------------------------------------

    def _listen(self) -> None:
        while not self._closing.is_set():
            self.wait(self._poll_s)

    def _create_session(self, timeout: float) -> str:
        token = _handle_token()
        options = {
            "handle_token": _dbus_client.Variant("s", token),
            "session_handle_token": _dbus_client.Variant("s", token + "_s"),
        }
        results = self._request("CreateSession", "a{sv}", [options], token,
                                timeout)
        handle = str(results.get("session_handle", ""))
        if not handle:
            raise ShortcutUnavailable(
                "the portal created a session but returned no handle")
        return handle

    def _bind(self, timeout: float) -> None:
        token = _handle_token()
        shortcut: Dict[str, Any] = {
            "description": _dbus_client.Variant(
                "s", "Stop the running AutoControl script"),
        }
        if self._trigger:
            shortcut["preferred_trigger"] = _dbus_client.Variant(
                "s", self._trigger)
        options = {"handle_token": _dbus_client.Variant("s", token)}
        self._request(
            "BindShortcuts", "oa(sa{sv})sa{sv}",
            [self._session_handle, [(STOP_SHORTCUT_ID, shortcut)], "",
             options], token, timeout)

    def _request(self, member: str, signature: str, body: List[Any],
                 token: str, timeout: float) -> Dict[str, Any]:
        """One portal request: subscribe, call, wait for its ``Response``."""
        predicted = _request_path(self._bus.sender_token, token)
        self._bus.add_match(_match_rule(predicted))
        reply = self._bus.call(PORTAL_BUS, PORTAL_PATH, SHORTCUTS_INTERFACE,
                               member, signature, body, timeout=_CALL_TIMEOUT)
        paths = [predicted]
        handle = str(reply[0]) if reply else ""
        if handle and handle != predicted:
            self._bus.add_match(_match_rule(handle))
            paths.append(handle)
        answer = self._bus.wait_for_signal(paths, REQUEST_INTERFACE,
                                           "Response", timeout)
        return _results(member, answer)


def _connected_bus() -> Any:
    bus = _dbus_client.SessionBus()
    bus.connect()
    return bus


def _results(member: str, body: List[Any]) -> Dict[str, Any]:
    """Read a ``(u, a{sv})`` Response; anything but success is an error."""
    if len(body) < 2 or not isinstance(body[1], dict):
        raise ShortcutUnavailable(
            f"the portal answered {member} with something unreadable")
    code = int(body[0])
    if code == 1:
        raise ShortcutPermissionError(
            f"the stop shortcut was declined ({member})")
    if code != 0:
        raise ShortcutUnavailable(
            f"the portal ended {member} with response {code}")
    return body[1]


def _is_our_stop(body: List[Any], session_handle: str) -> bool:
    """Whether an ``Activated`` signal is this session's stop shortcut."""
    return (len(body) >= 2 and str(body[0]) == session_handle
            and str(body[1]) == STOP_SHORTCUT_ID)


def _is_timeout(error: BaseException) -> bool:
    """A quiet poll interval, as opposed to a connection that has ended."""
    return "did not answer in time" in str(error)


__all__ = [
    "DEFAULT_TIMEOUT", "SESSION_INTERFACE", "SHORTCUTS_INTERFACE",
    "STOP_RECOVERY", "STOP_SHORTCUT_ID", "ShortcutPermissionError",
    "ShortcutUnavailable", "StopShortcutSession",
]
