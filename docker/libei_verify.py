"""Verify AutoControl's libei binding against the real ``libei.so``.

No compositor is needed for this half. What the unit tests cannot check —
because they inject a fake symbol table — is whether the entry points this
binding names actually exist in the shared object, with the signatures it
declares. A single misspelled name or a wrong ``argtypes`` would sail past
every mock and only surface on a user's machine.

So: resolve every prototype against the installed library, then drive
``connect()`` at a socket that accepts the connection but speaks no EI. The
handshake cannot complete, and that is the point — the fail-closed promise
("anything short of a live device means use the ydotool CLI") is checked
here against the real library rather than asserted about a mock.

What this half cannot answer is anything a peer has to *agree* with: the
capability and event-type enum values, the variadic
``ei_seat_bind_capabilities`` call, and whether emission puts anything on the
wire. ``docker/eis_verify.py`` answers those by running a real libeis server
on the other end of the socket.

Exit status is the number of failed checks.
"""
from __future__ import annotations

import ctypes.util
import faulthandler
import os
import socket
import sys
import threading
import traceback
from typing import Any, Callable, List, Tuple

# A wrong prototype in a ctypes binding shows up as a segfault, not as an
# exception, and a segfault with no traceback is the hardest kind of bug to
# act on. faulthandler turns it into a Python stack ending at the exact call.
faulthandler.enable()

_results: List[Tuple[str, bool]] = []


def check(name: str, fn: Callable[[], Any]) -> Any:
    try:
        detail = fn()
    except Exception:  # noqa: BLE001  # reason: one failed check must not stop the rest
        _results.append((name, False))
        print(f"FAIL  {name}")
        print("        " + traceback.format_exc(limit=3).strip().replace(
            "\n", "\n        "))
        return None
    _results.append((name, True))
    print(f"ok    {name}" + (f"  — {detail}" if detail else ""))
    return detail


def serve_silent_socket(path: str) -> socket.socket:
    """Accept connections at ``path`` and then say nothing at all.

    libei will connect and begin its handshake; nothing answers, so the
    client has to give up on its own deadline rather than hang.
    """
    if os.path.exists(path):
        os.unlink(path)
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(path)
    server.listen(4)

    def accept_forever() -> None:
        held = []
        while True:
            try:
                conn, _ = server.accept()
            except OSError:
                return
            held.append(conn)  # keep it open; never write

    threading.Thread(target=accept_forever, daemon=True).start()
    return server


def main() -> int:
    print("=" * 72)
    print("AutoControl libei binding — against the real libei.so")
    print("=" * 72)

    resolved = ctypes.util.find_library("ei")
    print(f"find_library('ei')       = {resolved!r}")
    print(f"find_library('oeffis')   = {ctypes.util.find_library('oeffis')!r}")
    print("-" * 72)

    from je_auto_control.linux_wayland import _select_input, libei, oeffis
    from je_auto_control.linux_wayland import keyboard as wl_keyboard

    # --- the check the mocks structurally cannot make --------------------
    def _symbols():
        symbols = libei._load_symbols()
        if symbols is None:
            raise AssertionError(
                "not one prototype resolved — either libei.so is absent or a "
                "name in _PROTOTYPES does not exist in it")
        missing = [name for name, _, _ in libei._PROTOTYPES
                   if not hasattr(symbols, name)]
        if missing:
            raise AssertionError(f"unresolved entry points: {missing}")
        # The variadic one is bound separately, without argtypes.
        if not hasattr(symbols, "ei_seat_bind_capabilities"):
            raise AssertionError("ei_seat_bind_capabilities did not resolve")
        return f"{len(libei._PROTOTYPES)} prototypes + 1 variadic, all resolved"
    check("every libei entry point this binding names exists", _symbols)

    check("LibeiBackend reports the library as available",
          lambda: _assert_true(libei.LibeiBackend().is_available,
                               "is_available was False with libei installed"))

    # --- liboeffis: packaged separately, so easily absent ----------------
    # Debian does package it (liboeffis1 on trixie), but as its own binary
    # package that libei1 does not depend on — so installing libei alone
    # leaves the portal route off, which is the state this image is in and
    # the state a user who installed one package would be in.
    available = oeffis.is_available()
    print(f"      liboeffis available here: {available}")
    if not available:
        print("      (liboeffis is not installed here, so the portal route is")
        print("       unavailable and connect() falls back to the socket —")
        print("       which is exactly the path exercised below. The portal")
        print("       route itself is covered by docker/portal_verify.py.)")

    # --- a real sender against a socket that speaks no EI ----------------
    runtime = os.environ.get("XDG_RUNTIME_DIR", "/tmp")
    socket_path = os.path.join(runtime, "eis-0")
    server = serve_silent_socket(socket_path)
    print(f"      silent EIS stand-in listening at {socket_path}")

    # --- raw, one call at a time -----------------------------------------
    # connect() is half a dozen library calls deep. Walking them by hand with
    # flushed output means a crash names the call that caused it instead of
    # just the function that contained it.
    def _raw_walk():
        symbols = libei._load_symbols()
        step = lambda msg: print(f"        · {msg}", flush=True)  # noqa: E731

        step("ei_new_sender(None) ...")
        handle = symbols.ei_new_sender(None)
        step(f"  -> {handle!r}")
        if not handle:
            raise AssertionError("ei_new_sender returned NULL")

        step(f"ei_setup_backend_socket(handle, {socket_path!r}) ...")
        code = symbols.ei_setup_backend_socket(
            handle, socket_path.encode("utf-8"))
        step(f"  -> {code}")

        step("ei_get_fd(handle) ...")
        poll_fd = symbols.ei_get_fd(handle)
        step(f"  -> {poll_fd}")

        step("ei_dispatch(handle) ...")
        symbols.ei_dispatch(handle)
        step("  -> returned")

        step("ei_get_event(handle) ...")
        event = symbols.ei_get_event(handle)
        step(f"  -> {event!r}")
        while event:
            kind = symbols.ei_event_get_type(event)
            step(f"  event type {kind}")
            symbols.ei_event_unref(event)
            event = symbols.ei_get_event(handle)
            step(f"  next -> {event!r}")

        # ei_unref is NOT called here: on this libei it segfaults once the
        # backend is open. The sentinel below establishes that separately,
        # in a subprocess, so it cannot take this run down with it.
        step("(context abandoned — see the ei_unref sentinel)")
        return "every call up to teardown behaves"
    check("each libei call in isolation", _raw_walk)

    # --- the upstream defect this binding works around -------------------
    def _unref_sentinel():
        import subprocess
        program = (
            "import ctypes, ctypes.util, os, socket, threading;"
            "lib = ctypes.CDLL(ctypes.util.find_library('ei'));"
            "lib.ei_new_sender.restype = ctypes.c_void_p;"
            "lib.ei_new_sender.argtypes = (ctypes.c_void_p,);"
            "lib.ei_setup_backend_socket.restype = ctypes.c_int;"
            "lib.ei_setup_backend_socket.argtypes = "
            "(ctypes.c_void_p, ctypes.c_char_p);"
            "lib.ei_unref.restype = ctypes.c_void_p;"
            "lib.ei_unref.argtypes = (ctypes.c_void_p,);"
            f"p = {socket_path!r};"
            "s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM);"
            "s.connect(p);"
            "h = lib.ei_new_sender(None);"
            "rc = lib.ei_setup_backend_socket(h, p.encode());"
            "assert rc == 0, rc;"
            "lib.ei_unref(h)"
        )
        finished = subprocess.run([sys.executable, "-c", program],
                                  capture_output=True)
        if finished.returncode == -11:
            return ("still segfaults (rc=-11), so the abandon-on-teardown "
                    "workaround in libei.py::_teardown is still required")
        print()
        print("      *** REVISIT ***  ei_unref no longer crashes on this")
        print("      libei (rc=%s). The workaround in LibeiBackend._teardown"
              % finished.returncode)
        print("      can probably go; see Progress.md.")
        print()
        return f"no longer crashes (rc={finished.returncode}) — see above"
    check("ei_unref after a successful setup — upstream state", _unref_sentinel)

    def _connect_fails_closed():
        backend = libei.LibeiBackend()
        try:
            backend.connect(timeout=1.0,
                            socket_path=socket_path.encode("utf-8"))
        except libei.LibeiUnavailable as error:
            return f"LibeiUnavailable: {str(error)[:90]}"
        raise AssertionError(
            "connect() reported success against a peer that sent nothing, so "
            "the handshake is not actually gating on a live device")
    check("connect() against a silent peer fails closed, not open",
          _connect_fails_closed)

    def _no_crash_on_teardown():
        backend = libei.LibeiBackend()
        try:
            backend.connect(timeout=0.5,
                            socket_path=socket_path.encode("utf-8"))
        except libei.LibeiUnavailable:
            pass
        backend.disconnect()          # must be safe after a failed connect
        backend.disconnect()          # and idempotent
        return "teardown survived a failed connect, twice"
    check("teardown after a failed handshake does not crash the process",
          _no_crash_on_teardown)

    # --- the fallback the whole design rests on --------------------------
    libei.reset_default_backend()
    check("active_backend() gives up and hands over to the CLI",
          lambda: _assert_true(_select_input.active_backend() is None,
                               "active_backend() returned a backend that "
                               "cannot emit"))

    def _keyboard_falls_back():
        # ydotool is deliberately not installed in this image, so the CLI
        # path must surface its install hint — not a libei error and not a
        # silent no-op.
        try:
            wl_keyboard.press_key(30)
        except Exception as error:  # noqa: BLE001  # reason: any type is informative
            if "ydotool" in str(error):
                return f"{type(error).__name__}: {str(error)[:60]}"
            raise
        raise AssertionError("press_key claimed success with no libei and no "
                             "ydotool")
    check("press_key falls through to the ydotool CLI path",
          _keyboard_falls_back)

    server.close()

    print("-" * 72)
    print("Not covered here, because it needs a peer that speaks EI:")
    print("      the capability / event-type enum values, the variadic")
    print("      ei_seat_bind_capabilities call, seat grants, emission and")
    print("      the live-context teardown. docker/eis_verify.py covers all")
    print("      of that against a real libeis server — run it too.")

    failed = [name for name, ok in _results if not ok]
    print("=" * 72)
    print(f"{len(_results) - len(failed)}/{len(_results)} checks passed")
    for name in failed:
        print(f"  FAILED: {name}")
    print("=" * 72)
    return len(failed)


def _assert_true(value: bool, message: str) -> str:
    if not value:
        raise AssertionError(message)
    return "yes"


if __name__ == "__main__":
    sys.exit(main())
