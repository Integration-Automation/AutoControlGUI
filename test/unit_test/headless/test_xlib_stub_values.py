"""Hold the Xlib stub to the library it stands in for.

`_xlib_stub.py` lets `test_window_backend_x11.py` and its accessibility
counterpart run on all nine CI squares rather than the two with an X server,
by shadowing `Xlib` in `sys.modules`. That buys portability at one cost: a
stub can agree with a test about a number that is wrong on the wire.

This file is what stops that. `python-Xlib` is a real dependency on Linux and
BSD, so on both Linux squares the genuine module is installed and every
constant the stub declares is compared against it. Elsewhere there is nothing
to compare with and these skip -- which is the right shape for the check,
because a wrong constant is a Linux-only bug and Linux is where it is caught.

If a test here fails, the stub is wrong, not the library: fix
`_xlib_stub.py`'s value and re-read whichever assertion in
`test_window_backend_x11.py` depended on it.
"""
from __future__ import annotations

import pytest

from headless import _xlib_stub

# python-Xlib ships no wheel-less platforms: it is pinned in pyproject for
# Linux, FreeBSD, OpenBSD and NetBSD, and absent everywhere else.
xlib = pytest.importorskip(
    "Xlib", reason="python-Xlib is a Linux/BSD-only dependency",
)


@pytest.mark.parametrize("name", sorted(_xlib_stub.X_CONSTANTS))
def test_every_x_constant_matches_the_installed_library(name):
    from Xlib import X
    assert _xlib_stub.X_CONSTANTS[name] == getattr(X, name), (
        f"the stub's X.{name} is not what python-Xlib says it is"
    )


@pytest.mark.parametrize("name", sorted(_xlib_stub.XATOM_CONSTANTS))
def test_every_predefined_atom_matches_the_installed_library(name):
    from Xlib import Xatom
    assert _xlib_stub.XATOM_CONSTANTS[name] == getattr(Xatom, name), (
        f"the stub's Xatom.{name} is not what python-Xlib says it is"
    )


@pytest.mark.parametrize("name", sorted(_xlib_stub.KEYSYMS))
def test_every_keysym_matches_what_the_installed_library_resolves(name):
    # `XK.string_to_keysym` is what turns "Page_Up" into the number a grab is
    # registered against; a wrong one grabs the wrong key.
    from Xlib import XK
    assert _xlib_stub.KEYSYMS[name] == XK.string_to_keysym(name), (
        f"the stub's keysym for {name!r} is not what python-Xlib resolves"
    )


def test_an_unknown_key_name_resolves_to_zero():
    # Zero is how X says "no such keysym", and the hotkey backend reports it
    # as an unsupported key rather than grabbing keycode 0.
    from Xlib import XK
    assert XK.string_to_keysym("not-a-key") == 0


def test_the_event_classes_the_stub_fakes_all_exist():
    # A stub that answers for an event class the library does not have would
    # let a backend build a message nothing can send.
    from Xlib.protocol import event
    for name in ("ClientMessage", "KeyPress", "KeyRelease",
                 "ButtonPress", "ButtonRelease"):
        assert hasattr(event, name), f"Xlib.protocol.event.{name}"


def test_the_display_entry_point_the_stub_fakes_exists():
    from Xlib import display
    assert hasattr(display, "Display")
