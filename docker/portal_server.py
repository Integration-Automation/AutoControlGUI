"""A mock ``org.freedesktop.portal.Desktop`` that implements RemoteDesktop.

The libei input path has two halves. ``docker/eis_server.py`` answers the
protocol half — a real ``libeis`` peer on a Unix socket, which settles the
enum values, the variadic bind and what actually goes on the wire. The other
half is how a client *gets* that socket on GNOME and KDE: it is not a path on
disk but a file descriptor handed over D-Bus at the end of the
``org.freedesktop.portal.RemoteDesktop`` session dance, and
:mod:`je_auto_control.linux_wayland.oeffis` drives ``liboeffis`` to perform it.

That half was recorded as needing a GNOME VM, on the grounds that
``xdg-desktop-portal-wlr`` implements ScreenCast and Screenshot but not
RemoteDesktop. What that reasoning missed is that the portal is *a D-Bus
interface*, not a compositor feature: anything that owns the well-known name
and answers the four calls is a portal as far as ``liboeffis`` is concerned.
So this module is that — a real D-Bus service on a real session bus, driving
the real ``liboeffis`` through the real handshake — and ``ConnectToEIS``
hands back a live connection to the real EIS server next door, which makes
the whole chain end at pixels-equivalent evidence: input emitted through a
portal-obtained fd, recorded by an independent implementation.

What it deliberately does *not* claim to be: a consent dialog. There is no
user here to dismiss anything. What a dialog produces, though — a grant, a
refusal, and a wait that never ends — are all just Response codes and silence
on the bus, so ``--behaviour`` produces each of them and the caller's
fail-closed handling is verified against all three.

Runs on the system interpreter, not the one that has AutoControl installed:
GDBus is what can pass a file descriptor over D-Bus from Python, it comes
from Debian's ``python3-gi``, and it is bound to Debian's ``python3``. That
suits it anyway — the portal has to be a separate process from the client
that calls it.
"""
from __future__ import annotations

import argparse
import json
import os
import socket
import struct
import sys
import tempfile
import zlib
from typing import Any, Dict, Optional

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib  # noqa: E402  # reason: gi.require_version must run first


BUS_NAME = "org.freedesktop.portal.Desktop"
OBJECT_PATH = "/org/freedesktop/portal/desktop"
REQUEST_INTERFACE = "org.freedesktop.portal.Request"
SESSION_INTERFACE = "org.freedesktop.portal.Session"

#: Portal response codes, from the XDG portal specification.
RESPONSE_SUCCESS = 0
RESPONSE_CANCELLED = 1

#: Everything a compositor could offer: keyboard | pointer | touchscreen.
ALL_DEVICE_TYPES = 7

#: ``grant`` is the happy path; the rest are the ways a real portal says no.
BEHAVIOURS = ("grant", "deny", "stall", "no-fd", "close")

#: The same idea for the Screenshot interface, which is a different portal
#: with a different client: :mod:`je_auto_control.linux_wayland.portal` speaks
#: D-Bus itself, so what is under test there is hand-written marshalling and a
#: directed signal arriving on a path the client predicted.
SCREENSHOT_BEHAVIOURS = ("grant", "deny", "stall", "no-uri", "not-a-file")

#: A filename with a space in it on purpose: the URI the portal returns is
#: percent-encoded, and unquoting it is a step the client has to get right.
SCREENSHOT_NAME = "autocontrol portal shot.png"

#: What the mock paints, so the client can be checked on the bytes it got
#: rather than merely on getting some.
SHOT_SIZE = (4, 3)
SHOT_RGB = (0, 128, 255)

PORTAL_XML = """
<node>
  <interface name='org.freedesktop.portal.RemoteDesktop'>
    <method name='CreateSession'>
      <arg type='a{sv}' name='options' direction='in'/>
      <arg type='o' name='handle' direction='out'/>
    </method>
    <method name='SelectDevices'>
      <arg type='o' name='session_handle' direction='in'/>
      <arg type='a{sv}' name='options' direction='in'/>
      <arg type='o' name='handle' direction='out'/>
    </method>
    <method name='Start'>
      <arg type='o' name='session_handle' direction='in'/>
      <arg type='s' name='parent_window' direction='in'/>
      <arg type='a{sv}' name='options' direction='in'/>
      <arg type='o' name='handle' direction='out'/>
    </method>
    <method name='ConnectToEIS'>
      <arg type='o' name='session_handle' direction='in'/>
      <arg type='a{sv}' name='options' direction='in'/>
      <arg type='h' name='fd' direction='out'/>
    </method>
    <property name='AvailableDeviceTypes' type='u' access='read'/>
    <property name='version' type='u' access='read'/>
  </interface>
  <interface name='org.freedesktop.portal.Screenshot'>
    <method name='Screenshot'>
      <arg type='s' name='parent_window' direction='in'/>
      <arg type='a{sv}' name='options' direction='in'/>
      <arg type='o' name='handle' direction='out'/>
    </method>
    <property name='version' type='u' access='read'/>
  </interface>
</node>
"""

REQUEST_XML = """
<node>
  <interface name='org.freedesktop.portal.Request'>
    <method name='Close'/>
    <signal name='Response'>
      <arg type='u' name='response'/>
      <arg type='a{sv}' name='results'/>
    </signal>
  </interface>
</node>
"""

SESSION_XML = """
<node>
  <interface name='org.freedesktop.portal.Session'>
    <method name='Close'/>
    <signal name='Closed'>
      <arg type='a{sv}' name='details'/>
    </signal>
    <property name='version' type='u' access='read'/>
  </interface>
</node>
"""


def sender_token(sender: str) -> str:
    """The client's unique bus name as the portal spec spells it in a path.

    Request and session objects live at a path the *client* predicts so it can
    subscribe before it calls, which only works if both sides mangle the name
    the same way: drop the leading colon, turn dots into underscores.
    """
    return sender.lstrip(":").replace(".", "_")


def _interface(xml: str, name: str = "") -> Gio.DBusInterfaceInfo:
    """One interface out of an introspection document, by name or the first."""
    interfaces = Gio.DBusNodeInfo.new_for_xml(xml).interfaces
    if not name:
        return interfaces[0]
    return next(info for info in interfaces if info.name == name)


def encode_png(width: int, height: int, rgb: tuple) -> bytes:
    """A valid PNG of one flat colour, with nothing but the standard library.

    The mock runs on Debian's interpreter, which has no imaging package, and
    handing the client bytes that are not really a PNG would check the
    transport while quietly skipping whether the result is usable.
    """
    row = bytes((0,)) + bytes(rgb) * width
    raw = zlib.compress(row * height, 9)

    def chunk(kind: bytes, payload: bytes) -> bytes:
        body = kind + payload
        return (struct.pack(">I", len(payload)) + body
                + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF))

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header)
            + chunk(b"IDAT", raw) + chunk(b"IEND", b""))


class MockPortal:
    """Owns the portal bus name and answers the RemoteDesktop calls.

    :param eis_socket: the EIS server socket ``ConnectToEIS`` connects to.
    :param behaviour: one of :data:`BEHAVIOURS`.
    :param record_path: JSON file the driver reads to see what arrived.
    :param version: what to report as the RemoteDesktop interface version;
        ``ConnectToEIS`` only exists from 2, so 1 is a portal too old to use.
    """

    def __init__(self, eis_socket: str, behaviour: str, record_path: str,
                 version: int = 2, screenshot: str = "grant",
                 shot_dir: Optional[str] = None) -> None:
        self.eis_socket = eis_socket
        self.behaviour = behaviour
        self.record_path = record_path
        self.version = version
        self.screenshot = screenshot
        # The driver always passes one; without it, a private
        # directory rather than the world-writable /tmp root.
        self.shot_dir = shot_dir or tempfile.mkdtemp(
            prefix="autocontrol-portal-")
        self.record: Dict[str, Any] = {
            "calls": [], "device_types": None, "properties": [],
            "session_closed_by_client": False, "shot_path": "",
        }
        self.connection: Optional[Gio.DBusConnection] = None
        #: Registration ids are kept only so the objects stay exported.
        self._exported: list = []
        self._remote_desktop_info = _interface(
            PORTAL_XML, "org.freedesktop.portal.RemoteDesktop")
        self._screenshot_info = _interface(
            PORTAL_XML, "org.freedesktop.portal.Screenshot")
        self._request_info = _interface(REQUEST_XML)
        self._session_info = _interface(SESSION_XML)

    # --- recording --------------------------------------------------------

    def _flush(self) -> None:
        """Write the record out now; the driver reads it while we still run."""
        with open(self.record_path, "w", encoding="utf-8") as handle:
            json.dump(self.record, handle)

    def _note(self, method: str, detail: Any = None) -> None:
        self.record["calls"].append({"method": method, "detail": detail})
        self._flush()

    # --- lifecycle --------------------------------------------------------

    def run(self) -> None:
        """Take the bus name and serve until killed."""
        self.connection = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        for info in (self._remote_desktop_info, self._screenshot_info):
            self.connection.register_object(
                OBJECT_PATH, info,
                self._on_method_call, self._on_get_property, None)
        Gio.bus_own_name_on_connection(
            self.connection, BUS_NAME, Gio.BusNameOwnerFlags.NONE,
            lambda *_args: print("portal: owns " + BUS_NAME, flush=True),
            lambda *_args: print("portal: lost " + BUS_NAME, flush=True))
        self._flush()
        print(f"portal: ready (behaviour={self.behaviour}, "
              f"screenshot={self.screenshot}, version={self.version})",
              flush=True)
        GLib.MainLoop().run()

    # --- properties -------------------------------------------------------

    def _on_get_property(self, _connection: Gio.DBusConnection, _sender: str,
                         _path: str, _interface_name: str,
                         name: str) -> Optional[GLib.Variant]:
        """``version`` is the first thing liboeffis reads, before any call."""
        self.record["properties"].append(name)
        self._flush()
        if name == "version":
            return GLib.Variant("u", self.version)
        if name == "AvailableDeviceTypes":
            return GLib.Variant("u", ALL_DEVICE_TYPES)
        return None

    # --- method dispatch --------------------------------------------------

    def _on_method_call(self, _connection: Gio.DBusConnection, sender: str,
                        _path: str, _interface_name: str, method: str,
                        parameters: GLib.Variant,
                        invocation: Gio.DBusMethodInvocation) -> None:
        print(f"portal: {method}{parameters}", flush=True)
        handler = getattr(self, f"_do_{method}", None)
        if handler is None:
            invocation.return_error_literal(
                Gio.dbus_error_quark(), Gio.DBusError.UNKNOWN_METHOD, method)
            return
        handler(sender, parameters, invocation)

    def _request_path(self, sender: str, options: Dict[str, Any]) -> str:
        """The object path the client already subscribed to."""
        token = options.get("handle_token", "unnamed")
        return f"{OBJECT_PATH}/request/{sender_token(sender)}/{token}"

    def _export_request(self, path: str) -> None:
        """Export the request object so ``Close()`` on it is answerable."""
        self._exported.append(self.connection.register_object(
            path, self._request_info, self._answer_empty, None, None))

    def _answer_empty(self, _connection: Gio.DBusConnection, _sender: str,
                      _path: str, _interface_name: str, _method: str,
                      _parameters: GLib.Variant,
                      invocation: Gio.DBusMethodInvocation) -> None:
        invocation.return_value(None)

    def _on_session_call(self, _connection: Gio.DBusConnection, _sender: str,
                         _path: str, _interface_name: str, method: str,
                         _parameters: GLib.Variant,
                         invocation: Gio.DBusMethodInvocation) -> None:
        """Record whether the client ends its grant explicitly, or just leaves."""
        if method == "Close":
            self.record["session_closed_by_client"] = True
            self._flush()
        invocation.return_value(None)

    def _respond(self, sender: str, path: str, code: int,
                 results: Dict[str, GLib.Variant]) -> bool:
        """Emit the ``Response`` signal the whole portal protocol turns on."""
        self.connection.emit_signal(
            sender, path, REQUEST_INTERFACE, "Response",
            GLib.Variant("(ua{sv})", (code, results)))
        return False  # reason: one-shot, so GLib.idle_add does not repeat it

    # --- the four RemoteDesktop calls -------------------------------------

    def _do_CreateSession(self, sender: str, parameters: GLib.Variant,  # noqa: N802  # reason: D-Bus method name
                          invocation: Gio.DBusMethodInvocation) -> None:
        options = parameters.unpack()[0]
        self._note("CreateSession", options)
        request = self._request_path(sender, options)
        self._export_request(request)
        token = options.get("session_handle_token", "unnamed")
        session = f"{OBJECT_PATH}/session/{sender_token(sender)}/{token}"
        self._exported.append(self.connection.register_object(
            session, self._session_info, self._on_session_call,
            lambda *_args: GLib.Variant("u", 2), None))
        invocation.return_value(GLib.Variant("(o)", (request,)))
        if self.behaviour == "stall":
            # A consent dialog nobody answers: the handle was returned, the
            # Response never comes. The client must give up on its own clock.
            return
        GLib.idle_add(self._respond, sender, request, RESPONSE_SUCCESS,
                      {"session_handle": GLib.Variant("s", session)})
        if self.behaviour == "close":
            GLib.idle_add(self._close_session, sender, session)

    def _close_session(self, sender: str, session: str) -> bool:
        """End the grant the way a compositor does when the session stops."""
        self.connection.emit_signal(
            sender, session, SESSION_INTERFACE, "Closed",
            GLib.Variant("(a{sv})", ({},)))
        return False

    def _do_SelectDevices(self, sender: str, parameters: GLib.Variant,  # noqa: N802  # reason: D-Bus method name
                          invocation: Gio.DBusMethodInvocation) -> None:
        session, options = parameters.unpack()
        self._note("SelectDevices", {"session": session, "options": options})
        types = options.get("types")
        if types is not None:
            self.record["device_types"] = int(types)
            self._flush()
        request = self._request_path(sender, options)
        self._export_request(request)
        invocation.return_value(GLib.Variant("(o)", (request,)))
        GLib.idle_add(self._respond, sender, request, RESPONSE_SUCCESS, {})

    def _do_Start(self, sender: str, parameters: GLib.Variant,  # noqa: N802  # reason: D-Bus method name
                  invocation: Gio.DBusMethodInvocation) -> None:
        session, parent_window, options = parameters.unpack()
        self._note("Start", {"session": session, "parent": parent_window,
                             "options": options})
        request = self._request_path(sender, options)
        self._export_request(request)
        invocation.return_value(GLib.Variant("(o)", (request,)))
        # ``deny`` is the consent dialog the user dismissed: the portal
        # answers, and the answer is no.
        denied = self.behaviour == "deny"
        code = RESPONSE_CANCELLED if denied else RESPONSE_SUCCESS
        results = {} if denied else {"devices": GLib.Variant("u", 3)}
        GLib.idle_add(self._respond, sender, request, code, results)

    def _do_ConnectToEIS(self, _sender: str, parameters: GLib.Variant,  # noqa: N802  # reason: D-Bus method name
                         invocation: Gio.DBusMethodInvocation) -> None:
        session, options = parameters.unpack()
        self._note("ConnectToEIS", {"session": session, "options": options})
        if self.behaviour == "no-fd":
            invocation.return_error_literal(
                Gio.dbus_error_quark(), Gio.DBusError.FAILED,
                "this portal will not hand over an EIS fd")
            return
        try:
            client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            client.connect(self.eis_socket)
        except OSError as error:
            invocation.return_error_literal(
                Gio.dbus_error_quark(), Gio.DBusError.FAILED, str(error))
            return
        # GDBus dups what it appends, so the local end is closed here and the
        # client gets its own descriptor — which is exactly the ownership a
        # real portal hands over.
        fd_list = Gio.UnixFDList.new()
        index = fd_list.append(client.fileno())
        client.close()
        invocation.return_value_with_unix_fd_list(
            GLib.Variant("(h)", (index,)), fd_list)


    # --- the Screenshot call ----------------------------------------------

    def _do_Screenshot(self, sender: str, parameters: GLib.Variant,  # noqa: N802  # reason: D-Bus method name
                       invocation: Gio.DBusMethodInvocation) -> None:
        """Answer the interface every desktop implements, however it captures.

        The client here is not a C library but AutoControl's own D-Bus
        marshalling, in :mod:`je_auto_control.linux_wayland._dbus_client`.
        Answering on the path the client predicted, with a signal directed at
        the connection that called, is what that code has to cope with — and
        is exactly what the ``gdbus monitor`` design it replaced could not.
        """
        parent_window, options = parameters.unpack()
        self._note("Screenshot", {"parent": parent_window, "options": options})
        request = self._request_path(sender, options)
        self._export_request(request)
        invocation.return_value(GLib.Variant("(o)", (request,)))
        if self.screenshot == "stall":
            return
        GLib.idle_add(self._respond_screenshot, sender, request)

    def _respond_screenshot(self, sender: str, request: str) -> bool:
        """Every outcome a real Screenshot portal can end on."""
        if self.screenshot == "deny":
            return self._respond(sender, request, RESPONSE_CANCELLED, {})
        if self.screenshot == "no-uri":
            return self._respond(sender, request, RESPONSE_SUCCESS, {})
        if self.screenshot == "not-a-file":
            return self._respond(sender, request, RESPONSE_SUCCESS,
                                 {"uri": GLib.Variant(
                                     "s", "https://example.invalid/shot.png")})
        path = os.path.join(self.shot_dir, SCREENSHOT_NAME)
        with open(path, "wb") as image:
            image.write(encode_png(*SHOT_SIZE, SHOT_RGB))
        self.record["shot_path"] = path
        self._flush()
        uri = "file://" + GLib.uri_escape_string(path, "/", False)
        return self._respond(sender, request, RESPONSE_SUCCESS,
                             {"uri": GLib.Variant("s", uri)})


def main() -> int:
    """Parse the arguments and serve until the driver kills the process."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--eis-socket", required=True,
                        help="EIS server socket that ConnectToEIS connects to")
    parser.add_argument("--behaviour", default="grant", choices=BEHAVIOURS)
    parser.add_argument("--record", required=True,
                        help="JSON file recording what the client asked for")
    parser.add_argument("--version", type=int, default=2,
                        help="RemoteDesktop interface version to advertise")
    parser.add_argument("--screenshot", default="grant",
                        choices=SCREENSHOT_BEHAVIOURS)
    parser.add_argument("--shot-dir", default=None,
                        help="directory the mock writes its capture into")
    arguments = parser.parse_args()
    os.umask(0o077)
    MockPortal(arguments.eis_socket, arguments.behaviour, arguments.record,
               arguments.version, arguments.screenshot,
               arguments.shot_dir).run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
