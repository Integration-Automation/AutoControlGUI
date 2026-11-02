"""Verify AutoControl's libei binding against the real ``libei.so``.

No compositor is needed for this half. What the unit tests cannot check —
because they inject a fake symbol table — is whether the entry points this
binding names actually exist in the shared object, with the signatures it
declares. A single misspelled name or a wrong ``argtypes`` would sail past
every mock and only surface on a user's machine.

So: resolve every prototype against the installed library, then drive
``connect()`` at a socket that accepts the connection but speaks no EI. The
handshake cannot complete, and that is the point — a protocol failure must
refuse input without silently handing over to a CLI. Explicit CLI selection
is checked separately, against the real library rather than only a mock.

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
import json
import os
import subprocess  # nosec B404  # reason: isolate a known native teardown fault in this interpreter
import socket
import sys
import tempfile
import threading
import traceback
from typing import Any, Callable, List, Tuple, cast

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
    """Retain each verification result and continue collecting evidence after an ordinary failure."""
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
    if symbols is None:
        raise AssertionError('libei did not resolve before isolated native calls')

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
    """Classify only a measured half-open teardown; preserve native traces and bound the child."""
    program = f"""
import ctypes, ctypes.util, json, os
lib = ctypes.CDLL(ctypes.util.find_library('ei'))
lib.ei_new_sender.restype = ctypes.c_void_p
lib.ei_new_sender.argtypes = (ctypes.c_void_p,)
lib.ei_setup_backend_socket.restype = ctypes.c_int
lib.ei_setup_backend_socket.argtypes = (ctypes.c_void_p, ctypes.c_char_p)
lib.ei_unref.restype = ctypes.c_void_p
lib.ei_unref.argtypes = (ctypes.c_void_p,)
fd_before = len(os.listdir('/proc/self/fd'))
handle = lib.ei_new_sender(None)
if not handle:
    raise RuntimeError('ei_new_sender returned NULL')
code = lib.ei_setup_backend_socket(handle, {socket_path!r}.encode('utf-8'))
if code != 0:
    raise RuntimeError(f'ei_setup_backend_socket returned {{code}}')
print('ei_unref: begin', flush=True)
lib.ei_unref(handle)
print('ei_unref: end', flush=True)
result = {{'fd_before': fd_before, 'fd_after': len(os.listdir('/proc/self/fd'))}}
print('EI_UNREF_RESULT='+json.dumps(result), flush=True)
"""
    finished = subprocess.run(  # nosec B603  # nosemgrep  # reason: fixed interpreter/argv, no shell or user program
        [sys.executable, '-X', 'faulthandler', '-c', program], capture_output=True,
        text=True, encoding='utf-8', errors='replace', timeout=10, check=False,
    )
    print(finished.stdout, end='')
    print(finished.stderr, end='')
    return _interpret_unref(finished)


def _interpret_unref(finished: subprocess.CompletedProcess[str]) -> str:
    """An unrelated failure is not evidence of a fixed upstream teardown."""
    began = 'ei_unref: begin' in finished.stdout.splitlines()
    ended = 'ei_unref: end' in finished.stdout.splitlines()
    if finished.returncode == -11:
        if not began or ended:
            raise AssertionError('native fault occurred before or outside ei_unref')
        return ("still segfaults (rc=-11), so the abandon-on-teardown "
                "workaround in libei.py::_teardown is still required")
    if finished.returncode != 0:
        raise AssertionError(f'unexpected ei_unref probe exit {finished.returncode}')
    if not began or not ended:
        raise AssertionError('ei_unref did not reach completed cleanup')
    return f'no longer crashes (rc=0), descriptors {_descriptor_evidence(finished.stdout)}; revisit Progress.md'


def _descriptor_evidence(output: str) -> str:
    """Require exact nonnegative integer descriptor counts after successful native cleanup."""
    records = [line.removeprefix('EI_UNREF_RESULT=') for line in output.splitlines()
               if line.startswith('EI_UNREF_RESULT=')]
    if len(records) != 1:
        raise AssertionError('successful cleanup lacks descriptor evidence')
    counts = json.loads(records[0])
    before, after = counts['fd_before'], counts['fd_after']
    if any(isinstance(value, bool) or not isinstance(value, int) or value < 0 for value in (before, after)):
        raise AssertionError('ei_unref descriptor counts are not nonnegative integers')
    if before != after:
        raise AssertionError(f'ei_unref descriptor counts differ: {before!r} -> {after!r}')
    return f'{before} -> {after}'


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


def _check_native_refusal() -> str:
    """A timed-out native handshake must refuse an implicit CLI handoff."""
    # pylint: disable-next=import-outside-toplevel  # reason: native modules load only when this check runs
    from je_auto_control.linux_wayland import _select_input, libei
    try:
        cast(Callable[[], object], _select_input.active_backend)()
    except libei.LibeiUnavailable as error:
        if error.state == 'failed' and not error.status.fallback_allowed:
            return f'failed, no fallback: {error}'
        raise
    raise AssertionError('a failed native handshake did not refuse automatic CLI fallback')


def _check_keyboard_refuses_native() -> str:
    """The keyboard path retains the cached native refusal without starting another provider."""
    # pylint: disable-next=import-outside-toplevel  # reason: native modules load only when this check runs
    from je_auto_control.linux_wayland import keyboard, libei
    try:
        keyboard.press_key(30)
    except libei.LibeiUnavailable as error:
        if error.state == 'failed' and not error.status.fallback_allowed:
            return f'failed, no fallback: {error}'
        raise
    raise AssertionError('press_key bypassed the failed native session')


def _check_explicit_cli_hint() -> str:
    """An explicit CLI choice remains usable and reports its missing helper clearly."""
    from je_auto_control.linux_wayland import keyboard as wl_keyboard
    key = 'JE_AUTOCONTROL_WAYLAND_INPUT_BACKEND'
    previous = os.environ.get(key)
    try:
        os.environ[key] = 'cli'
        wl_keyboard.press_key(30)
    except Exception as error:  # noqa: BLE001  # reason: any type is informative
        if "ydotool" in str(error):
            return f"{type(error).__name__}: {str(error)[:60]}"
        raise
    finally:
        if previous is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = previous
    raise AssertionError("press_key claimed success with no libei and no "
                         "ydotool")


def main() -> int:
    """Verify native ABI, bounded half-open teardown, authority refusal and explicit CLI behavior."""
    print("=" * 72)
    print("AutoControl libei binding — against the real libei.so")
    print("=" * 72)

    resolved = ctypes.util.find_library("ei")
    print(f"find_library('ei')       = {resolved!r}")
    print(f"find_library('oeffis')   = {ctypes.util.find_library('oeffis')!r}")
    print("-" * 72)

    # pylint: disable-next=import-outside-toplevel  # reason: native modules load only for the explicit verification run
    from je_auto_control.linux_wayland import libei, oeffis

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

    # --- native refusal and deliberate CLI selection --------------------
    libei.reset_default_backend()
    check("failed native handshake refuses automatic CLI fallback", _check_native_refusal)
    check("press_key retains the native refusal", _check_keyboard_refuses_native)
    check("explicit CLI selection retains its missing-helper hint", _check_explicit_cli_hint)

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
