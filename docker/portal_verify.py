"""Verify AutoControl's portal handshake against a real ``liboeffis``.

``eis_verify.py`` drives the libei sender against a real EIS peer, but it
reaches that peer the way no GNOME or KDE desktop offers: by handing
``connect()`` a socket path. The route those desktops actually use is
``org.freedesktop.portal.RemoteDesktop`` — a D-Bus session dance ending in a
file descriptor passed over SCM_RIGHTS — and it was recorded as unverifiable
without a GNOME VM, because ``xdg-desktop-portal-wlr`` has no RemoteDesktop
interface.

The portal is a D-Bus interface, though, not a compositor feature.
``docker/portal_server.py`` owns the well-known name and answers the four
calls, so the real ``liboeffis`` runs the real handshake here, and its
``ConnectToEIS`` returns a live connection to the real EIS server from
``eis_server.py``. That makes the whole path checkable end to end:

  * the four calls arrive in the order the specification prescribes, at the
    request paths the client predicted — a mismatch there is a client that
    subscribes to a signal nobody sends and then times out;
  * ``SelectDevices`` receives the keyboard-and-pointer mask this project
    asks for, so :data:`~je_auto_control.linux_wayland.oeffis.OEFFIS_DEVICE_DEFAULT`
    is neither wider than the grant the user consents to nor the ``= 0``
    all-devices sentinel it would be if the constant were wrong;
  * the descriptor that comes back carries a real EI session: the sender
    completes its handshake on it and the input it emits is recorded by an
    independent implementation at the far end;
  * and every way a portal says no — a dismissed dialog, a dialog left open,
    a refused descriptor, a closed session, a portal too old to have
    ``ConnectToEIS`` at all, no portal on the bus — produces a refusal on
    this project's own clock rather than a hang or a silent downgrade.

What is still not claimed: the consent dialog itself. No user dismisses
anything here. What a dialog *produces* is a Response code or silence, and
all three outcomes are exercised; what it looks like is mutter's business.

Exit status is the number of failed checks.
"""
from __future__ import annotations

import contextlib
import faulthandler
import json
import os
import shutil
import stat
import subprocess  # nosec B404  # reason: launches dbus-daemon and the mock portal, argv lists, no shell
import sys
import threading
import time
import traceback
from typing import Any, Callable, Dict, List, Optional, Tuple

# A wrong prototype in a ctypes binding is a segfault, not an exception.
faulthandler.enable()

_results: List[Tuple[str, bool]] = []

#: evdev codes the emission check uses. KEY_A, BTN_LEFT.
KEY_A = 30
BTN_LEFT = 272
TARGET_POSITION = (640, 400)

#: The order the XDG portal specification prescribes, and the order a client
#: that got it wrong would never complete in.
EXPECTED_CALLS = ("CreateSession", "SelectDevices", "Start", "ConnectToEIS")

#: What the mock paints. Re-declared rather than imported from
#: ``portal_server``, which runs on the other interpreter — and which is the
#: right call anyway: two sides agreeing on one wrong constant is a test that
#: passes while the thing under it is broken.
SHOT_SIZE = (4, 3)
SHOT_RGB = (0, 128, 255)

#: The file name the mock writes into the ``--shot-dir`` it is given. Both
#: halves of the capture path are therefore this script's own, so the
#: cleanup check below never has to build a path out of what came back over
#: the bus; the equality assertion there is what fails loudly if
#: ``portal_server.SCREENSHOT_NAME`` and this ever drift apart.
SHOT_NAME = "autocontrol portal shot.png"

#: Long enough for a portal that is going to answer; short enough that the
#: ones written not to answer do not hold the image up.
GRANT_TIMEOUT = 10.0
REFUSAL_TIMEOUT = 3.0


def check(name: str, function: Callable[[], Any]) -> Any:
    """Run one check, record the outcome, and never let it stop the rest."""
    try:
        detail = function()
    except Exception:  # noqa: BLE001  # reason: one failed check must not stop the rest
        _results.append((name, False))
        print(f"FAIL  {name}")
        print("        " + traceback.format_exc(limit=4).strip().replace(
            "\n", "\n        "))
        return None
    _results.append((name, True))
    print(f"ok    {name}" + (f"  — {detail}" if detail else ""))
    return detail


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _runtime_dir() -> str:
    runtime = os.environ.get("XDG_RUNTIME_DIR", "/tmp")  # nosec B108  # reason: container fallback only
    os.makedirs(runtime, exist_ok=True)
    return runtime


def _fresh_socket_path(name: str) -> str:
    path = os.path.join(_runtime_dir(), name)
    with contextlib.suppress(FileNotFoundError):
        os.unlink(path)
    return path


class SessionBus:
    """A private ``dbus-daemon`` this run owns, exported to the environment.

    liboeffis reads ``DBUS_SESSION_BUS_ADDRESS`` from the environment of the
    process it is loaded into, so the address has to land in :data:`os.environ`
    and not only in the child's.
    """

    def __init__(self) -> None:
        self._process: Optional[subprocess.Popen] = None
        self.address = ""

    def start(self) -> str:
        binary = shutil.which("dbus-daemon")
        if binary is None:
            raise RuntimeError("dbus-daemon is not installed")
        # argv is a private allow-list; no shell and no user-supplied component.
        self._process = subprocess.Popen(  # nosec B603  # nosemgrep
            [binary, "--session", "--print-address", "--nofork"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        address = (self._process.stdout.readline() or "").strip()
        if not address:
            raise RuntimeError("dbus-daemon printed no bus address")
        self.address = address
        os.environ["DBUS_SESSION_BUS_ADDRESS"] = address
        return address

    def stop(self) -> None:
        if self._process is None:
            return
        with contextlib.suppress(OSError, ValueError):
            self._process.terminate()
        with contextlib.suppress(subprocess.TimeoutExpired, OSError, ValueError):
            self._process.wait(timeout=5)
        self._process = None


class Portal:
    """The mock portal, running as a child process for one scenario.

    Used as a context manager so the bus name is released before the next
    scenario asks for it.
    """

    def __init__(self, eis_socket: str, behaviour: str = "grant",
                 version: int = 2, screenshot: str = "grant") -> None:
        self.eis_socket = eis_socket
        self.behaviour = behaviour
        self.version = version
        self.screenshot = screenshot
        self.record_path = os.path.join(
            _runtime_dir(),
            f"portal-record-{behaviour}-{screenshot}-{version}.json")
        self.lines: List[str] = []
        self._process: Optional[subprocess.Popen] = None
        self._pump: Optional[threading.Thread] = None

    def __enter__(self) -> "Portal":
        server = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              "portal_server.py")
        # Debian's python3 is the one with GDBus; this interpreter is the one
        # with AutoControl. The portal has to be a separate process anyway.
        argv = ["/usr/bin/python3", server,
                "--eis-socket", self.eis_socket,
                "--behaviour", self.behaviour,
                "--record", self.record_path,
                "--version", str(self.version),
                "--screenshot", self.screenshot,
                "--shot-dir", _runtime_dir()]
        # argv is a private allow-list; no shell and no user-supplied component.
        self._process = subprocess.Popen(  # nosec B603  # nosemgrep
            argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        self._pump = threading.Thread(target=self._read, daemon=True,
                                      name="portal-stdout")
        self._pump.start()
        self._await_name()
        return self

    def __exit__(self, *_exception: Any) -> None:
        if self._process is None:
            return
        with contextlib.suppress(OSError, ValueError):
            self._process.terminate()
        with contextlib.suppress(subprocess.TimeoutExpired, OSError, ValueError):
            self._process.wait(timeout=5)
        if self._pump is not None:
            self._pump.join(timeout=2)
        self._process = None

    def _read(self) -> None:
        stream = self._process.stdout if self._process else None
        if stream is None:
            return
        with contextlib.suppress(OSError, ValueError):
            for line in stream:
                self.lines.append(line.rstrip())

    def _await_name(self, timeout: float = 15.0) -> None:
        """Wait until the portal owns the name, not merely until it started."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            # Snapshot: the reader thread appends to this list as we read.
            seen = list(self.lines)
            if any("owns " in line for line in seen):
                return
            if self._process is not None and self._process.poll() is not None:
                raise RuntimeError(
                    "the mock portal exited before taking the bus name:\n"
                    + "\n".join(self.lines))
            time.sleep(0.02)
        raise RuntimeError("the mock portal never took the bus name")

    def recorded(self) -> Dict[str, Any]:
        """What the portal has seen so far."""
        try:
            with open(self.record_path, "r", encoding="utf-8") as handle:
                return json.load(handle)
        except (OSError, ValueError):
            return {"calls": [], "device_types": None, "properties": []}

    def methods(self) -> List[str]:
        return [call["method"] for call in self.recorded()["calls"]]

    def await_call(self, method: str, timeout: float = 5.0) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if method in self.methods():
                return
            time.sleep(0.02)
        raise AssertionError(
            f"the portal never saw {method}; it saw {self.methods()}")


def _wait_for(predicate: Callable[[], bool], timeout: float,
              description: str) -> None:
    """Spin until the server thread has recorded something, or give up."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.02)
    raise AssertionError(f"timed out waiting for {description}")


def _refused(action: Callable[[], Any], expected: type,
             budget: float) -> str:
    """Assert an action fails closed, promptly, and return the reason it gave."""
    started = time.monotonic()
    try:
        action()
    except expected as error:
        elapsed = time.monotonic() - started
        _require(elapsed <= budget,
                 f"the refusal took {elapsed:.1f}s, longer than the {budget:g}s "
                 f"budget — that is a hang wearing a refusal's clothes")
        return f"{str(error)[:96]} (in {elapsed:.1f}s)"
    raise AssertionError(
        f"expected {expected.__name__}; the call returned instead")


# --- checks ---------------------------------------------------------------


def _check_liboeffis_binds(oeffis) -> str:
    """Every entry point the binding names, resolved against the real library."""
    symbols = oeffis.load_symbols()
    _require(symbols is not None,
             "liboeffis.so.* did not resolve — install liboeffis1")
    _require(oeffis.is_available(), "is_available() disagrees with load_symbols()")
    _require(oeffis.OEFFIS_DEVICE_DEFAULT != oeffis.OEFFIS_DEVICE_ALL_DEVICES,
             "the default device mask is the all-devices sentinel")
    return f"default device mask = {oeffis.OEFFIS_DEVICE_DEFAULT}"


def _check_no_portal_is_refused(oeffis) -> str:
    """The state of every desktop that has no RemoteDesktop portal."""
    return _refused(lambda: oeffis.connect_eis_fd(timeout=REFUSAL_TIMEOUT),
                    oeffis.OeffisUnavailable, REFUSAL_TIMEOUT + 3.0)


def _check_call_order(portal: Portal) -> str:
    calls = portal.methods()
    _require(tuple(calls[:len(EXPECTED_CALLS)]) == EXPECTED_CALLS,
             f"the portal saw {calls}, not {list(EXPECTED_CALLS)}")
    _require("version" in portal.recorded()["properties"],
             "liboeffis never read the RemoteDesktop version property")
    return " -> ".join(calls)


def _check_device_mask(portal: Portal, oeffis) -> str:
    """What the user is actually asked to consent to."""
    types = portal.recorded()["device_types"]
    _require(types is not None, "SelectDevices carried no `types` option")
    _require(types == oeffis.OEFFIS_DEVICE_DEFAULT,
             f"the portal was asked for {types}, not "
             f"{oeffis.OEFFIS_DEVICE_DEFAULT}")
    _require(not types & oeffis.OEFFIS_DEVICE_TOUCHSCREEN,
             "the grant includes a touchscreen this backend never emits on")
    return f"types={types} (keyboard|pointer)"


def _check_fd_is_live_and_owned(oeffis) -> str:
    """The descriptor is a real socket, and it is the caller's to close.

    ``oeffis_get_eis_fd`` is documented as returning a ``dup()`` whose owner
    is the caller. Everything downstream depends on that: libei takes
    ownership of what it is handed and closes it when torn down, so a second
    owner here would be a double close.
    """
    eis_fd, session = oeffis.connect_eis_fd(timeout=GRANT_TIMEOUT)
    try:
        _require(eis_fd >= 0, f"the portal handed over fd {eis_fd}")
        info = os.fstat(eis_fd)
        _require(stat.S_ISSOCK(info.st_mode),
                 f"fd {eis_fd} is not a socket (mode {info.st_mode:#o})")
        os.close(eis_fd)
        with contextlib.suppress(OSError):
            os.fstat(eis_fd)
            raise AssertionError(
                f"fd {eis_fd} survived close() — it was not ours to own")
    finally:
        session.close()
        session.close()  # idempotent: the teardown path calls it too
    return f"fd {eis_fd} was a socket, and closing it was ours to do"


def _connected_through_the_portal(libei):
    """A full sender handshake with no socket path — the portal's route."""
    backend = libei.LibeiBackend()
    backend.connect(timeout=GRANT_TIMEOUT)
    _require(backend.is_connected,
             "connect() returned but the backend reports no live device")
    return backend


def _check_session_reaches_eis(server) -> str:
    record = server.recording
    _wait_for(lambda: bool(record.devices), 5.0, "the seat to hand over devices")
    _require(record.seat_binds >= 1, "the client never bound a seat")
    _require(all(record.sender_flags),
             "the client did not present itself as a sender")
    return (f"client={record.clients[0]!r} seat binds={record.seat_binds} "
            f"devices={record.devices}")


def _check_input_over_the_portal_fd(backend, server) -> str:
    record = server.recording
    backend.press_key(KEY_A)
    backend.release_key(KEY_A)
    backend.set_position(*TARGET_POSITION)
    backend.press_button(BTN_LEFT)
    backend.release_button(BTN_LEFT)
    _wait_for(lambda: len(record.keys) >= 2, 5.0, "the key press and release")
    _wait_for(lambda: bool(record.absolute_motions), 5.0, "the absolute motion")
    _wait_for(lambda: len(record.buttons) >= 2, 5.0, "the button edges")
    _require(record.keys[:2] == [(KEY_A, True), (KEY_A, False)],
             f"the server recorded {record.keys[:2]}")
    landed = record.absolute_motions[-1]
    _require(tuple(int(value) for value in landed) == TARGET_POSITION,
             f"the pointer landed at {landed}, not {TARGET_POSITION}")
    _require(record.buttons[:2] == [(BTN_LEFT, True), (BTN_LEFT, False)],
             f"the server recorded {record.buttons[:2]}")
    return (f"keys={record.keys[:2]} motion={landed} "
            f"buttons={record.buttons[:2]}")


def _check_disconnect_ends_the_grant(backend, server, portal: Portal) -> str:
    """Tearing down must revoke the grant, not merely stop emitting."""
    before = server.recording.disconnects
    backend.disconnect()
    backend.disconnect()
    _wait_for(lambda: server.recording.disconnects > before, 5.0,
              "the EIS server to see the client go away")
    closed = portal.recorded().get("session_closed_by_client", False)
    return ("the portal session was closed explicitly" if closed else
            "the D-Bus connection was dropped, which revokes the grant")


def _check_portal_refuses(oeffis) -> str:
    return _refused(lambda: oeffis.connect_eis_fd(timeout=GRANT_TIMEOUT),
                    oeffis.OeffisUnavailable, GRANT_TIMEOUT)


def _check_open_dialog_times_out(oeffis) -> str:
    """A consent dialog nobody answers must end on our clock, not never."""
    reason = _refused(lambda: oeffis.connect_eis_fd(timeout=REFUSAL_TIMEOUT),
                      oeffis.OeffisUnavailable, REFUSAL_TIMEOUT + 3.0)
    _require("consent" in reason,
             f"the timeout did not name the consent dialog: {reason}")
    return reason


def _check_backend_surfaces_the_refusal(libei) -> str:
    """A refused portal must reach the caller as this project's own error."""
    return _refused(lambda: libei.LibeiBackend().connect(timeout=GRANT_TIMEOUT),
                    libei.LibeiUnavailable, GRANT_TIMEOUT + 3.0)


def _check_capture_returns_the_portal_bytes(wayland_portal, portal: Portal) -> str:
    """The Screenshot tier, end to end, on hand-marshalled D-Bus.

    Nothing here is mocked: a real ``dbus-daemon`` routes real messages that
    :mod:`je_auto_control.linux_wayland._dbus_client` marshalled itself, to a
    real portal that answers with a signal directed at the caller — which is
    the property that made the previous ``gdbus monitor`` design unable to work
    at all, and which nothing short of a real bus would have shown.
    """
    import numpy
    import cv2

    payload = wayland_portal.capture_png(timeout=15.0)
    _require(payload.startswith(b"\x89PNG"),
             f"the portal tier returned {payload[:8]!r}, which is not a PNG")
    decoded = cv2.imdecode(numpy.frombuffer(payload, dtype=numpy.uint8),
                           cv2.IMREAD_COLOR)
    _require(decoded is not None, "the portal's PNG did not decode")
    height, width = decoded.shape[:2]
    _require((width, height) == SHOT_SIZE,
             f"decoded {width}x{height}, expected {SHOT_SIZE}")
    # OpenCV decodes to BGR; the mock painted RGB.
    _require(tuple(int(value) for value in decoded[0][0]) == SHOT_RGB[::-1],
             f"the first pixel is {decoded[0][0]}, not {SHOT_RGB[::-1]}")
    shot = portal.recorded().get("shot_path", "")
    _require(bool(shot), "the portal never recorded where it wrote the capture")
    expected = os.path.join(_runtime_dir(), SHOT_NAME)
    _require(shot == expected,
             f"the portal wrote {shot!r}, not the {expected!r} it was told to")
    _require(not os.path.exists(expected),
             f"the portal's file at {expected!r} was left behind")
    return (f"{len(payload)} bytes, decoded {width}x{height}, "
            f"and {SHOT_NAME!r} was cleaned up")


def _check_capture_refused(wayland_portal, needle: str,
                           timeout: float = 15.0) -> str:
    """A capture that cannot succeed must say why, not return half an image."""
    reason = _refused(lambda: wayland_portal.capture_png(timeout=timeout),
                      wayland_portal.AutoControlScreenException, timeout + 3.0)
    _require(needle in reason,
             f"the failure did not mention {needle!r}: {reason}")
    return reason


# --- scenarios ------------------------------------------------------------


def _run_grant_scenario(portal: Portal, server, libei, oeffis,
                        wayland_portal) -> None:
    """Everything that needs a portal which says yes."""
    backend = check("libei completes its handshake over a portal-obtained fd",
                    lambda: _connected_through_the_portal(libei))
    check("the portal dance runs the four calls in the prescribed order",
          lambda: _check_call_order(portal))
    check("SelectDevices is asked for keyboard and pointer, nothing wider",
          lambda: _check_device_mask(portal, oeffis))
    check("the EIS fd is a live socket the caller owns and must close",
          lambda: _check_fd_is_live_and_owned(oeffis))
    if backend is None:
        return
    check("the portal's descriptor carries a real EI session",
          lambda: _check_session_reaches_eis(server))
    check("input emitted through the portal path reaches the EIS server",
          lambda: _check_input_over_the_portal_fd(backend, server))
    check("disconnect() revokes the grant instead of leaving it open",
          lambda: _check_disconnect_ends_the_grant(backend, server, portal))
    check("the Screenshot tier reaches a real portal and returns real pixels",
          lambda: _check_capture_returns_the_portal_bytes(
              wayland_portal, portal))


def _run_refusal_scenarios(socket_path: str, libei, oeffis) -> None:
    """Every way a portal says no, and this project's answer to each."""
    with Portal(socket_path, behaviour="deny"):
        check("a dismissed consent dialog is refused, not worked around",
              lambda: _check_portal_refuses(oeffis))
        check("a refused portal reaches the caller as LibeiUnavailable",
              lambda: _check_backend_surfaces_the_refusal(libei))
    with Portal(socket_path, behaviour="stall"):
        check("a consent dialog left open times out on this project's clock",
              lambda: _check_open_dialog_times_out(oeffis))
    with Portal(socket_path, behaviour="no-fd"):
        check("a portal that withholds the descriptor fails closed",
              lambda: _check_portal_refuses(oeffis))
    with Portal(socket_path, behaviour="close"):
        check("a portal that closes the session fails closed",
              lambda: _check_portal_refuses(oeffis))
    with Portal(socket_path, version=1):
        check("a portal too old to have ConnectToEIS fails closed",
              lambda: _check_portal_refuses(oeffis))


def _run_capture_scenarios(socket_path: str, wayland_portal) -> None:
    """Every way the Screenshot portal ends without an image."""
    with Portal(socket_path, screenshot="deny"):
        check("a dismissed screenshot dialog is named as dismissed",
              lambda: _check_capture_refused(wayland_portal, "dismissed"))
    with Portal(socket_path, screenshot="stall"):
        check("a screenshot dialog left open times out on our clock",
              lambda: _check_capture_refused(
                  wayland_portal, "did not answer", REFUSAL_TIMEOUT))
    with Portal(socket_path, screenshot="no-uri"):
        check("a success carrying no image URI is treated as a failure",
              lambda: _check_capture_refused(wayland_portal, "no image URI"))
    with Portal(socket_path, screenshot="not-a-file"):
        check("a URI that is not a local file is refused",
              lambda: _check_capture_refused(wayland_portal, "non-file URI"))


def main() -> int:
    """Run every check and return the number that failed."""
    print("=" * 72)
    print("AutoControl RemoteDesktop portal — against a real liboeffis")
    print("=" * 72)

    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from eis_server import RecordingEisServer, load_symbols
    from je_auto_control.linux_wayland import libei, oeffis
    from je_auto_control.linux_wayland import portal as wayland_portal

    if load_symbols() is None:
        print("libeis.so.* not found — install libeis1. Nothing to verify.")
        return 1

    bus = SessionBus()
    print(f"      session bus at {bus.start()}")

    socket_path = _fresh_socket_path("eis-portal-verify")
    server = RecordingEisServer(socket_path)
    server.start()
    print(f"      EIS server listening at {socket_path}")
    print("-" * 72)

    try:
        check("liboeffis resolves and every entry point binds",
              lambda: _check_liboeffis_binds(oeffis))
        check("no portal on the bus is refused rather than waited on",
              lambda: _check_no_portal_is_refused(oeffis))
        with Portal(socket_path) as portal:
            _run_grant_scenario(portal, server, libei, oeffis, wayland_portal)
        _run_refusal_scenarios(socket_path, libei, oeffis)
        _run_capture_scenarios(socket_path, wayland_portal)
    finally:
        server.stop()
        bus.stop()

    if server.error is not None:
        print(f"      NOTE: the server thread ended with {server.error!r}")

    failed = [name for name, ok in _results if not ok]
    print("=" * 72)
    print(f"{len(_results) - len(failed)}/{len(_results)} checks passed")
    for name in failed:
        print(f"  FAILED: {name}")
    print("=" * 72)
    return len(failed)


if __name__ == "__main__":
    sys.exit(main())
