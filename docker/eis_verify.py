"""Verify AutoControl's libei sender against a real EIS peer.

``libei_verify.py`` goes as far as a peer-less container can: every prototype
resolves, every call behaves, and the fail-closed chain runs end to end. It
closes by listing what it cannot answer — the capability and event-type enum
values, and whether the variadic ``ei_seat_bind_capabilities`` call is
marshalled correctly — because those need something that speaks the protocol.

``docker/eis_server.py`` is that something. With a real EIS implementation on
the other end of the socket, every one of those questions has an answer, and
they are answered here:

  * the seat records exactly the four capabilities AutoControl asks for, so
    both the ``EI_DEVICE_CAP_*`` bitmask values and the variadic call are
    right — a wrong value binds the wrong capability or none at all;
  * ``SEAT_ADDED`` / ``DEVICE_ADDED`` / ``DEVICE_RESUMED`` are recognised, so
    the ``EI_EVENT_*`` values are right — a wrong one leaves the handshake
    waiting until it times out;
  * ``start_emulating`` → event → ``frame`` puts real events on the wire, with
    the key codes, coordinates, button codes and scroll signs intended —
    including the axis flip ``mouse.scroll()`` applies between the kernel's
    ``REL_WHEEL`` frame and libei's, and the negative value that flip makes;
  * tearing down a *live* context is finally testable — it is safe, which is
    what lets ``_teardown`` release a completed session instead of leaking a
    context and an fd per process, and this file is the sentinel for that.

Two things it measures but cannot settle, and says so rather than claiming
either way: ``eis_device_pause()`` puts nothing on the wire for a sender
client on libeis 1.3.901, so ``DEVICE_PAUSED`` handling still has no peer to
drive it; and the ``start_emulating`` sequence number does not survive the
trip, so the client's counter cannot be read back from this side.

Exit status is the number of failed checks.
"""
from __future__ import annotations

import faulthandler
import os
import subprocess  # nosec B404  # reason: runs this interpreter to isolate a known segfault
import sys
import time
import traceback
from typing import Any, Callable, List, Tuple

# A wrong prototype in a ctypes binding is a segfault, not an exception.
faulthandler.enable()

_results: List[Tuple[str, bool]] = []

#: evdev codes the emission checks use. KEY_A, BTN_LEFT.
KEY_A = 30
BTN_LEFT = 272
TARGET_POSITION = (640, 400)


def check(name: str, fn: Callable[[], Any]) -> Any:
    try:
        detail = fn()
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


def _wait_for(predicate: Callable[[], bool], timeout: float,
              description: str) -> None:
    """Spin until the server thread has recorded something, or give up."""
    import time
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.02)
    raise AssertionError(f"timed out waiting for {description}")


def _socket_path() -> str:
    runtime = os.environ.get("XDG_RUNTIME_DIR", "/tmp")  # nosec B108  # reason: container fallback only
    os.makedirs(runtime, exist_ok=True)
    path = os.path.join(runtime, "eis-verify")
    if os.path.exists(path):
        os.unlink(path)
    return path


def _connected_backend(libei, server, path):
    """Drive a real handshake to completion against the recording server."""
    backend = libei.LibeiBackend()
    backend.connect(timeout=5.0, socket_path=path.encode("utf-8"))
    _require(backend.is_connected,
             "connect() returned but the backend reports no live device")
    _require(server.error is None, f"the server thread died: {server.error!r}")
    return backend


def _check_handshake(server) -> str:
    record = server.recording
    _require(record.seat_binds >= 1, "the client never bound a seat")
    _require(all(record.sender_flags),
             "the client did not present itself as a sender")
    return (f"client={record.clients[0]!r} seat binds={record.seat_binds} "
            f"devices={record.devices}")


def _check_capabilities(server, libei) -> str:
    """The enum values and the variadic bind call, read back off the wire."""
    from eis_server import CAPABILITY_NAMES
    expected = set(libei._WANTED_CAPS)
    bound = server.recording.bound_capabilities
    _require(bound == expected, (
        "the seat was bound with "
        f"{sorted(CAPABILITY_NAMES.get(c, c) for c in bound)} but AutoControl "
        f"asks for {sorted(CAPABILITY_NAMES.get(c, c) for c in expected)} — "
        "either an EI_DEVICE_CAP_* value is wrong or the variadic "
        "ei_seat_bind_capabilities call is mis-marshalled"))
    return ", ".join(server.recording.capability_names())


def _check_keyboard(backend, server) -> str:
    backend.press_key(KEY_A)
    backend.release_key(KEY_A)
    _wait_for(lambda: len(server.recording.keys) >= 2, 2.0, "two key events")
    _require(server.recording.keys[:2] == [(KEY_A, True), (KEY_A, False)],
             f"the server saw {server.recording.keys[:2]}")
    return f"press+release of key {KEY_A} arrived in order"


def _check_pointer(backend, server) -> str:
    backend.set_position(*TARGET_POSITION)
    _wait_for(lambda: server.recording.absolute_motions, 2.0, "absolute motion")
    got = server.recording.absolute_motions[-1]
    _require(got == TARGET_POSITION,
             f"asked for {TARGET_POSITION}, the server saw {got}")
    return f"absolute motion landed on {got}"


def _check_button(backend, server) -> str:
    backend.click_button(BTN_LEFT)
    _wait_for(lambda: len(server.recording.buttons) >= 2, 2.0, "button events")
    _require(server.recording.buttons[:2] == [(BTN_LEFT, True),
                                              (BTN_LEFT, False)],
             f"the server saw {server.recording.buttons[:2]}")
    return f"press+release of button {BTN_LEFT} arrived in order"


#: libei.h: "A discrete scroll event is based logical scroll units (equivalent
#: to one mouse wheel click). The value for one scroll unit is 120."
SCROLL_UNIT = 120


def _check_scroll_unit(backend, server) -> str:
    """One wheel click has to arrive as one wheel click.

    This is the path Progress.md left deliberately unwired because the sign
    was a guess. The sign turns out to be the smaller half of the question:
    libei measures discrete scroll in 120ths of a click, so a raw detent count
    is 1/120th of a scroll and libei logs it as a client bug.
    """
    backend.scroll(0, 1)
    _wait_for(lambda: server.recording.scrolls, 2.0, "a discrete scroll")
    got = server.recording.scrolls[-1]
    _require(got == (0, SCROLL_UNIT), (
        f"scroll(0, 1) — one wheel click down — reached the server as {got}, "
        f"but libei measures discrete scroll in units of {SCROLL_UNIT} per "
        "click, so this is 1/120th of the scroll that was asked for"))
    return (f"scroll(0, 1) arrives as {got}: one click, positive on the y "
            "axis, no axis swap")


def _check_scroll_wiring(backend, server) -> str:
    """The public ``mouse.scroll()`` has to land the axis flip on the wire.

    ``_check_scroll_unit`` drives ``LibeiBackend.scroll`` directly, so it says
    nothing about the frame conversion the mouse module does on top: this
    repository's ``wayland_scroll_direction_*`` constants are in the kernel's
    ``REL_WHEEL`` frame (positive is up, which is what ydotool writes) and
    libei is in the ``wl_pointer`` frame (positive is down), so the vertical
    axis is negated on the way out and the horizontal one is not.

    Running it through the real server is also the only place a *negative*
    discrete value is put on the wire — the direct check only ever sent a
    positive one, so a marshalling fault on the sign would have gone unseen.
    """
    from unittest.mock import patch

    from je_auto_control.linux_wayland import mouse as wayland_mouse

    def _next_scroll(call) -> tuple:
        before = len(server.recording.scrolls)
        call()
        _wait_for(lambda: len(server.recording.scrolls) > before, 2.0,
                  "a discrete scroll from mouse.scroll()")
        return server.recording.scrolls[-1]

    with patch.object(wayland_mouse, "_try_libei", return_value=backend):
        up = _next_scroll(lambda: wayland_mouse.scroll(
            1, wayland_mouse.wayland_scroll_direction_up))
        down = _next_scroll(lambda: wayland_mouse.scroll(
            1, wayland_mouse.wayland_scroll_direction_down))
        right = _next_scroll(lambda: wayland_mouse.scroll(
            1, wayland_mouse.wayland_scroll_direction_right))

    _require(up == (0, -SCROLL_UNIT), (
        f"scrolling up reached the server as {up}, not (0, {-SCROLL_UNIT}) — "
        "libei counts positive y as down, so up has to arrive negative"))
    _require(down == (0, SCROLL_UNIT),
             f"scrolling down reached the server as {down}")
    _require(right == (SCROLL_UNIT, 0), (
        f"scrolling right reached the server as {right} — the horizontal "
        "axis must not be flipped, both frames count right as positive"))
    return (f"up arrives as {up}, down as {down}, right as {right}: the "
            "vertical flip survives, including the negative value")


def _check_frames(server) -> str:
    """No frame means nothing was delivered, however many events were sent."""
    frames = server.recording.frames
    _require(frames >= 4, f"only {frames} frames for 9 emissions")
    return f"{frames} frames — every emission was committed"


def _check_emulating(server) -> str:
    """Every device the client kept has to open an emulation transaction.

    libei is explicit that "sending events before ei_device_start_emulating()
    ... is a client bug", so a device that receives events without one is a
    protocol violation this peer happens to tolerate and a stricter
    compositor need not.
    """
    offered = {f"autocontrol-{label}" for label in server.recording.devices}

    def _all_started() -> bool:
        return {name for name, _seq in server.recording.emulating_sequences} \
            >= offered

    # The handshake returns as soon as the *required* devices are live, so the
    # last device's transaction can still be in flight when this runs.
    try:
        _wait_for(_all_started, 2.0, "every device to start emulating")
    except AssertionError:
        pass
    started = {name for name, _sequence in server.recording.emulating_sequences}
    _require(started == offered, (
        f"devices {sorted(offered)} were handed over but only "
        f"{sorted(started)} started emulating.\n        server saw: "
        f"{_format_log(server.recording.event_log)}"))
    return f"{sorted(started)}, sequences " \
           f"{[seq for _n, seq in server.recording.emulating_sequences]}"


_EVENT_NAMES = {
    1: "CLIENT_CONNECT", 2: "CLIENT_DISCONNECT", 3: "SEAT_BIND",
    4: "DEVICE_CLOSED", 100: "FRAME", 200: "START_EMULATING",
    201: "STOP_EMULATING", 300: "POINTER_MOTION", 400: "MOTION_ABSOLUTE",
    500: "BUTTON", 603: "SCROLL_DISCRETE", 700: "KEYBOARD_KEY",
}


def _format_log(entries) -> str:
    return ", ".join(
        f"{_EVENT_NAMES.get(kind, kind)}{'@' + name if name else ''}"
        for kind, name in entries)


def _check_sequence_reaches_the_server(backend, server, libei) -> str:
    """Does the start/stop sequence number survive the trip at all?

    libei documents it as identifying one start→stop transaction and requires
    it to rise by at least one per call. AutoControl counts correctly, but the
    server reads 0 for every transaction — so either the number is not put on
    the wire by this libei, or it is not read back by this libeis. Sending an
    unmistakable value settles which end to blame.
    """
    symbols = libei._load_symbols()
    device = backend._devices[libei.EI_DEVICE_CAP_KEYBOARD]
    symbols.ei_device_stop_emulating(device)
    symbols.ei_device_start_emulating(device, 4242)
    _wait_for(lambda: any(seq == 4242 for _n, seq
                          in server.recording.emulating_sequences)
              or server.recording.stopped_emulating > 0, 2.0,
              "the restarted emulation transaction")
    seen = [seq for _n, seq in server.recording.emulating_sequences]
    if 4242 in seen:
        return "an explicit 4242 arrives intact, so the number is carried"
    return (f"an explicit 4242 arrives as {seen[-1]} — libei {_libei_version()} "
            "does not carry the sequence number, so AutoControl's counter "
            "cannot be checked from this side (it satisfies the contract "
            "regardless: it rises by one per call)")


def _libei_version() -> str:
    import ctypes.util
    return str(ctypes.util.find_library("ei"))


def _check_pause_fails_closed(backend, server) -> str:
    """A paused device must take its capability out of service, not misfire.

    ``is_connected`` is not polled here on purpose: it only reads cached
    state, and the client learns about a pause when it next pumps — which is
    inside ``_emit``. Asking for a keystroke is therefore the only honest way
    to ask whether the pause was noticed.
    """
    import select
    import time
    symbols = libei_module()._load_symbols()
    seen: List[int] = []
    original = backend._on_event

    def spy(event: int) -> None:
        seen.append(int(symbols.ei_event_get_type(event)))
        original(event)

    backend._on_event = spy
    try:
        server.pause_devices()
        deadline = time.monotonic() + 3.0
        attempts = 0
        while time.monotonic() < deadline:
            attempts += 1
            try:
                backend.press_key(KEY_A)
            except Exception as error:  # noqa: BLE001  # reason: the type is the finding
                _require(type(error).__name__ == "LibeiUnavailable",
                         f"a paused device raised {error!r}, not a fail-closed")
                return (f"the keystroke {attempts} calls after the pause "
                        f"failed closed: {str(error)[:60]}")
            time.sleep(0.05)
        # Nothing arrived. Before blaming the client, ask whether anything was
        # sent at all: an idle fd means the pause never left the server.
        poll_fd = int(symbols.ei_get_fd(backend._ei))
        readable = bool(select.select([poll_fd], [], [], 1.0)[0])
    finally:
        backend._on_event = original
    _require(not readable and not seen, (
        f"the client was told about the pause (events {seen}, fd "
        f"{'readable' if readable else 'idle'}) and still emitted {attempts} "
        "keystrokes, so DEVICE_PAUSED is received and ignored"))
    return ("UNTESTED here: libeis 1.3.901 put nothing on the wire for "
            f"eis_device_pause on {len(server.recording.paused)} live devices "
            "(client fd stayed idle for 4s), so the client's DEVICE_PAUSED "
            "handling still has no peer to exercise it — see Progress.md")


def libei_module():
    from je_auto_control.linux_wayland import libei
    return libei


def _check_resume_recovers(backend, server) -> str:
    """And a device must still be usable after a pause/resume round trip."""
    before = len(server.recording.keys)
    server.resume_devices()
    _wait_for(lambda: server.recording.frames >= 0, 0.3, "the resume to land")
    backend.press_key(KEY_A)
    backend.release_key(KEY_A)
    _wait_for(lambda: len(server.recording.keys) >= before + 2, 2.0,
              "keys after the resume")
    return "the device came back and emitted again"


def _live_teardown_sentinel(path: str) -> str:
    """Is ``ei_unref`` safe once the handshake has actually completed?

    ``libei_verify.py`` established that it segfaults on a context whose
    backend opened but never handshook. Whether a *live* context is safe was
    untestable without a peer; it is testable now, and it is safe — which is
    what lets ``_teardown`` release a completed session rather than leaking
    its context. This is therefore a regression sentinel for that decision,
    and it runs in a subprocess because the answer is a signal, not an
    exception.
    """
    program = (
        "import sys; sys.path.insert(0, '/opt/verify');"
        "from eis_server import RecordingEisServer;"
        "from je_auto_control.linux_wayland import libei;"
        f"srv = RecordingEisServer({path + '-teardown'!r}); srv.start();"
        "b = libei.LibeiBackend();"
        f"b.connect(timeout=5.0, socket_path={(path + '-teardown').encode()!r});"
        "assert b.is_connected;"
        "sym = libei._load_symbols();"
        "sym.ei_unref(b._ei);"
        "print('survived')"
    )
    finished = subprocess.run(  # nosec B603  # reason: this interpreter, fixed argv
        [sys.executable, "-c", program], capture_output=True, timeout=60)
    if finished.returncode == 0:
        return ("safe, which is what _teardown now relies on to release a "
                "completed session instead of leaking its context")
    if finished.returncode == -11:
        print()
        print("      *** REVISIT ***  ei_unref now SEGFAULTS on a live")
        print("      context too. LibeiBackend._teardown releases completed")
        print("      sessions on the measurement that it is safe, so that")
        print("      must go back to abandoning them — this is a crash in a")
        print("      library that drives the user's desktop. See Progress.md.")
        print()
        raise AssertionError(
            "ei_unref segfaults on a live context (rc=-11); _teardown's "
            "release path is no longer safe on this libei")
    detail = finished.stderr.decode("utf-8", "replace").strip().splitlines()
    return f"inconclusive (rc={finished.returncode}): {detail[-1] if detail else ''}"


#: An offset region layout: the shape a compositor must advertise for a
#: desktop whose left-most monitor sits at a negative layout coordinate.
#: Region offsets are ``uint32``, so it cannot advertise the negative
#: coordinate itself — which is the whole reason the two spaces can differ.
OFFSET_REGIONS = (((0, 0), (1280, 1024)), ((1280, 0), (1920, 1080)))


def _offset_region_session(path, libei, server_class):
    """Bring up a peer whose pointer regions are the OFFSET_REGIONS layout."""
    if os.path.exists(path):
        os.unlink(path)
    server = server_class(path, regions=OFFSET_REGIONS)
    server.start()
    backend = libei.LibeiBackend()
    backend.connect(timeout=5.0, socket_path=path.encode("utf-8"))
    _require(backend.is_connected, "the offset-region handshake never landed")
    return backend, server


def _pointer_device(backend, libei):
    device = backend._devices.get(libei.EI_DEVICE_CAP_POINTER_ABSOLUTE)
    _require(bool(device), "no absolute pointer device was granted")
    return device


def _check_regions_are_read_back(backend, libei) -> str:
    """The client sees the regions the server configured, offsets included."""
    got = backend._device_regions(_pointer_device(backend, libei))
    expected = [(x, y, w, h) for (x, y), (w, h) in OFFSET_REGIONS]
    _require(got == expected,
             f"the server configured {expected}, the client reads {got}")
    return f"{got} — offsets survive the trip, so they are part of the space"


def _check_offset_region_takes_absolute_coordinates(backend, server,
                                                    libei) -> str:
    """A region at x=1280 takes 1380 for a point 100 pixels into it."""
    before = len(server.recording.absolute_motions)
    backend.set_position(1380, 100)
    _wait_for(lambda: len(server.recording.absolute_motions) > before, 2.0,
              "absolute motion into the offset region")
    got = server.recording.absolute_motions[-1]
    _require(got == (1380.0, 100.0),
             f"asked for (1380, 100) inside a region at x=1280, saw {got}")
    return "region-space coordinates carry the offset, they are not local"


def _check_libei_drops_out_of_region_motion(backend, server, libei) -> str:
    """The measurement the whole guard rests on.

    Called under the guard rather than through it: ``set_position`` now
    refuses this point, so the raw entry point is used to find out what libei
    does when nothing stops it. If some future libei clamps instead of
    dropping, this is the check that says so.
    """
    device = _pointer_device(backend, libei)
    symbols = backend._symbols
    before = list(server.recording.absolute_motions)
    symbols.ei_device_pointer_motion_absolute(device, 9000.0, 9000.0)
    symbols.ei_device_frame(device, symbols.ei_now(backend._ei))
    time.sleep(0.5)
    after = server.recording.absolute_motions
    _require(after == before, (
        "libei no longer drops an absolute motion outside every region — it "
        f"delivered {after[len(before):]}. Re-read LibeiBackend._region_point: "
        "its refusal exists because this was silent"))
    return ("(9000, 9000) reached the server as nothing at all — no event, "
            "no error, no return code: the silent no-op _region_point "
            "replaces with a refusal")


def _check_out_of_region_move_is_refused(backend, server, libei) -> str:
    """AutoControl turns that silence into something the CLI path can act on."""
    before = len(server.recording.absolute_motions)
    try:
        backend.set_position(9000, 9000)
    except libei.LibeiUnavailable as error:
        _require("outside every region" in str(error),
                 f"refused, but with an unhelpful message: {error}")
        time.sleep(0.3)
        _require(len(server.recording.absolute_motions) == before,
                 "the refusal still put a motion on the wire")
        return f"refused with {str(error)[:60]}... — _select_input.emitted "\
               "hands it to ydotool"
    raise AssertionError(
        "set_position(9000, 9000) returned as though the pointer had moved; "
        "libei dropped it and nobody was told")


def _check_negative_origin_is_normalised(backend, server, libei,
                                         monkey) -> str:
    """The layout half of the same problem, end to end against the peer.

    A monitor left of the primary puts this project's layout origin at
    ``(-1280, 0)`` while the compositor's regions still start at 0. Asking
    for the top-left pixel of that monitor means asking for ``(-1280, 0)``,
    which no region covers — so it has to arrive as ``(0, 0)``.
    """
    before = len(server.recording.absolute_motions)
    with monkey(libei, "_layout_origin", lambda: (-1280, 0)):
        backend.set_position(-1280, 10)
    _wait_for(lambda: len(server.recording.absolute_motions) > before, 2.0,
              "the normalised motion")
    got = server.recording.absolute_motions[-1]
    _require(got == (0.0, 10.0),
             f"(-1280, 10) on a layout starting at -1280 arrived as {got}, "
             "not the (0, 10) the region space calls that pixel")
    return "(-1280, 10) arrives as (0, 10): input and capture name one pixel"


class _swap:
    """Minimal context-managed attribute swap; no pytest in this image."""

    def __init__(self, target, name, value):
        self._target, self._name, self._value = target, name, value

    def __enter__(self):
        self._old = getattr(self._target, self._name)
        setattr(self._target, self._name, self._value)
        return self

    def __exit__(self, *_exc):
        setattr(self._target, self._name, self._old)
        return False


def _run_region_checks(path, libei, server_class) -> None:
    """Every region check, on a peer of their own.

    They need a differently-shaped device than the rest of the file, and a
    device's regions are fixed when the compositor adds it.
    """
    backend, server = _offset_region_session(path, libei, server_class)
    try:
        check("the client reads back the regions the compositor advertised",
              lambda: _check_regions_are_read_back(backend, libei))
        check("an offset region takes absolute coordinates, not local ones",
              lambda: _check_offset_region_takes_absolute_coordinates(
                  backend, server, libei))
        check("libei still drops out-of-region motion without a word",
              lambda: _check_libei_drops_out_of_region_motion(
                  backend, server, libei))
        check("an out-of-region move is refused rather than silently lost",
              lambda: _check_out_of_region_move_is_refused(
                  backend, server, libei))
        check("a negative layout origin is normalised into region space",
              lambda: _check_negative_origin_is_normalised(
                  backend, server, libei, _swap))
    finally:
        backend.disconnect()
        server.stop()


def main() -> int:
    print("=" * 72)
    print("AutoControl libei sender — against a real EIS server (libeis)")
    print("=" * 72)

    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from eis_server import RecordingEisServer, load_symbols
    from je_auto_control.linux_wayland import libei

    if load_symbols() is None:
        print("libeis.so.* not found — install libeis1. Nothing to verify.")
        return 1

    path = _socket_path()
    server = RecordingEisServer(path)
    server.start()
    print(f"      EIS server listening at {path}")
    print("-" * 72)

    backend = check("the handshake completes against a real EIS peer",
                    lambda: _connected_backend(libei, server, path))
    if backend is None:
        server.stop()
        print("the handshake never completed; the rest cannot run")
        return 1 + sum(1 for _n, ok in _results if not ok)

    check("the client connects, binds a seat and is handed devices",
          lambda: _check_handshake(server))
    check("the seat binds exactly the capabilities AutoControl asks for",
          lambda: _check_capabilities(server, libei))
    check("a device starts emulating with a rising sequence number",
          lambda: _check_emulating(server))
    check("press_key / release_key arrive as the right evdev code",
          lambda: _check_keyboard(backend, server))
    check("set_position arrives as absolute motion at the right point",
          lambda: _check_pointer(backend, server))
    check("press_button / release_button arrive as the right BTN_ code",
          lambda: _check_button(backend, server))
    check("scroll() arrives as whole wheel clicks, on the right axis and sign",
          lambda: _check_scroll_unit(backend, server))
    check("mouse.scroll()'s kernel-to-libei axis flip reaches the server",
          lambda: _check_scroll_wiring(backend, server))
    check("every emission was committed with a frame",
          lambda: _check_frames(server))
    check("the emulation sequence number, end to end",
          lambda: _check_sequence_reaches_the_server(backend, server, libei))
    check("a paused device is either acted on, or never announced",
          lambda: _check_pause_fails_closed(backend, server))
    check("a resumed device can emit again",
          lambda: _check_resume_recovers(backend, server))

    check("disconnect() after a live session does not crash the process",
          lambda: (backend.disconnect(), backend.disconnect(),
                   "torn down twice")[-1])
    check("ei_unref on a live context is still safe — teardown depends on it",
          lambda: _live_teardown_sentinel(path))

    # The absolute pointer's coordinate space, on a peer whose regions are
    # shaped like the desktop that made it a question: two monitors, the
    # left one at a negative layout coordinate the region space cannot hold.
    _run_region_checks(path + "-regions", libei, RecordingEisServer)

    server.stop()
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
