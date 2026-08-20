"""Drive real X11 input from a real FreeBSD, and read it back off the server.

The X11 backend was gated on ``sys.platform`` being ``linux``/``linux2``, so it
refused to load on a FreeBSD desktop running the same X server, the same
python-Xlib and the same code. Relaxing that guard is only worth something if a
BSD actually runs it, and no hosted runner is one — so
``.github/workflows/platform-smoke.yml`` boots a FreeBSD VM inside an Ubuntu
runner and runs this.

For a while this could only check the *decision* — that ``sys.platform`` really
looks like ``freebsd14``, and that the classification every relaxed guard asks
answers correctly on it — because importing anything under ``je_auto_control``
ran the facade, and the facade imported OpenCV and cryptography at module scope.
Neither publishes a FreeBSD wheel, and building them from ports had not finished
after fifty minutes.

That was the wrong thing to fix. Moving a mouse needs neither package, and the
facade had no business insisting on them: they are imported by the functions
that use them now (``test_facade_import_is_light.py`` keeps it that way), which
leaves this VM needing python-Xlib and defusedxml — both pure Python — and an X
server. So the whole backend runs here, not just the guard.

Ground truth is the X server answering for itself, never this codebase:
``query_pointer`` for where the cursor actually is, its button mask for which
buttons the server believes are down, and ``query_keymap`` — a bitmap of every
physically-pressed key — for whether an injected key press really landed. That
last one is what makes a second X client unnecessary here; the Linux
``x11-verification`` job already reads events back out of ``xev``, and what a
BSD is uniquely needed to answer is whether this code drives the same server on
a different kernel.

Exit status is the number of failed checks.
"""
from __future__ import annotations

import os
import sys
import time
import traceback
from typing import Any, Callable, List, Tuple

#: Points the cursor is driven to. The corners matter: an off-by-one in the
#: coordinate space shows up at (0, 0) and at the far edge, not in the middle.
PROBE_POINTS: Tuple[Tuple[int, int], ...] = (
    (321, 123), (0, 0), (1, 1), (640, 480), (1279, 1023),
)

#: How long the server is given to settle after an injected event.
SETTLE = 0.05

_results: List[Tuple[str, bool, str]] = []


def check(name: str, fn: Callable[[], Any]) -> Any:
    """Run one check, record pass/fail, and keep going either way."""
    try:
        detail = fn()
    except Exception:  # noqa: BLE001  # reason: a failed check must not stop the rest
        _results.append((name, False, traceback.format_exc(limit=3).strip()))
        print(f"FAIL  {name}")
        print("        " + traceback.format_exc(limit=3).strip().replace(
            "\n", "\n        "))
        return None
    _results.append((name, True, str(detail)))
    print(f"ok    {name}" + (f"  — {detail}" if detail else ""))
    return detail


def _assert_eq(actual: Any, expected: Any) -> str:
    if actual != expected:
        raise AssertionError(f"expected {expected!r}, got {actual!r}")
    return f"{actual!r}"


def _assert_true(value: bool, message: str) -> str:
    if not value:
        raise AssertionError(message)
    return "yes"


# --- the decision only a BSD can answer ---------------------------------


def check_platform_identity() -> None:
    """What ``sys.platform`` is here, and what every relaxed guard makes of it."""
    from je_auto_control.utils import platform_id

    def _is_freebsd() -> str:
        _assert_true(sys.platform.startswith("freebsd"),
                     f"not a FreeBSD: sys.platform is {sys.platform!r}")
        return sys.platform
    check("sys.platform really is a FreeBSD", _is_freebsd)

    # Before the guards were relaxed the answer to the second of these was
    # False on exactly this platform, and the package refused to import at all.
    check("is_bsd() recognises it",
          lambda: _assert_true(platform_id.is_bsd(), "not recognised as a BSD"))
    check("is_x11_unix() recognises it",
          lambda: _assert_true(platform_id.is_x11_unix(), "not an X11 unix"))
    check("is_windows() does not",
          lambda: _assert_true(not platform_id.is_windows(), "claimed Windows"))
    check("is_macos() does not",
          lambda: _assert_true(not platform_id.is_macos(), "claimed macOS"))
    check("current_family() is bsd",
          lambda: _assert_eq(platform_id.current_family(), "bsd"))

    # The version suffix is the trap: sys.platform is freebsd14 here, never a
    # bare "freebsd", so an equality check would match no real system at all.
    def _suffixed() -> str:
        _assert_true(
            sys.platform != "freebsd",
            "this release stopped carrying a version suffix; the prefix match "
            "still works, but the comment explaining why it exists no longer "
            "describes reality")
        return sys.platform
    check("sys.platform still carries the major version", _suffixed)


def check_facade_is_importable() -> None:
    """The facade imports here — which is the thing that used to be impossible.

    And it imports *without* the wheels FreeBSD has none of. Asserting they are
    genuinely absent is the point: if some future image happens to have OpenCV
    installed, this job would quietly stop testing the property it exists for.
    """
    def _absent() -> str:
        import importlib.util

        present = [name for name in ("cv2", "PIL", "cryptography", "je_open_cv")
                   if importlib.util.find_spec(name) is not None]
        _assert_true(not present,
                     f"expected these to be absent on the VM, found: {present}")
        return "cv2, PIL, cryptography, je_open_cv all absent"
    check("the heavy wheels really are not installed here", _absent)

    def _facade() -> str:
        import je_auto_control

        return f"{len(je_auto_control.__all__)} public names"
    check("import je_auto_control", _facade)

    def _backend() -> str:
        from je_auto_control.wrapper import platform_wrapper

        module = platform_wrapper.mouse.__name__
        _assert_true("linux_with_x11" in module,
                     f"expected the X11 backend, got {module}")
        return module
    check("the wrapper selects the X11 backend on a BSD", _backend)


# --- input, driven and read back off the server -------------------------


def check_mouse_position() -> None:
    """Every point the backend is told to move to is where the server puts it."""
    from je_auto_control.linux_with_x11.mouse import x11_linux_mouse_control as m

    for x, y in PROBE_POINTS:
        def _round_trip(x=x, y=y) -> str:
            m.set_position(x, y)
            time.sleep(SETTLE)
            return _assert_eq(m.position(), (x, y))
        check(f"set_position({x}, {y}) lands where it was asked", _round_trip)


def check_mouse_buttons() -> None:
    """A pressed button is a button the *server* reports as down."""
    from je_auto_control.linux_with_x11.core.utils.x11_linux_display import (
        display,
    )
    from je_auto_control.linux_with_x11.mouse import x11_linux_mouse_control as m

    def _mask() -> int:
        return display.screen().root.query_pointer()._data["mask"]

    #: Button 1 in the pointer mask reported by the server.
    button_1 = 1 << 8

    def _press() -> str:
        m.set_position(400, 300)
        m.press_mouse(m.x11_linux_mouse_left)
        time.sleep(SETTLE)
        held = _mask()
        m.release_mouse(m.x11_linux_mouse_left)
        time.sleep(SETTLE)
        _assert_true(bool(held & button_1),
                     f"the server did not report button 1 down (mask {held:#x})")
        _assert_true(not _mask() & button_1,
                     "button 1 stayed down after release_mouse")
        return "pressed and released"
    check("press_mouse reaches the server, release_mouse clears it", _press)

    def _click() -> str:
        m.click_mouse(m.x11_linux_mouse_left, 500, 260)
        time.sleep(SETTLE)
        _assert_eq(m.position(), (500, 260))
        _assert_true(not _mask() & button_1,
                     "click_mouse left button 1 held down")
        return "moved and clicked cleanly"
    check("click_mouse moves and leaves no button held", _click)


def check_keyboard() -> None:
    """An injected key press is a key the server reports as physically down.

    ``query_keymap`` is a 32-byte bitmap of every key currently held, straight
    out of the server, so this needs no second client to read the event back.
    """
    from je_auto_control.linux_with_x11.core.utils.x11_linux_display import (
        display,
    )
    from je_auto_control.linux_with_x11.keyboard import (
        x11_linux_keyboard_control as k,
    )

    def _is_down(keycode: int) -> bool:
        keymap = display.query_keymap()
        return bool(keymap[keycode // 8] & (1 << (keycode % 8)))

    # Keycode 38 is 'a' on the standard PC layout Xvfb comes up with. The
    # check does not depend on which character it produces — only on the
    # server agreeing that this physical key went down and came back up.
    keycode = 38

    def _press() -> str:
        _assert_true(not _is_down(keycode), "the key was already down")
        k.press_key(keycode)
        time.sleep(SETTLE)
        down = _is_down(keycode)
        k.release_key(keycode)
        time.sleep(SETTLE)
        _assert_true(down, "the server never saw the key go down")
        _assert_true(not _is_down(keycode), "the key stayed down after release")
        return f"keycode {keycode} down then up"
    check("press_key/release_key reach the server", _press)


def check_scroll() -> None:
    """Scrolling is the one BSD-only defect this job exists to catch.

    ``mouse_scroll`` matched Windows, then macOS, then a literal
    ``["linux", "linux2"]`` — so on a BSD it fell off the end of the chain,
    raised nothing and scrolled nothing. Nothing above would notice: the
    pointer mask never shows a wheel button, because X11 delivers a scroll as a
    press *and* release of button 4/5/6/7 too fast to sample.

    So this maps a real X window that has asked for button events, puts the
    cursor inside it, and reads the buttons back out of the event queue — the
    same ground truth the Linux job gets from ``xev``, without needing a second
    process. It also holds the sign contract that was settled for all three
    platforms: a negative count reverses the direction.
    """
    from Xlib import X

    from je_auto_control.linux_with_x11.core.utils.x11_linux_display import (
        display,
    )

    screen = display.screen()
    window = screen.root.create_window(
        0, 0, 400, 400, 0, screen.root_depth,
        X.InputOutput, X.CopyFromParent,
        background_pixel=screen.white_pixel,
        event_mask=X.ButtonPressMask | X.ButtonReleaseMask)
    window.map()
    display.sync()

    def _drain() -> None:
        while display.pending_events():
            display.next_event()

    def _collect(count: int) -> List[int]:
        """The button of every ButtonPress that arrives, up to ``count``."""
        buttons: List[int] = []
        deadline = time.time() + 5.0
        while len(buttons) < count and time.time() < deadline:
            if not display.pending_events():
                time.sleep(0.01)
                continue
            event = display.next_event()
            if event.type == X.ButtonPress:
                buttons.append(event.detail)
        return buttons

    def _scroll(value: int, direction: str, expected: int) -> str:
        import je_auto_control as ac

        ac.set_mouse_position(200, 200)
        time.sleep(SETTLE)
        _drain()
        ac.mouse_scroll(value, scroll_direction=direction)
        buttons = _collect(abs(value))
        _assert_eq(buttons, [expected] * abs(value))
        return f"{value:+d} {direction} arrived as button {expected}"

    # A positive count scrolls the direction it names...
    check("scroll_down arrives as button 5",
          lambda: _scroll(2, "scroll_down", 5))
    check("scroll_up arrives as button 4",
          lambda: _scroll(2, "scroll_up", 4))
    # ...and a negative one reverses it, on this platform as on the others.
    check("a negative count reverses scroll_down into button 4",
          lambda: _scroll(-2, "scroll_down", 4))
    check("a negative count reverses scroll_up into button 5",
          lambda: _scroll(-2, "scroll_up", 5))

    window.destroy()
    display.sync()


def check_facade_input() -> None:
    """The same thing through the public API, so the binding is covered too."""
    def _through_facade() -> str:
        import je_auto_control as ac

        ac.set_mouse_position(210, 340)
        time.sleep(SETTLE)
        return _assert_eq(tuple(ac.get_mouse_position()), (210, 340))
    check("set_mouse_position/get_mouse_position through the facade",
          _through_facade)


def report_environment() -> None:
    """Print what this is running on, so a failure has context in the log."""
    import platform

    print(f"uname            : {' '.join(platform.uname())}")
    print(f"sys.platform     : {sys.platform}")
    print(f"python           : {sys.version.split()[0]}")
    print(f"DISPLAY          : {os.environ.get('DISPLAY', '(unset)')}")
    print()


def summarise() -> int:
    """Print the tally; return the number of failed checks."""
    failed = [name for name, ok, _ in _results if not ok]
    print()
    print(f"{len(_results) - len(failed)}/{len(_results)} checks passed")
    for name in failed:
        print(f"  FAILED: {name}")
    return len(failed)


def main() -> int:
    report_environment()
    check_platform_identity()
    check_facade_is_importable()
    check_mouse_position()
    check_mouse_buttons()
    check_scroll()
    check_keyboard()
    check_facade_input()
    return summarise()


if __name__ == "__main__":
    raise SystemExit(main())
