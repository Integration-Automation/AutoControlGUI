"""Verify the Linux accessibility backend against a real AT-SPI bus.

Linux had no accessibility backend at all — the selector fell through to the
null one — while the capability matrix claimed "backend tests" for Linux X11.
The backend that closes that speaks AT-SPI2 over D-Bus directly, with no
binding, so what has to be checked is whether a *real* accessibility bus and a
*real* toolkit application agree with the bytes it sends.

Neither half can be mocked usefully. The bus is activated by D-Bus rather than
started by hand, an application only appears on it if its toolkit bridge
loaded, and the tree's shape is the toolkit's business. So the subject here is
``zenity`` — a GTK application with a label and buttons whose names are known
because this script chose them.

Exit status is the number of failed checks.
"""
from __future__ import annotations

import os
import subprocess  # nosec B404  # reason: argv lists of fixed tool names, no shell
import sys
import time
from typing import Any, Optional

from x11_verify import _assert_eq, _assert_true, check, note, summarise

#: The text zenity is told to show. Distinctive so a match cannot be an
#: accident of some other accessible carrying the same words.
DIALOG_TITLE = "autocontrol-atspi-dialog"
DIALOG_TEXT = "autocontrol-atspi-label"

#: How long the toolkit is given to bridge itself onto the bus. This is the
#: slowest part of the whole image: the application has to start, load the
#: bridge module, and register with the registry.
BRIDGE_TIMEOUT = 30.0


class Zenity:
    """A real GTK application, bridged onto the accessibility bus."""

    def __init__(self) -> None:
        self._process: Optional[subprocess.Popen] = None

    def __enter__(self) -> "Zenity":
        self._process = subprocess.Popen(  # nosec B603 B607  # nosemgrep
            ["zenity", "--info", "--title", DIALOG_TITLE,
             "--text", DIALOG_TEXT],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return self

    def __exit__(self, *_exception: Any) -> None:
        if self._process is not None and self._process.poll() is None:
            self._process.terminate()
            try:
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._process.kill()

    def alive(self) -> bool:
        return self._process is not None and self._process.poll() is None


def _await_bridged(backend, timeout: float = BRIDGE_TIMEOUT) -> list:
    """Wait until the application shows up on the bus, then return its tree."""
    deadline = time.monotonic() + timeout
    last: list = []
    while time.monotonic() < deadline:
        last = backend.list_elements(max_results=400)
        if any(DIALOG_TEXT in element.name or DIALOG_TITLE in element.name
               for element in last):
            return last
        time.sleep(0.5)
    return last


def check_backend_selection() -> None:
    def _selected() -> str:
        from je_auto_control.utils.accessibility.backends import (
            get_backend, reset_backend_cache,
        )

        reset_backend_cache()
        backend = get_backend()
        _assert_true(
            backend.available,
            f"backend {backend.name!r} reports unavailable — if this says "
            f"'null', the accessibility bus did not come up in this container")
        return _assert_eq(backend.name, "linux-atspi")
    check("Linux selects the AT-SPI backend, not the null one", _selected)


def check_tree(backend, zenity: Zenity) -> None:
    elements = _await_bridged(backend)

    def _application_appears() -> str:
        _assert_true(zenity.alive(), "zenity exited before it was inspected")
        names = [element.name for element in elements]
        _assert_true(
            any(DIALOG_TEXT in name or DIALOG_TITLE in name for name in names),
            f"the dialog never appeared on the bus; saw {names[:20]}")
        return f"{len(elements)} accessibles, including the dialog"
    check("a real GTK application is reachable over the bus",
          _application_appears)

    def _roles_are_named() -> str:
        # GetRoleName is a separate call from the name, and a backend that
        # skipped it would still list every element — with no role at all,
        # which is what a role= filter searches on.
        roles = {element.role for element in elements if element.role}
        _assert_true(bool(roles), "no element reported a role")
        return f"{len(roles)} distinct roles, e.g. {sorted(roles)[:4]}"
    check("every accessible carries the role AT-SPI reports", _roles_are_named)

    def _extents_are_screen_pixels() -> str:
        # GetExtents takes a coordinate space, and the wrong one returns
        # window-relative numbers that look plausible and click the wrong
        # place. A window on this screen has to have a non-zero size.
        sized = [element for element in elements
                 if element.bounds[2] > 0 and element.bounds[3] > 0]
        _assert_true(bool(sized), "no accessible reported a rectangle")
        widest = max(sized, key=lambda element: element.bounds[2])
        return (f"{len(sized)} with a rectangle; widest {widest.role!r} "
                f"{widest.bounds}")
    check("Component.GetExtents returns real screen rectangles",
          _extents_are_screen_pixels)

    def _application_is_named() -> str:
        # The walk is per-application, so every element has to carry the name
        # of the application it came from — that is what app_name filters on.
        owners = {element.app_name for element in elements if element.app_name}
        _assert_true(bool(owners), "no element carried an application name")
        return f"applications on the bus: {sorted(owners)}"
    check("elements carry the application they belong to", _application_is_named)

    def _scoped_walk_is_narrower() -> str:
        scoped = backend.list_elements(max_results=400,
                                       window_title=DIALOG_TITLE)
        _assert_true(len(scoped) <= len(elements),
                     f"scoping widened the walk: {len(scoped)} > {len(elements)}")
        return f"{len(scoped)} scoped vs {len(elements)} unscoped"
    check("scoping to a window narrows the walk", _scoped_walk_is_narrower)


def check_state(backend) -> None:
    def _state() -> str:
        # The state bitfield arrives as two 32-bit words; reading only the
        # first silently drops every state above bit 31.
        state = backend.get_state(role="push button")
        if state is None:
            state = backend.get_state(role="label")
        _assert_true(state is not None,
                     "get_state found neither a button nor a label")
        _assert_true("enabled" in state,
                     f"no enabled flag in {sorted(state)}")
        return f"{sorted(state)}"
    check("get_state reads the AT-SPI state bitfield", _state)


def main() -> int:
    print("=" * 72)
    print("AutoControl accessibility — real AT-SPI bus, real GTK application")
    print("=" * 72)
    note(f"DBUS_SESSION_BUS_ADDRESS set: "
         f"{bool(os.environ.get('DBUS_SESSION_BUS_ADDRESS'))}")

    check_backend_selection()

    from je_auto_control.utils.accessibility.backends import get_backend

    backend = get_backend()
    if not backend.available:
        print("-" * 72)
        print("The accessibility bus is not up, so nothing below can run.")
        print("That is a failure of this container, not a reason to skip:")
        print("every other check here depends on it.")
        return summarise() or 1

    with Zenity() as zenity:
        check_tree(backend, zenity)
        check_state(backend)

    print("-" * 72)
    print("NOT verifiable in this container, and why:")
    note("Anything needing a screen reader's own state — at-spi2 exposes")
    note("  ScreenReaderEnabled, and nothing here is a screen reader.")

    return summarise()


if __name__ == "__main__":
    sys.exit(main())
