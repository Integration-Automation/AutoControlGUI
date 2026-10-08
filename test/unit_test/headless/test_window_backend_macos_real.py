"""Minimise a real macOS window and bring it back, on a real window server.

`test_window_backend_macos.py` holds the backend to a stand-in for pyobjc,
and a stand-in can only agree with what its author believed about Quartz.
The defect this file exists for was exactly such a belief: a minimised window
is missing from Quartz's *on-screen* list, the backend looked every window up
there, and so `minimize` was a one-way trip -- `restore` raised the "grant
Accessibility" refusal on a Mac where it had been granted.

So this opens a window of its own, in a child process, and drives it through
the real frameworks. The child owns the window because the accessibility API
talks to an application through its run loop, and a test process blocked in
an assertion is not running one.

**Where it runs.** Only on macOS, and only when asked: on CI (`CI` is set by
GitHub Actions, whose `macos-14` runners were measured to grant Accessibility
-- see `test/verify/macos_verify.py`) or with `AUTOCONTROL_REAL_WINDOW_TEST=1`.
It puts a window on the screen, and a developer running the headless suite on
their own Mac has not asked for that.

**What is a skip and what is a failure.** Everything needed to *reach* the
question is a skip with its reason: no window server, no Accessibility grant,
a window that would not minimise. Once a window has been minimised through
this backend, failing to find it, list it or restore it is the defect, and
fails.

No Qt imports.
"""
from __future__ import annotations

import os
import subprocess  # nosec B404  # reason: starts this interpreter with a fixed script to own a test window
import sys
import time

import pytest

pytestmark = pytest.mark.skipif(
    sys.platform != "darwin"
    or not (os.environ.get("CI")
            or os.environ.get("AUTOCONTROL_REAL_WINDOW_TEST")),
    reason="opens a real window: macOS only, on CI or with "
           "AUTOCONTROL_REAL_WINDOW_TEST=1",
)

_WIDTH, _HEIGHT = 320, 240

#: The whole child: one titled, miniaturisable window and a run loop.
_CHILD = f"""
import AppKit
app = AppKit.NSApplication.sharedApplication()
app.setActivationPolicy_(AppKit.NSApplicationActivationPolicyRegular)
style = (AppKit.NSWindowStyleMaskTitled | AppKit.NSWindowStyleMaskClosable
         | AppKit.NSWindowStyleMaskMiniaturizable)
window = AppKit.NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
    ((200, 200), ({_WIDTH}, {_HEIGHT})), style,
    AppKit.NSBackingStoreBuffered, False)
window.setTitle_("AutoControl minimise test")
window.makeKeyAndOrderFront_(None)
app.activateIgnoringOtherApps_(True)
app.run()
"""

_POLL_S = 0.1


def _wait_for(condition, timeout_s: float):
    """Poll `condition` until it is truthy; its last value either way."""
    deadline = time.monotonic() + timeout_s
    while True:
        value = condition()
        if value or time.monotonic() >= deadline:
            return value
        time.sleep(_POLL_S)


def _on_screen_ids(backend, pid: int) -> list:
    import Quartz

    return [int(info.get(Quartz.kCGWindowNumber, 0) or 0)
            for info in backend._window_info()
            if int(info.get(Quartz.kCGWindowOwnerPID, 0) or 0) == pid
            and int(info.get(Quartz.kCGWindowLayer, 0) or 0) == 0]


@pytest.fixture
def owned_window():
    """`(backend, window_id, pid)` for a window this test may do anything to."""
    from je_auto_control.wrapper.window_backends.macos_backend import (
        MacOSWindowBackend,
    )

    backend = MacOSWindowBackend()
    if not backend.available:
        pytest.skip("the macOS window backend is unavailable here")
    child = subprocess.Popen(  # nosec B603  # nosemgrep  # reason: this interpreter, fixed argv, no shell
        [sys.executable, "-c", _CHILD],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        ids = _wait_for(lambda: _on_screen_ids(backend, child.pid), 15.0)
        if not ids:
            pytest.skip("no window appeared: no window server in this session")
        window_id = ids[0]
        if not _wait_for(lambda: backend._ax_window(window_id), 5.0):
            pytest.skip("no accessibility element: Accessibility not granted")
        yield backend, window_id, child.pid
    finally:
        child.terminate()
        try:
            child.wait(timeout=5)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait(timeout=5)


def test_a_really_minimised_window_is_found_listed_and_restored(owned_window):
    backend, window_id, pid = owned_window

    if not backend.minimize(window_id):
        pytest.skip("the accessibility API refused to minimise the window")
    if _wait_for(lambda: window_id not in _on_screen_ids(backend, pid),
                 5.0) is not True:
        pytest.skip("the window never left the screen after minimising")

    # From here on the window is minimised by this backend, so every answer
    # below is the contract and not a precondition.
    assert backend.window_process_id(window_id) == pid, (
        "a minimised window must still be found by id")
    assert backend.window_rect(window_id) is not None
    assert backend.is_minimized(window_id) is True

    backend.restore(window_id)      # raised the Accessibility refusal before
    assert _wait_for(lambda: window_id in _on_screen_ids(backend, pid),
                     5.0), "restore did not bring the window back on screen"
    assert backend.is_minimized(window_id) is False


def test_a_really_minimised_window_stays_in_the_listing(owned_window):
    # Separate from the test above on purpose: this half depends on matching
    # an off-screen Quartz window to its accessibility element, which is the
    # part of the fix a stand-in is least able to vouch for.
    backend, window_id, pid = owned_window

    assert window_id in [number for number, _title in backend.list_windows()]
    if not backend.minimize(window_id):
        pytest.skip("the accessibility API refused to minimise the window")
    if _wait_for(lambda: window_id not in _on_screen_ids(backend, pid),
                 5.0) is not True:
        pytest.skip("the window never left the screen after minimising")

    listed = [number for number, _title in backend.list_windows()]
    assert window_id in listed, (
        "list_windows must include a minimised window, as on Windows")
