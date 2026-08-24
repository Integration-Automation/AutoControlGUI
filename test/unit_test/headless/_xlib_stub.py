"""A python-Xlib stand-in, so the X11 backends can be tested off Linux.

`python-Xlib` is a Linux/BSD-only dependency, and both X11 backends import it
*inside* their methods — so the modules load anywhere and only the calls need
a display. That is what makes them testable on all nine CI squares rather
than the two that have X: put a stub in `sys.modules` and the lazy import
finds it, on Linux as well as on Windows and macOS.

Two things make this a stub rather than a mock.

**The constants carry their real values.** `SubstructureRedirectMask` here is
`1 << 20` because that is what `X.h` says, so a test asserting an event mask
is asserting the number that goes on the wire. `test_xlib_stub_values.py`
compares every constant below against the real module wherever it is
installed, which on CI is both Linux squares — so a wrong value here is a
named failure there rather than a test that agrees with itself.

**The display is a real object graph, not a recorder.** Windows have
properties, properties are keyed by interned atom, and `query_tree` returns a
parent — because the code under test walks up to the frame, interns atoms
once per connection, and reads properties by id. A recorder would let a
backend that never interned an atom pass.

Nothing here is a test; the file is named so pytest does not collect it.
"""
from __future__ import annotations

import sys
import types

# --- X.h -----------------------------------------------------------------

#: `X.h` event masks, modifier masks and sentinels the backends name.
X_CONSTANTS = {
    "NONE": 0,
    "CurrentTime": 0,
    "AnyPropertyType": 0,
    "KeyPress": 2,
    "KeyPressMask": 1 << 0,
    "KeyReleaseMask": 1 << 1,
    "ButtonPressMask": 1 << 2,
    "ButtonReleaseMask": 1 << 3,
    "SubstructureNotifyMask": 1 << 19,
    "SubstructureRedirectMask": 1 << 20,
    # Modifier masks, for the hotkey backend's grabs. The two lock masks are
    # what it re-grabs each combo under, so a hotkey still fires with NumLock
    # or CapsLock on.
    "ShiftMask": 1 << 0,
    "LockMask": 1 << 1,
    "ControlMask": 1 << 2,
    "Mod1Mask": 1 << 3,
    "Mod2Mask": 1 << 4,
    "Mod4Mask": 1 << 6,
    "GrabModeSync": 0,
    "GrabModeAsync": 1,
}

#: Keysyms `XK.string_to_keysym` answers for, by their `keysymdef.h` values.
#: Latin-1 letters are their ASCII code point; the named keys are 0xFF00-range
#: function keysyms.
KEYSYMS = {
    "a": 0x0061, "b": 0x0062, "k": 0x006B, "q": 0x0071, "z": 0x007A,
    "1": 0x0031, "Return": 0xFF0D, "Tab": 0xFF09, "Escape": 0xFF1B,
    "space": 0x0020, "F5": 0xFFC2, "Page_Up": 0xFF55, "Delete": 0xFFFF,
}

#: `Xatom.h` predefined atoms, by their fixed protocol numbers.
XATOM_CONSTANTS = {
    "CARDINAL": 6,
    "STRING": 31,
    "WINDOW": 33,
}


# --- the object graph ----------------------------------------------------

class Event:
    """One X event, recording the keywords the backend built it from."""

    def __init__(self, kind: str, **fields) -> None:
        self.kind = kind
        self.fields = fields

    def __repr__(self) -> str:      # pragma: no cover - debugging aid
        return f"Event({self.kind!r}, {self.fields!r})"


class _Property:
    def __init__(self, value) -> None:
        self.value = value


class Window:
    """A window with properties, a parent, and a geometry."""

    def __init__(self, display, window_id: int, *, properties=None,
                 geometry=None, wm_name=None, parent_id=None) -> None:
        self._display = display
        self.id = int(window_id)
        self.properties = dict(properties or {})
        self.geometry = geometry or (0, 0, 0, 0)
        self.wm_name = wm_name
        self.parent_id = parent_id
        self.sent = []
        self.mapped = None
        self.attributes = {}
        self.grabs = []
        self.ungrabs = []
        self.grab_errors = {}       # (keycode, mask) -> exception
        self.ungrab_errors = {}
        self.property_error = None
        self.tree_error = None
        self.geometry_error = None
        self.send_error = None

    # -- the python-Xlib surface --
    def get_full_property(self, atom: int, kind):
        if self.property_error is not None:
            raise self.property_error
        name = self._display.atom_name(atom)
        if name not in self.properties:
            return None
        return _Property(self.properties[name])

    def get_wm_name(self):
        return self.wm_name

    def query_tree(self):
        if self.tree_error is not None:
            raise self.tree_error
        parent = (None if self.parent_id is None
                  else self._display.window(self.parent_id))
        return types.SimpleNamespace(parent=parent)

    def get_geometry(self):
        if self.geometry_error is not None:
            raise self.geometry_error
        x, y, width, height = self.geometry
        return types.SimpleNamespace(x=x, y=y, width=width, height=height)

    def send_event(self, event, event_mask=0, propagate=False):
        if self.send_error is not None:
            raise self.send_error
        self.sent.append((event, event_mask, propagate))

    def map(self):
        self.mapped = True

    def unmap(self):
        self.mapped = False

    def change_attributes(self, **kwargs):
        self.attributes = dict(kwargs)

    def grab_key(self, keycode, mask, owner_events, pointer_mode, key_mode):
        error = self.grab_errors.get((keycode, mask))
        if error is not None:
            raise error
        self.grabs.append((keycode, mask, owner_events, pointer_mode,
                           key_mode))

    def ungrab_key(self, keycode, mask):
        if (keycode, mask) in self.ungrab_errors:
            raise self.ungrab_errors[(keycode, mask)]
        self.ungrabs.append((keycode, mask))

    @property
    def grabbed(self):
        """The `(keycode, mask)` pairs currently held, in grab order."""
        held = [(keycode, mask) for keycode, mask, *_rest in self.grabs]
        for pair in self.ungrabs:
            if pair in held:
                held.remove(pair)
        return held


class Display:
    """One X connection: an atom table, a root, and a window table."""

    #: Interned atoms start above the predefined range so a test can tell an
    #: interned atom from `Xatom.WINDOW` at a glance.
    FIRST_INTERNED_ATOM = 100

    def __init__(self) -> None:
        self.atoms = {}
        self.flushes = 0
        self.syncs = 0
        self.closed = False
        self.events = []
        self.keycodes = {}      # keysym -> keycode
        self._windows = {}
        self.root = Window(self, 1)
        self._windows[1] = self.root

    # -- the python-Xlib surface --
    def intern_atom(self, name: str) -> int:
        if name not in self.atoms:
            self.atoms[name] = self.FIRST_INTERNED_ATOM + len(self.atoms)
        return self.atoms[name]

    def screen(self):
        return types.SimpleNamespace(root=self.root)

    def create_resource_object(self, kind: str, window_id: int) -> Window:
        assert kind == "window"
        return self.window(window_id)

    def flush(self) -> None:
        self.flushes += 1

    def sync(self) -> None:
        self.syncs += 1

    def close(self) -> None:
        self.closed = True

    def keysym_to_keycode(self, keysym: int) -> int:
        return self.keycodes.get(keysym, 0)

    def pending_events(self) -> int:
        return len(self.events)

    def next_event(self):
        return self.events.pop(0)

    # -- test helpers --
    def atom_name(self, atom: int):
        for name, value in self.atoms.items():
            if value == atom:
                return name
        return None

    def window(self, window_id: int, **kwargs) -> Window:
        window_id = int(window_id)
        if window_id not in self._windows:
            self._windows[window_id] = Window(self, window_id, **kwargs)
        elif kwargs:
            existing = self._windows[window_id]
            for key, value in kwargs.items():
                setattr(existing, key, value)
        return self._windows[window_id]

    def set_root_property(self, name: str, value) -> None:
        """Publish an EWMH property on the root, interning its atom."""
        self.intern_atom(name)
        self.root.properties[name] = value


def install(monkeypatch, display=None, display_error=None) -> Display:
    """Put the stub in `sys.modules` and hand back the display it opens.

    Shadows the real `Xlib` for the duration wherever one is installed, so
    the same test reads the same on every square.

    `display_error` makes `Display()` raise while leaving the rest of the
    package importable, which is the shape of a Wayland or headless session:
    python-Xlib is a hard dependency on Linux, so it is always *there* — it
    is the connection that is not.
    """
    display = display if display is not None else Display()

    x_module = types.ModuleType("Xlib.X")
    for name, value in X_CONSTANTS.items():
        setattr(x_module, name, value)

    xatom_module = types.ModuleType("Xlib.Xatom")
    for name, value in XATOM_CONSTANTS.items():
        setattr(xatom_module, name, value)

    # `XK.string_to_keysym` answers 0 for a name X does not know, which is
    # the "unknown key" branch the hotkey backend has to report.
    xk_module = types.ModuleType("Xlib.XK")
    xk_module.string_to_keysym = lambda name: KEYSYMS.get(name, 0)

    event_module = types.SimpleNamespace(
        ClientMessage=lambda **kwargs: Event("ClientMessage", **kwargs),
        KeyPress=lambda **kwargs: Event("KeyPress", **kwargs),
        KeyRelease=lambda **kwargs: Event("KeyRelease", **kwargs),
        ButtonPress=lambda **kwargs: Event("ButtonPress", **kwargs),
        ButtonRelease=lambda **kwargs: Event("ButtonRelease", **kwargs),
    )
    protocol_module = types.ModuleType("Xlib.protocol")
    protocol_module.event = event_module

    def _open_display(*args, **kwargs):
        if display_error is not None:
            raise display_error
        return display

    display_module = types.ModuleType("Xlib.display")
    display_module.Display = _open_display

    package = types.ModuleType("Xlib")
    package.X = x_module
    package.Xatom = xatom_module
    package.XK = xk_module
    package.protocol = protocol_module
    package.display = display_module

    for name, module in (("Xlib", package), ("Xlib.X", x_module),
                         ("Xlib.Xatom", xatom_module),
                         ("Xlib.XK", xk_module),
                         ("Xlib.protocol", protocol_module),
                         ("Xlib.display", display_module)):
        monkeypatch.setitem(sys.modules, name, module)
    return display


def install_failing(monkeypatch, error) -> None:
    """Install a stub whose `Display()` raises, as a headless session does."""
    def _raise(*args, **kwargs):
        raise error

    display_module = types.ModuleType("Xlib.display")
    display_module.Display = _raise
    package = types.ModuleType("Xlib")
    package.display = display_module
    monkeypatch.setitem(sys.modules, "Xlib", package)
    monkeypatch.setitem(sys.modules, "Xlib.display", display_module)
