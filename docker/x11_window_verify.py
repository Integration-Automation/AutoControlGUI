"""Verify cross-platform window management against a real window manager.

Window management was Windows-only for the project's whole life: the facade
branched on ``sys.platform`` and raised everywhere else, so 23 ``AC_*``
commands and their MCP tools were dead on Linux and macOS. The X11 backend
that replaces that branch talks EWMH to the window manager, and EWMH is
exactly the kind of contract a mock cannot check — what matters is whether
*openbox* agrees, not whether python-Xlib was called with the right atoms.

So this runs against the real session ``entrypoint-x11.sh`` brings up, drives
the public facade (``je_auto_control.list_windows`` and friends, not the
backend), and takes ground truth from ``xdotool`` and ``xprop`` — the window
manager answering for itself.

The subject is a real ``xterm``, launched with a title nothing else uses.

It shares the harness in ``x11_verify`` rather than duplicating it: same
session, same tally, one exit status.
"""
from __future__ import annotations

import os
import subprocess  # nosec B404  # reason: argv lists of fixed tool names, no shell
import sys
import time
from typing import Any, Optional, Tuple

from x11_verify import (
    EventTester, _assert_eq, _assert_true, _run, check, note, summarise,
)

#: Unique enough that `xdotool search` cannot match anything else in the image.
WINDOW_TITLE = "autocontrol-window-verify"

#: How long the window manager is given to act on an EWMH request. These are
#: asynchronous by design — the client message goes to the root window and the
#: window manager gets to it when it gets to it.
WM_TIMEOUT = 5.0


class Xterm:
    """A real X client owning a real, managed, titled window."""

    def __init__(self, title: str = WINDOW_TITLE) -> None:
        self.title = title
        self._process: Optional[subprocess.Popen] = None
        self.window_id = 0

    def __enter__(self) -> "Xterm":
        # -hold keeps the window up after the shell exits, so the subject
        # cannot vanish mid-check for a reason unrelated to what is under test.
        self._process = subprocess.Popen(  # nosec B603 B607  # nosemgrep
            ["xterm", "-title", self.title, "-geometry", "40x10+150+150",
             "-hold", "-e", "true"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.window_id = self._await_window()
        return self

    def __exit__(self, *_exception: Any) -> None:
        if self._process is not None and self._process.poll() is None:
            self._process.terminate()
            try:
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._process.kill()

    def _await_window(self) -> int:
        deadline = time.monotonic() + 20.0
        while time.monotonic() < deadline:
            try:
                found = _run(["xdotool", "search", "--name", self.title])
            except subprocess.CalledProcessError:
                found = ""
            ids = [line for line in found.split() if line.isdigit()]
            if ids:
                # Wait for the window manager to finish managing it: an EWMH
                # request against an unmanaged window is simply dropped.
                self._await_managed(int(ids[-1]))
                return int(ids[-1])
            if self._process is not None and self._process.poll() is not None:
                raise RuntimeError(
                    f"xterm exited {self._process.returncode} without a window")
            time.sleep(0.1)
        raise RuntimeError("xterm never mapped a window")

    @staticmethod
    def _await_managed(window_id: int) -> None:
        deadline = time.monotonic() + 10.0
        while time.monotonic() < deadline:
            listed = _run(["xprop", "-root", "_NET_CLIENT_LIST"])
            if f"{window_id:#x}" in listed.lower().replace("0x", "0x"):
                return
            time.sleep(0.1)
        raise RuntimeError(f"the window manager never took window {window_id}")

    @property
    def pid(self) -> int:
        return self._process.pid if self._process is not None else 0


def _active_window() -> int:
    """The window the server says is active, via xdotool."""
    return int(_run(["xdotool", "getactivewindow"]).strip() or 0)


#: How far a size may differ from what was asked before it counts as wrong.
#: xterm resizes in whole character cells, so it rounds a pixel size down to
#: the nearest cell — a property of the subject, not of the backend. A real
#: failure to resize is out by hundreds of pixels, not by one cell.
SIZE_TOLERANCE = 24


def _client_geometry(window_id: int) -> Tuple[int, int, int, int]:
    """The *client* ``(x, y, width, height)``, as xwininfo reports it."""
    values: dict = {}
    for line in _run(["xwininfo", "-id", str(window_id)]).splitlines():
        stripped = line.strip()
        for label, key in (("Absolute upper-left X:", "X"),
                           ("Absolute upper-left Y:", "Y"),
                           ("Width:", "WIDTH"), ("Height:", "HEIGHT")):
            if stripped.startswith(label):
                values[key] = int(stripped[len(label):].strip())
    return (values.get("X", 0), values.get("Y", 0),
            values.get("WIDTH", 0), values.get("HEIGHT", 0))


def _frame_extents(window_id: int) -> Tuple[int, int, int, int]:
    """``(left, right, top, bottom)`` decoration thickness, or zeroes."""
    try:
        raw = _run(["xprop", "-id", str(window_id), "_NET_FRAME_EXTENTS"])
    except subprocess.CalledProcessError:
        return (0, 0, 0, 0)
    if "not found" in raw or "=" not in raw:
        return (0, 0, 0, 0)
    parts = [piece.strip() for piece in raw.split("=", 1)[1].split(",")]
    if len(parts) < 4 or not all(piece.isdigit() for piece in parts[:4]):
        return (0, 0, 0, 0)
    return tuple(int(piece) for piece in parts[:4])  # type: ignore[return-value]


def _geometry(window_id: int) -> Tuple[int, int, int, int]:
    """The *frame* ``(x, y, width, height)``: the client plus its decorations.

    Win32's ``GetWindowRect`` returns the frame, every caller in this project
    is written against that, and the X11 backend reports the frame to match —
    so the frame is what has to be checked.

    Neither tool reports it directly. ``xwininfo -id`` gives the client
    rectangle (``-frame`` changes how a window is *picked*, not what is
    reported, so it makes no difference with ``-id``), and ``xprop``'s
    ``_NET_FRAME_EXTENTS`` gives the thickness the window manager added
    around it. Adding them is both the definition of the frame and a check
    that the backend's own walk up to it found the same window.
    """
    x, y, width, height = _client_geometry(window_id)
    left, right, top, bottom = _frame_extents(window_id)
    return (x - left, y - top, width + left + right, height + top + bottom)


def _wait_until(predicate, timeout: float = WM_TIMEOUT) -> bool:
    """Poll a predicate — every EWMH request is asynchronous."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.1)
    return False


# --- checks ----------------------------------------------------------------


def check_backend_selection() -> None:
    def _selected() -> str:
        from je_auto_control.wrapper.window_backends import get_backend

        backend = get_backend()
        _assert_true(backend.available,
                     f"backend {backend.name!r} reports unavailable")
        return _assert_eq(backend.name, "x11-ewmh")
    check("the window seam selects the X11 backend", _selected)


def check_listing(xterm: Xterm) -> None:
    import je_auto_control as ac

    def _lists() -> str:
        titles = dict(ac.list_windows())
        _assert_true(xterm.window_id in titles,
                     f"window {xterm.window_id} missing from {sorted(titles)}")
        return _assert_eq(titles[xterm.window_id], xterm.title)
    check("list_windows sees a real managed window with its title", _lists)

    def _finds() -> str:
        hit = ac.find_window(xterm.title)
        _assert_true(hit is not None, "find_window returned nothing")
        return _assert_eq(hit[0], xterm.window_id)
    check("find_window resolves the title substring", _finds)

    def _rect() -> str:
        rect = ac.window_rect(xterm.title)
        _assert_true(rect is not None, "window_rect returned None")
        left, top, right, bottom = rect
        x, y, width, height = _geometry(xterm.window_id)
        # Both sides are the frame: the rectangle a user sees and drags, and
        # the one Win32 reports. See _geometry for why the client rectangle
        # is the wrong comparison.
        _assert_eq((left, top), (x, y))
        _assert_eq((right - left, bottom - top), (width, height))
        return f"({left}, {top}) {right - left}x{bottom - top}"
    check("window_rect matches what the server reports", _rect)

    def _pid() -> str:
        # _NET_WM_PID is what the client advertises; xterm advertises its own.
        return _assert_eq(ac.window_process_id(xterm.title), xterm.pid)
    check("window_process_id is the owning process", _pid)

    def _by_pid() -> str:
        owned = dict(ac.windows_for_process_id(xterm.pid))
        _assert_true(xterm.window_id in owned,
                     f"window missing from the pid's windows: {sorted(owned)}")
        return f"{len(owned)} window(s) for pid {xterm.pid}"
    check("windows_for_process_id addresses windows by owner", _by_pid)


def check_focus(xterm: Xterm) -> None:
    import je_auto_control as ac

    def _focus() -> str:
        ac.focus_window(xterm.title)
        _assert_true(_wait_until(lambda: _active_window() == xterm.window_id),
                     f"the window manager never made {xterm.window_id} active")
        return _assert_eq(ac.foreground_window()[0], xterm.window_id)
    check("focus_window makes the window active, and foreground_window agrees",
          _focus)

    def _fg_pid() -> str:
        return _assert_eq(ac.foreground_window_process_id(), xterm.pid)
    check("foreground_window_process_id names the owning process", _fg_pid)


def check_move(xterm: Xterm) -> None:
    import je_auto_control as ac

    def _move() -> str:
        _assert_true(ac.move_window_by_title(xterm.title, 300, 220, 500, 300),
                     "move_window_by_title reported failure")
        _assert_true(
            _wait_until(lambda: _geometry(xterm.window_id)[:2] == (300, 220)),
            f"window stayed at {_geometry(xterm.window_id)}")
        x, y, width, height = _geometry(xterm.window_id)
        _assert_eq((x, y), (300, 220))
        _assert_true(abs(width - 500) <= SIZE_TOLERANCE
                     and abs(height - 300) <= SIZE_TOLERANCE,
                     f"asked 500x300, frame is {width}x{height}")
        return f"frame at ({x}, {y}), {width}x{height}"
    check("move_window_by_title moves and resizes for real", _move)

    def _move_keeps_size() -> str:
        # Omitting width/height must keep the current size rather than
        # collapsing the window, which is what makes a plain reposition usable
        # without looking the dimensions up first.
        before = _geometry(xterm.window_id)
        _assert_true(ac.move_window_by_title(xterm.title, 120, 90),
                     "move_window_by_title reported failure")
        _assert_true(
            _wait_until(lambda: _geometry(xterm.window_id)[:2] == (120, 90)),
            f"window stayed at {_geometry(xterm.window_id)}")
        return _assert_eq(_geometry(xterm.window_id)[2:], before[2:])
    check("moving without a size keeps the size", _move_keeps_size)


def check_minimize(xterm: Xterm) -> None:
    import je_auto_control as ac
    from je_auto_control.wrapper.window_backends import get_backend

    backend = get_backend()

    def _minimize() -> str:
        _assert_true(ac.minimize_window_by_title(xterm.title),
                     "minimize_window_by_title reported failure")
        _assert_true(
            _wait_until(lambda: backend.is_minimized(xterm.window_id)),
            "the window never reported itself hidden")
        return "iconified, and _NET_WM_STATE_HIDDEN says so"
    check("minimize_window_by_title iconifies the window", _minimize)

    def _restore() -> str:
        # focus_window restores before raising, which is the path a caller
        # takes to get back to a minimised window without knowing it was one.
        ac.focus_window(xterm.title)
        _assert_true(
            _wait_until(lambda: not backend.is_minimized(xterm.window_id)),
            "the window stayed hidden")
        return "restored by focus_window"
    check("focus_window restores a minimised window", _restore)


def check_post_is_synthetic(tester: EventTester) -> None:
    """Posting to an unfocused window works, and is honest about what it is."""
    import je_auto_control as ac

    def _post_click() -> str:
        tester.flush()
        _assert_true(
            ac.post_click_to_window("Event Tester", "left", 20, 20),
            "post_click_to_window reported failure")
        press = tester.collect("ButtonPress")[0]
        _assert_eq(press["button"], 1)
        # This is the point of the check. XSendEvent traffic arrives flagged
        # synthetic and GTK and Qt discard it by design, so post_* is
        # best-effort by nature — the same caveat Win32's PostMessage carries.
        # Asserting it here stops anyone reading post_* as real input.
        return _assert_eq(press["synthetic"], "YES")
    check("post_click_to_window arrives, flagged synthetic", _post_click)

    def _post_key() -> str:
        from je_auto_control import keyboard_keys_table

        tester.flush()
        _assert_true(ac.post_key_to_window("Event Tester", "b"),
                     "post_key_to_window reported failure")
        press = tester.collect("KeyPress")[0]
        _assert_eq(press["keycode"], keyboard_keys_table["b"])
        return _assert_eq(press["synthetic"], "YES")
    check("post_key_to_window arrives, flagged synthetic", _post_key)


def check_close(xterm: Xterm) -> None:
    import je_auto_control as ac

    def _close() -> str:
        _assert_true(ac.close_window_by_title(xterm.title),
                     "close_window_by_title reported failure")
        _assert_true(
            _wait_until(lambda: ac.find_window(xterm.title) is None, 10.0),
            "the window is still listed")
        return "gone from the client list"
    check("close_window_by_title really closes the window", _close)


def main() -> int:
    print("=" * 72)
    print("AutoControl window management — real X11 window manager")
    print("=" * 72)
    note(f"DISPLAY={os.environ.get('DISPLAY')!r}")

    check_backend_selection()

    with Xterm() as xterm:
        note(f"subject: xterm window {xterm.window_id} pid {xterm.pid}")
        check_listing(xterm)
        check_focus(xterm)
        check_move(xterm)
        check_minimize(xterm)
        check_close(xterm)

    with EventTester() as tester:
        check_post_is_synthetic(tester)

    print("-" * 72)
    print("NOT verifiable in this container, and why:")
    note("Wayland window management — the protocol does not let a client")
    note("  enumerate or move another application's windows at all, so there")
    note("  is nothing to implement, let alone verify. The backend selector")
    note("  says so rather than looking broken.")

    return summarise()


if __name__ == "__main__":
    sys.exit(main())
