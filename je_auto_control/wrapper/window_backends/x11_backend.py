"""X11 window-management backend, over EWMH and python-Xlib.

Everything here goes through the EWMH properties and client messages a
window manager maintains (``_NET_CLIENT_LIST_STACKING``, ``_NET_ACTIVE_WINDOW``,
``_NET_WM_PID``, ``_NET_WM_STATE``, …) rather than by poking at windows
directly, because on X11 the window manager owns stacking, focus and
iconification — a client that reparents or raises behind its back gets
overruled or, worse, half-obeyed.

``python-Xlib`` is already a hard dependency on Linux, so this adds nothing to
install.

One caveat is written into :meth:`X11WindowBackend.post_key` and
:meth:`X11WindowBackend.post_click` rather than hidden: events delivered with
``XSendEvent`` arrive at the client flagged *synthetic*, and most toolkits
(GTK and Qt among them) ignore synthetic input by design. They are the closest
X11 equivalent of Win32's ``PostMessage`` — which also bypasses focus — and
they are honest about being best-effort.
"""
import sys
import time
from typing import Any, List, Optional, Tuple

from je_auto_control.utils.logging.logging_instance import autocontrol_logger
from je_auto_control.wrapper.window_backends.base import WindowManageBackend

#: ``ShowWindow`` codes this backend can honour, mapped to what X11 calls the
#: same idea. The Win32 numbering is the project's cross-platform spelling of
#: show-state; the codes with no X11 meaning are refused rather than guessed.
SW_HIDE = 0
SW_SHOWNORMAL = 1
SW_SHOWMINIMIZED = 2
SW_MAXIMIZE = 3
SW_MINIMIZE = 6
SW_RESTORE = 9

#: ICCCM window states, from the specification.
_ICONIC_STATE = 3

#: Button names the project uses, in X11's button numbering.
_BUTTONS = {"left": 1, "middle": 2, "right": 3}


def _is_linux() -> bool:
    return sys.platform in ("linux", "linux2")


class X11WindowBackend(WindowManageBackend):
    """Window management through the window manager's own EWMH contract."""

    name = "x11-ewmh"

    def __init__(self) -> None:
        self._connection = None
        self._atoms: dict = {}
        self.available = _is_linux() and self._probe()

    # --- connection --------------------------------------------------------

    def _probe(self) -> bool:
        try:
            self._display()
            return True
        except Exception as error:  # noqa: BLE001  # reason: any X failure means unavailable
            autocontrol_logger.info(
                "X11 window backend unavailable: %r", error)
            return False

    def _display(self):
        """The X connection, opened once and kept.

        Its own connection rather than the input backend's: this module is
        selected by the wrapper independently of which input path is active,
        and on Wayland-with-XWayland the input backend may not have opened one
        at all.
        """
        if self._connection is None:
            from Xlib import display as xdisplay

            self._connection = xdisplay.Display()
        return self._connection

    def _atom(self, name: str) -> int:
        """Intern an atom once per connection."""
        if name not in self._atoms:
            self._atoms[name] = self._display().intern_atom(name)
        return self._atoms[name]

    def _root(self):
        return self._display().screen().root

    def _window(self, window_id: int):
        return self._display().create_resource_object("window", int(window_id))

    def _property(self, window, name: str, kind: Optional[int] = None):
        """Read a property's value list, or ``None`` when it is absent."""
        from Xlib import X

        found = window.get_full_property(
            self._atom(name), X.AnyPropertyType if kind is None else kind)
        return None if found is None else found.value

    def _client_message(self, window, name: str, data: List[int]) -> None:
        """Send an EWMH client message to the root window.

        EWMH requests are addressed to the root with
        ``SubstructureRedirect``: that is what routes them to the window
        manager, which is the only party allowed to act on them.
        """
        from Xlib import X, protocol

        padded = (list(data) + [0, 0, 0, 0, 0])[:5]
        event = protocol.event.ClientMessage(
            window=window, client_type=self._atom(name), data=(32, padded))
        self._root().send_event(
            event,
            event_mask=X.SubstructureRedirectMask | X.SubstructureNotifyMask)
        self._display().flush()

    # --- listing -----------------------------------------------------------

    def list_windows(self) -> List[Tuple[int, str]]:
        from Xlib import Xatom

        # Stacking order is bottom-to-top, so reversing it puts the front-most
        # window first — which is what makes "the first title that matches" the
        # one the user meant. _NET_CLIENT_LIST carries no order at all, so it
        # is only the fallback.
        ids = self._property(self._root(), "_NET_CLIENT_LIST_STACKING",
                             Xatom.WINDOW)
        if ids is None:
            ids = self._property(self._root(), "_NET_CLIENT_LIST",
                                 Xatom.WINDOW) or []
            ordered = list(ids)
        else:
            ordered = list(reversed(list(ids)))
        return [(int(window_id), self._title(int(window_id)))
                for window_id in ordered]

    def _title(self, window_id: int) -> str:
        """``_NET_WM_NAME`` if the client sets it, else the legacy ``WM_NAME``."""
        window = self._window(window_id)
        try:
            value = self._property(window, "_NET_WM_NAME")
            if value:
                return _as_text(value)
            legacy = window.get_wm_name()
            return legacy if isinstance(legacy, str) else _as_text(legacy)
        except Exception:  # noqa: BLE001  # reason: a window can vanish mid-walk
            return ""

    def foreground_window(self) -> int:
        from Xlib import Xatom

        active = self._property(self._root(), "_NET_ACTIVE_WINDOW", Xatom.WINDOW)
        return int(active[0]) if active else 0

    # --- reading one window ------------------------------------------------

    def _frame(self, window_id: int):
        """The window manager's frame around a client, or the client itself.

        A reparenting window manager makes the client a grandchild of the
        root, inside a frame that carries the border and title bar. The frame
        is what the user sees and drags, so it is the window every coordinate
        here is about.
        """
        window = self._window(window_id)
        root_id = self._root().id
        # Bounded rather than `while True`: a frame is one or two levels, and
        # a cycle here would hang the caller instead of returning something.
        for _ in range(16):
            tree = window.query_tree()
            parent = getattr(tree, "parent", None)
            if parent is None or parent.id == root_id:
                return window
            window = parent
        return window

    def _frame_extents(self, window_id: int) -> Tuple[int, int, int, int]:
        """``(left, right, top, bottom)`` decoration thickness, or zeroes."""
        from Xlib import Xatom

        try:
            value = self._property(self._window(window_id),
                                   "_NET_FRAME_EXTENTS", Xatom.CARDINAL)
        except Exception:  # noqa: BLE001  # reason: the window may be gone
            return (0, 0, 0, 0)
        if not value or len(value) < 4:
            return (0, 0, 0, 0)
        return (int(value[0]), int(value[1]), int(value[2]), int(value[3]))

    def window_rect(self, window_id: int,
                    ) -> Optional[Tuple[int, int, int, int]]:
        """The *frame* rectangle, decorations included.

        Win32's ``GetWindowRect`` returns the frame, and every caller in this
        project is written against that, so returning the client area here
        would be off by the border and title bar on X11 alone — silently, and
        by a different amount per window manager.
        """
        try:
            frame = self._frame(window_id)
            geometry = frame.get_geometry()
            # The frame is a direct child of the root, so its own x/y are
            # already root coordinates. Translating instead would add the
            # window's border width, because XTranslateCoordinates starts
            # from inside the border — measured as a one-pixel error against
            # xwininfo on an undecorated window.
            left, top = int(geometry.x), int(geometry.y)
            return (left, top, left + int(geometry.width),
                    top + int(geometry.height))
        except Exception as error:  # noqa: BLE001  # reason: the window may be gone
            autocontrol_logger.info("window_rect(%s) failed: %r", window_id, error)
            return None

    def window_process_id(self, window_id: int) -> int:
        from Xlib import Xatom

        try:
            value = self._property(self._window(window_id), "_NET_WM_PID",
                                   Xatom.CARDINAL)
        except Exception:  # noqa: BLE001  # reason: the window may be gone
            return 0
        return int(value[0]) if value else 0

    def is_minimized(self, window_id: int) -> bool:
        try:
            states = self._property(self._window(window_id), "_NET_WM_STATE") or []
        except Exception:  # noqa: BLE001  # reason: the window may be gone
            return False
        return self._atom("_NET_WM_STATE_HIDDEN") in list(states)

    # --- acting on one window ----------------------------------------------

    def set_foreground(self, window_id: int) -> None:
        window = self._window(window_id)
        # Source 2 ("pager") is what a window manager honours without the
        # focus-stealing prevention it applies to source 1 ("application").
        self._client_message(window, "_NET_ACTIVE_WINDOW",
                             [2, int(time.time()), 0])
        self._display().flush()

    def restore(self, window_id: int) -> None:
        window = self._window(window_id)
        window.map()
        self._client_message(window, "_NET_ACTIVE_WINDOW",
                             [2, int(time.time()), 0])
        self._display().flush()

    def show(self, window_id: int, cmd_show: int) -> None:
        window = self._window(window_id)
        code = int(cmd_show)
        if code == SW_HIDE:
            window.unmap()
        elif code in (SW_SHOWNORMAL, SW_RESTORE):
            self.restore(window_id)
        elif code in (SW_MINIMIZE, SW_SHOWMINIMIZED):
            self.minimize(window_id)
        elif code == SW_MAXIMIZE:
            # _NET_WM_STATE_ADD is 1; both axes have to be named or the window
            # only grows one way.
            self._client_message(
                window, "_NET_WM_STATE",
                [1, self._atom("_NET_WM_STATE_MAXIMIZED_HORZ"),
                 self._atom("_NET_WM_STATE_MAXIMIZED_VERT"), 2])
        else:
            # Win32 has show codes with no X11 meaning (SW_SHOWNA,
            # SW_FORCEMINIMIZE, …). Guessing at one would move a window in a
            # way the caller did not ask for.
            self._unsupported(f"show(cmd_show={code})")
        self._display().flush()

    def close(self, window_id: int) -> bool:
        try:
            self._client_message(self._window(window_id), "_NET_CLOSE_WINDOW",
                                 [int(time.time()), 2])
            return True
        except Exception as error:  # noqa: BLE001  # reason: report, do not abort
            autocontrol_logger.info("close(%s) failed: %r", window_id, error)
            return False

    def minimize(self, window_id: int) -> bool:
        try:
            # Iconifying is ICCCM, not EWMH: there is no _NET_ message for it,
            # and WM_CHANGE_STATE is what every window manager implements.
            self._client_message(self._window(window_id), "WM_CHANGE_STATE",
                                 [_ICONIC_STATE])
            return True
        except Exception as error:  # noqa: BLE001  # reason: report, do not abort
            autocontrol_logger.info("minimize(%s) failed: %r", window_id, error)
            return False

    def move(self, window_id: int, x: int, y: int,
             width: int, height: int) -> bool:
        """Move and resize the *frame*, matching :meth:`window_rect`.

        Goes through ``_NET_MOVERESIZE_WINDOW`` rather than configuring the
        window directly: under a reparenting window manager a client's own
        x/y are relative to its frame, so a direct ``ConfigureWindow`` asks
        for a position in the wrong coordinate space and the window manager
        applies its own arithmetic on top. Measured against openbox, asking
        for (300, 220) that way landed the window at (302, 260).

        EWMH sizes the *client*, while Win32's ``MoveWindow`` sizes the
        frame, so the decorations come off the requested size — which is what
        makes this round-trip with :meth:`window_rect`.
        """
        try:
            border_left, border_right, border_top, border_bottom = \
                self._frame_extents(window_id)
            client_width = max(1, int(width) - border_left - border_right)
            client_height = max(1, int(height) - border_top - border_bottom)
            # Bits 8-11 say which of x/y/width/height are supplied; bits 12-13
            # are the source indication, and 2 means "pager", which a window
            # manager honours without focus-stealing prevention. Gravity 0
            # leaves the window's own gravity in charge, so x/y place the
            # frame's top-left corner.
            flags = (1 << 8) | (1 << 9) | (1 << 10) | (1 << 11) | (2 << 12)
            self._client_message(
                self._window(window_id), "_NET_MOVERESIZE_WINDOW",
                [flags, int(x), int(y), client_width, client_height])
            return True
        except Exception as error:  # noqa: BLE001  # reason: report, do not abort
            autocontrol_logger.info("move(%s) failed: %r", window_id, error)
            return False

    # --- acting on a window that does not have focus -----------------------

    def post_key(self, window_id: int, keycode: int,
                 character: str = "") -> bool:
        """Send one key to the window without focusing it.

        Delivered with ``XSendEvent``, so it arrives flagged synthetic and
        GTK and Qt discard it by design. This is the X11 counterpart of
        Win32's ``PostMessage`` — best-effort, and useful mainly for the
        older toolkits that do accept it. For input that always lands, focus
        the window and use the ordinary keyboard API.
        """
        from Xlib import X, protocol

        del character  # X11 addresses keys by keycode; the character is Win32's
        try:
            window = self._window(window_id)
            for factory, mask in ((protocol.event.KeyPress, X.KeyPressMask),
                                  (protocol.event.KeyRelease, X.KeyReleaseMask)):
                window.send_event(
                    factory(time=X.CurrentTime, root=self._root(),
                            window=window, same_screen=1, child=X.NONE,
                            root_x=0, root_y=0, event_x=0, event_y=0,
                            state=0, detail=int(keycode)),
                    propagate=True, event_mask=mask)
            self._display().flush()
            return True
        except Exception as error:  # noqa: BLE001  # reason: report, do not abort
            autocontrol_logger.info("post_key(%s) failed: %r", window_id, error)
            return False

    def post_click(self, window_id: int, button: str, x: int, y: int) -> bool:
        """Send one click to the window without focusing it.

        Carries the same synthetic-event caveat as :meth:`post_key`.
        """
        from Xlib import X, protocol

        number = _BUTTONS.get(str(button).lower().removeprefix("mouse_"))
        if number is None:
            self._unsupported(f"post_click(button={button!r})")
        try:
            window = self._window(window_id)
            for factory, mask in (
                    (protocol.event.ButtonPress, X.ButtonPressMask),
                    (protocol.event.ButtonRelease, X.ButtonReleaseMask)):
                window.send_event(
                    factory(time=X.CurrentTime, root=self._root(),
                            window=window, same_screen=1, child=X.NONE,
                            root_x=0, root_y=0, event_x=int(x), event_y=int(y),
                            state=0, detail=number),
                    propagate=True, event_mask=mask)
            self._display().flush()
            return True
        except Exception as error:  # noqa: BLE001  # reason: report, do not abort
            autocontrol_logger.info("post_click(%s) failed: %r", window_id, error)
            return False


def _as_text(value: Any) -> str:
    """Decode a property value that may be bytes, str, or an array of either."""
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, str):
        return value
    try:
        return bytes(value).decode("utf-8", errors="replace").rstrip("\x00")
    except (TypeError, ValueError):
        return str(value)
