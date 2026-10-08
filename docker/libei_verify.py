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
import tempfile
import threading
import traceback
from typing import Any, Callable, List, Tuple

# A wrong prototype in a ctypes binding shows up as a segfault, not as an
# exception, and a segfault with no traceback is the hardest kind of bug to
# act on. faulthandler turns it into a Python stack ending at the exact call.
faulthandler.enable()

_results: List[Tuple[str, bool]] = []


def _scratch_dir() -> str:
    """A private directory to write into, created 0700 if it is not there.

    The images set ``XDG_RUNTIME_DIR``, so that is what this returns inside
    one. Run this script by hand without it and the answer is a fresh
    ``mkdtemp`` rather than the ``/tmp`` root itself, which any user on the
    host can create entries in.
    """
    runtime = os.environ.get("XDG_RUNTIME_DIR")
    if runtime:
        os.makedirs(runtime, mode=0o700, exist_ok=True)
        return runtime
    return tempfile.mkdtemp(prefix="autocontrol-verify-")


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


def _check_every_entry_point_resolves() -> str:
    """The check a mock structurally cannot make: does the .so have these?"""
    from je_auto_control.linux_wayland import libei
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


def _check_each_call_in_isolation(socket_path: str) -> str:
    """Walk connect()'s library calls by hand, printing as it goes.

    connect() is half a dozen calls deep; walking them with flushed output
    means a crash names the call that caused it rather than the function
    that contained it.
    """
    from je_auto_control.linux_wayland import libei
    symbols = libei._load_symbols()

    def step(message: str) -> None:
        print(f"        · {message}", flush=True)

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


def _check_unref_sentinel(socket_path: str) -> str:
    """Is the upstream ei_unref crash this binding works around still there?"""
    import subprocess  # nosec B404  # reason: argv list, no shell
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
    # This interpreter, running a program built from literals above; no shell.
    finished = subprocess.run([sys.executable, "-c", program],  # nosec B603  # nosemgrep
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


def measure(name: str, fn: Callable[[], Any]) -> Any:
    """Run a measurement and print what it found; never count it.

    The checks above decide this script's exit status. A measurement is
    something the reader of the log needs and the job must not turn red over
    — a classification, a number — so nothing here touches ``_results``.
    """
    try:
        detail = fn()
    except Exception:  # noqa: BLE001  # reason: a measurement that cannot run is itself a finding
        print(f"note  {name} — could not be measured:")
        print("        " + traceback.format_exc(limit=3).strip().replace(
            "\n", "\n        "))
        return None
    print(f"info  {name}  — {detail}")
    return detail


def _describe_exit(returncode: Any) -> str:
    """An exit status as a reader wants it: clean, a code, or a signal."""
    import signal
    if returncode is None:
        return "still running"
    if returncode == 0:
        return "clean (rc=0)"
    if returncode < 0:
        try:
            name = signal.Signals(-returncode).name
        except ValueError:
            name = "signal"
        return f"{name} (rc={returncode})"
    return f"exit status {returncode}"


#: Everything up to a context whose backend is open and whose handshake has
#: not progressed — the state ``LibeiBackend._teardown`` abandons.
_HALF_OPEN_PRELUDE = (
    "import ctypes, ctypes.util, os, socket;"
    "lib = ctypes.CDLL(ctypes.util.find_library('ei'));"
    "lib.ei_new_sender.restype = ctypes.c_void_p;"
    "lib.ei_new_sender.argtypes = (ctypes.c_void_p,);"
    "lib.ei_setup_backend_socket.restype = ctypes.c_int;"
    "lib.ei_setup_backend_socket.argtypes = "
    "(ctypes.c_void_p, ctypes.c_char_p);"
    "lib.ei_unref.restype = ctypes.c_void_p;"
    "lib.ei_unref.argtypes = (ctypes.c_void_p,);"
    "lib.ei_dispatch.restype = None;"
    "lib.ei_dispatch.argtypes = (ctypes.c_void_p,);"
    "p = {path!r};"
    "h = lib.ei_new_sender(None);"
    "rc = lib.ei_setup_backend_socket(h, p.encode());"
    "assert rc == 0, rc;"
)

#: How a half-open context can be ended, and the code that ends it that way.
_HALF_OPEN_ENDINGS = (
    ("ei_unref", "lib.ei_unref(h)"),
    ("ei_dispatch, then ei_unref", "lib.ei_dispatch(h); lib.ei_unref(h)"),
    ("no release, interpreter exits", "pass"),
    ("no release, os._exit(0)", "os._exit(0)"),
)


def _classify_half_open_teardown(socket_path: str) -> str:
    """Which ways of ending a half-open context crash, and which do not.

    Each ending runs in its own interpreter because the answer is a signal.
    This is what decides whether a helper process is a real fix: it only is
    if *leaving without releasing* is clean while ``ei_unref`` is not.
    """
    import subprocess  # nosec B404  # reason: argv list, no shell
    prelude = _HALF_OPEN_PRELUDE.format(path=socket_path)
    outcomes = {}
    print("        half-open context, ended by:")
    for label, ending in _HALF_OPEN_ENDINGS:
        # This interpreter, running a program built from literals; no shell.
        finished = subprocess.run([sys.executable, "-c", prelude + ending],  # nosec B603  # nosemgrep
                                  capture_output=True, timeout=60)
        outcomes[label] = finished.returncode
        print(f"          {label:<32} {_describe_exit(finished.returncode)}",
              flush=True)
    unref_crashes = outcomes["ei_unref"] < 0
    leaving_is_clean = (outcomes["no release, interpreter exits"] == 0
                        and outcomes["no release, os._exit(0)"] == 0)
    if unref_crashes and leaving_is_clean:
        return ("CLASSIFIED: the crash is ei_unref on a half-open context; "
                "a process that exits without releasing is clean, so the "
                "state is reclaimable by a helper process")
    if not unref_crashes:
        return ("CLASSIFIED: ei_unref no longer crashes on a half-open "
                "context, so neither the leak nor a helper is needed — see "
                "the REVISIT banner above")
    return ("UNCLASSIFIED: ei_unref crashes and exiting without release is "
            f"not clean either ({outcomes}); a helper would not contain it")


def _open_descriptors() -> int:
    return len(os.listdir("/proc/self/fd"))


def _leak_of(attempts: int, attempt: Callable[[], Any]) -> int:
    """How many descriptors ``attempts`` runs of ``attempt`` leave open."""
    before = _open_descriptors()
    for _ in range(attempts):
        attempt()
    return _open_descriptors() - before


def _half_open_in_process(socket_path: str) -> None:
    """One handshake that never completes, on the default in-process path."""
    from je_auto_control.linux_wayland import libei
    try:
        libei.LibeiBackend().connect(timeout=0.3,
                                     socket_path=socket_path.encode("utf-8"))
    except libei.LibeiUnavailable:
        pass


def _half_open_in_helper(socket_path: str) -> Any:
    """The same handshake inside a helper; returns the helper's exit status."""
    from je_auto_control.linux_wayland import ei_client, libei
    client = ei_client.EiWorkerClient(
        socket_path=socket_path, handshake_timeout_s=0.3,
        start_timeout_s=120.0)
    try:
        client.start()
    except libei.LibeiUnavailable:
        pass
    finally:
        client.close()
    return client.returncode


def _measure_helper_reclaims(socket_path: str) -> str:
    """Does the opt-in helper reclaim what the in-process path leaks?

    Three half-open handshakes each way, against the same silent socket. The
    in-process path is expected to leak one descriptor per attempt — that is
    the documented workaround, counted here rather than asserted — and the
    helper is expected to leak none and to exit without a signal.
    """
    from je_auto_control.linux_wayland import ei_client
    attempts = 3
    in_process = _leak_of(attempts, lambda: _half_open_in_process(socket_path))
    exits: List[Any] = []
    with_helper = _leak_of(
        attempts, lambda: exits.append(_half_open_in_helper(socket_path)))

    crashed = [code for code in exits if code is not None and code < 0]
    if crashed:
        print()
        print("      *** REVISIT ***  the libei helper process itself died")
        print(f"      on a signal ({[_describe_exit(c) for c in crashed]})")
        print("      while giving up a half-open handshake. It is opt-in")
        print("      (JE_AUTOCONTROL_WAYLAND_EI_WORKER) and must stay off")
        print("      until this is understood; see Progress.md.")
        print()
    return (f"{attempts} half-open handshakes: in-process leaked "
            f"{in_process} fd(s), the helper leaked {with_helper}; helper "
            f"exits {[_describe_exit(code) for code in exits]}; "
            f"{ei_client.active_worker_count()} helper(s) left running")


def _check_connect_fails_closed(socket_path: str) -> str:
    """A peer that sends nothing must not be reported as a live session."""
    from je_auto_control.linux_wayland import libei
    backend = libei.LibeiBackend()
    try:
        backend.connect(timeout=1.0,
                        socket_path=socket_path.encode("utf-8"))
    except libei.LibeiUnavailable as error:
        return f"LibeiUnavailable: {str(error)[:90]}"
    raise AssertionError(
        "connect() reported success against a peer that sent nothing, so "
        "the handshake is not actually gating on a live device")


def _check_teardown_survives(socket_path: str) -> str:
    """disconnect() has to be safe after a failed connect, and idempotent."""
    from je_auto_control.linux_wayland import libei
    backend = libei.LibeiBackend()
    try:
        backend.connect(timeout=0.5,
                        socket_path=socket_path.encode("utf-8"))
    except libei.LibeiUnavailable:
        pass
    backend.disconnect()          # must be safe after a failed connect
    backend.disconnect()          # and idempotent
    return "teardown survived a failed connect, twice"


def _check_keyboard_falls_back() -> str:
    """With no libei and no ydotool, the CLI path must surface its hint.

    ydotool is deliberately not installed in this image, so what comes back
    must be the install hint — not a libei error and not a silent no-op.
    """
    from je_auto_control.linux_wayland import keyboard as wl_keyboard
    try:
        wl_keyboard.press_key(30)
    except Exception as error:  # noqa: BLE001  # reason: any type is informative
        if "ydotool" in str(error):
            return f"{type(error).__name__}: {str(error)[:60]}"
        raise
    raise AssertionError("press_key claimed success with no libei and no "
                         "ydotool")


def main() -> int:
    print("=" * 72)
    print("AutoControl libei binding — against the real libei.so")
    print("=" * 72)

    resolved = ctypes.util.find_library("ei")
    print(f"find_library('ei')       = {resolved!r}")
    print(f"find_library('oeffis')   = {ctypes.util.find_library('oeffis')!r}")
    print("-" * 72)

    from je_auto_control.linux_wayland import _select_input, libei, oeffis

    # --- a real sender against a socket that speaks no EI ----------------
    runtime = _scratch_dir()
    socket_path = os.path.join(runtime, "eis-0")
    server = serve_silent_socket(socket_path)
    print(f"      silent EIS stand-in listening at {socket_path}")

    check("every libei entry point this binding names exists",
          _check_every_entry_point_resolves)

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

    check("each libei call in isolation",
          lambda: _check_each_call_in_isolation(socket_path))
    check("ei_unref after a successful setup — upstream state",
          lambda: _check_unref_sentinel(socket_path))
    check("connect() against a silent peer fails closed, not open",
          lambda: _check_connect_fails_closed(socket_path))
    check("teardown after a failed handshake does not crash the process",
          lambda: _check_teardown_survives(socket_path))

    # --- the fallback the whole design rests on --------------------------
    libei.reset_default_backend()
    check("active_backend() gives up and hands over to the CLI",
          lambda: _assert_true(_select_input.active_backend() is None,
                               "active_backend() returned a backend that "
                               "cannot emit"))
    check("press_key falls through to the ydotool CLI path",
          _check_keyboard_falls_back)

    # --- measurements: printed for the reader, never counted --------------
    # These classify the teardown the workaround exists for. They cannot
    # change this script's exit status, so a surprise here reads as a banner
    # in the log rather than as a red job.
    print("-" * 72)
    measure("teardown of a half-open context, classified",
            lambda: _classify_half_open_teardown(socket_path))
    measure("the opt-in helper process against the same half-open state",
            lambda: _measure_helper_reclaims(socket_path))

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
