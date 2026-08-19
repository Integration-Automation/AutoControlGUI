"""Last-resort screen capture through ``xdg-desktop-portal``.

The three CLI helpers in :mod:`capture` each cover one compositor family and
none of them is guaranteed to be installed — GNOME has not shipped
``gnome-screenshot`` by default since 42. ``org.freedesktop.portal.Screenshot``
is the one interface every modern desktop implements, so it is tried after
them all rather than not at all.

It is awkward enough to deserve explaining. The portal does not return the
image: ``Screenshot`` returns a *request* object path and the result arrives
later as a ``Response`` signal on it, **directed at the unique bus name that
made the call**. So the subscription has to be in place before the call, and
it has to be on the same connection — a listener anywhere else is not the
destination, and the bus routes a directed message to its destination only.

That is why this does not shell out. The obvious implementation — ``gdbus
monitor`` in one process, ``gdbus call`` in another — cannot work and did not:
each invocation opens its own connection under its own unique name, so the
monitor is never the caller. Measured against a real ``dbus-daemon``, the
monitor saw the call go past and the answer never arrived, and the capture
timed out every time. :mod:`_dbus_client` speaks the protocol directly instead,
which also drops the ``gdbus`` binary from what a desktop has to have
installed for this tier to work.

Two consequences the caller has to live with, both documented at the tier that
uses this: the portal may show a consent dialog the first time (so the wait is
bounded by :data:`DEFAULT_TIMEOUT`, not instant), and it always captures the
whole screen, so a region is cropped afterwards.

Every failure here is an ordinary capture failure — the caller reports the
install hint for the CLI helpers, which is the actionable advice.
"""
from __future__ import annotations

import contextlib
import os
import threading
import urllib.parse
from typing import Any, Dict, List, Tuple

from je_auto_control.linux_wayland import _dbus_client
from je_auto_control.utils.exception.exceptions import AutoControlScreenException


PORTAL_BUS = "org.freedesktop.portal.Desktop"
PORTAL_PATH = "/org/freedesktop/portal/desktop"
SCREENSHOT_INTERFACE = "org.freedesktop.portal.Screenshot"
REQUEST_INTERFACE = "org.freedesktop.portal.Request"
PORTAL_METHOD = f"{SCREENSHOT_INTERFACE}.Screenshot"

# The portal may put a consent dialog in front of the response the first time,
# so this is a human-scale wait, not a machine-scale one.
DEFAULT_TIMEOUT = 30.0
_CALL_TIMEOUT = 10.0

# 0 success, 1 cancelled by the user, 2 ended some other way.
_RESPONSE_MEANING = {
    1: "the user dismissed the desktop portal's screenshot dialog",
    2: "the desktop portal ended the screenshot request",
}


def is_available() -> bool:
    """Whether a session bus exists, so the portal tier is worth trying."""
    return _dbus_client.is_available()


def capture_png(timeout: float = DEFAULT_TIMEOUT) -> bytes:
    """Ask the desktop portal for a full-screen capture; return PNG bytes.

    :param timeout: seconds to wait for the portal's Response signal,
        including any time the user spends on a consent dialog.
    :return: the captured image file's bytes.
    """
    try:
        with _dbus_client.SessionBus() as bus:
            uri = _request_and_await(bus, timeout)
    except _dbus_client.DBusError as error:
        raise AutoControlScreenException(
            f"the desktop portal could not be reached: {error}",
        ) from error
    return _read_and_discard(_path_from_uri(uri))


def _request_and_await(bus: "_dbus_client.SessionBus", timeout: float) -> str:
    """Subscribe, call, and wait — in that order, on the one connection."""
    token = _handle_token()
    predicted = _request_path(bus.sender_token, token)
    bus.add_match(_match_rule(predicted))
    handle = _screenshot(bus, token)
    paths = [predicted]
    # A portal that ignores handle_token answers on a path of its own choosing.
    # The specification tells clients to follow the returned handle, and the
    # subscription for it can only be added once the call has returned it —
    # which is exactly why the predicted one is subscribed to first.
    if handle and handle != predicted:
        bus.add_match(_match_rule(handle))
        paths.append(handle)
    try:
        body = bus.wait_for_signal(paths, REQUEST_INTERFACE, "Response",
                                   timeout)
    except _dbus_client.DBusError as error:
        raise AutoControlScreenException(
            f"desktop portal did not answer within {timeout:g}s "
            f"(a consent dialog may be waiting)",
        ) from error
    return _uri_from_response(body)


def _screenshot(bus: "_dbus_client.SessionBus", token: str) -> str:
    """Make the Screenshot call; its return value is only a request handle."""
    options = {
        "interactive": _dbus_client.Variant("b", False),
        "handle_token": _dbus_client.Variant("s", token),
    }
    body = bus.call(PORTAL_BUS, PORTAL_PATH, SCREENSHOT_INTERFACE,
                    "Screenshot", "sa{sv}", ["", options],
                    timeout=_CALL_TIMEOUT)
    return str(body[0]) if body else ""


#: Guards the counter below. Captures can be started from the callback
#: executor and a GUI thread at once, and ``+= 1`` is not atomic — two threads
#: reading the same value would put both portal answers on one object path.
_TOKEN_LOCK = threading.Lock()
_REQUEST_COUNT = 0


def _handle_token() -> str:
    """A token unique to this request, which the request path is built from.

    Only ``[A-Za-z0-9_]`` is legal in the object path element it becomes, and
    reusing one across two concurrent captures would put both answers on one
    path, so the process and a counter both go in.
    """
    global _REQUEST_COUNT  # noqa: PLW0603  # reason: one counter per process is the point
    with _TOKEN_LOCK:
        _REQUEST_COUNT += 1
        count = _REQUEST_COUNT
    return f"je_auto_control_{os.getpid()}_{count}"


def _request_path(sender_token: str, handle_token: str) -> str:
    """Where the portal will emit ``Response``, by the specification's rule."""
    return f"{PORTAL_PATH}/request/{sender_token}/{handle_token}"


def _match_rule(path: str) -> str:
    """A match rule narrow enough that only this request's answer arrives."""
    return (f"type='signal',sender='{PORTAL_BUS}',path='{path}',"
            f"interface='{REQUEST_INTERFACE}',member='Response'")


def _uri_from_response(body: List[Any]) -> str:
    """Read the screenshot URI out of one ``Response`` signal body."""
    code, results = _response_parts(body)
    if code != 0:
        raise AutoControlScreenException(
            _RESPONSE_MEANING.get(code, f"desktop portal returned {code}"),
        )
    uri = results.get("uri", "")
    if not uri:
        raise AutoControlScreenException(
            "desktop portal reported success but returned no image URI",
        )
    return str(uri)


def _response_parts(body: List[Any]) -> Tuple[int, Dict[str, Any]]:
    """Split a ``(u, a{sv})`` signal body, rejecting anything else."""
    if len(body) < 2 or not isinstance(body[1], dict):
        raise AutoControlScreenException(
            f"the desktop portal sent a Response this cannot read: {body!r}",
        )
    return int(body[0]), body[1]


def _path_from_uri(uri: str) -> str:
    """Convert the portal's ``file://`` URI into a local path."""
    parsed = urllib.parse.urlparse(uri)
    if parsed.scheme != "file":
        raise AutoControlScreenException(
            f"desktop portal returned a non-file URI: {uri!r}",
        )
    return urllib.parse.unquote(parsed.path)


def _read_and_discard(path: str) -> bytes:
    """Read the portal's file, then remove it — it is ours to clean up."""
    try:
        with open(path, "rb") as captured:
            data = captured.read()
    except OSError as error:
        raise AutoControlScreenException(
            f"could not read the portal's screenshot at {path!r}: {error}",
        ) from error
    finally:
        with contextlib.suppress(OSError):
            os.unlink(path)
    if not data:
        raise AutoControlScreenException("desktop portal wrote an empty file")
    return data


__all__ = ["DEFAULT_TIMEOUT", "PORTAL_BUS", "PORTAL_METHOD", "PORTAL_PATH",
           "REQUEST_INTERFACE", "SCREENSHOT_INTERFACE", "capture_png",
           "is_available"]
