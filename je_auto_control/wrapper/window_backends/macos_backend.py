"""macOS window-management backend, over Quartz and the accessibility API.

Reading and acting are two different APIs on macOS, with two different
permission stories, and this backend needs both:

* **Quartz** (``CGWindowListCopyWindowInfo``) enumerates every on-screen
  window with its id, title, owning pid and bounds. It needs no grant, so
  listing, rectangles and ownership work out of the box.
* **The accessibility API** is the only way to *move*, *close*, *minimise* or
  *raise* someone else's window. It is gated by TCC: the user grants
  Accessibility to the interpreter, and until they do every action silently
  does nothing. :meth:`MacOSWindowBackend.available` reports the Quartz half,
  and each action raises through the base class when AX refuses, rather than
  returning a false success.

Quartz has no window handle that the accessibility API accepts, so a
``CGWindowID`` is matched to its ``AXUIElement`` by owner, title and frame.
That is what the two APIs give us to work with; the alternative is a private
symbol (``_AXUIElementGetWindow``) this project will not depend on.
"""
import sys
from typing import Any, List, Optional, Tuple

from je_auto_control.utils.logging.logging_instance import autocontrol_logger
from je_auto_control.wrapper.window_backends.base import WindowManageBackend

#: ``ShowWindow`` codes with a macOS meaning; see the X11 backend for why the
#: project spells show-state in Win32's numbering.
SW_SHOWNORMAL = 1
SW_SHOWMINIMIZED = 2
SW_MINIMIZE = 6
SW_RESTORE = 9


class MacOSWindowBackend(WindowManageBackend):
    """Quartz for what a window *is*, accessibility for what it *does*."""

    name = "macos-quartz-ax"

    def __init__(self) -> None:
        self.available = sys.platform == "darwin" and self._probe()

    def _probe(self) -> bool:
        try:
            import Quartz  # noqa: F401  # reason: probe import
            import AppKit  # noqa: F401  # reason: probe import
            return True
        except ImportError as error:
            autocontrol_logger.info(
                "macOS window backend unavailable: %r", error)
            return False

    # --- listing, via Quartz -----------------------------------------------

    def _window_info(self) -> List[dict]:
        """Every on-screen window Quartz will admit to, front-most first."""
        import Quartz

        options = (Quartz.kCGWindowListOptionOnScreenOnly
                   | Quartz.kCGWindowListExcludeDesktopElements)
        found = Quartz.CGWindowListCopyWindowInfo(options, Quartz.kCGNullWindowID)
        return list(found or [])

    def list_windows(self) -> List[Tuple[int, str]]:
        import Quartz

        windows = []
        for info in self._window_info():
            # Layer 0 is the ordinary application layer. Menu bars, the Dock
            # and status items live above it and are not windows a caller
            # means when they say "the Safari window".
            if int(info.get(Quartz.kCGWindowLayer, 0) or 0) != 0:
                continue
            number = int(info.get(Quartz.kCGWindowNumber, 0) or 0)
            if not number:
                continue
            windows.append((number, str(info.get(Quartz.kCGWindowName, "") or "")))
        return windows

    def _info_for(self, window_id: int) -> Optional[dict]:
        import Quartz

        for info in self._window_info():
            if int(info.get(Quartz.kCGWindowNumber, 0) or 0) == int(window_id):
                return info
        return None

    def foreground_window(self) -> int:
        import AppKit
        import Quartz

        workspace = AppKit.NSWorkspace.sharedWorkspace()
        frontmost = workspace.frontmostApplication()
        if frontmost is None:
            return 0
        pid = int(frontmost.processIdentifier())
        for info in self._window_info():
            if (int(info.get(Quartz.kCGWindowOwnerPID, 0) or 0) == pid
                    and int(info.get(Quartz.kCGWindowLayer, 0) or 0) == 0):
                # The list is front-to-back, so the owning app's first entry
                # is the window that is actually in front.
                return int(info.get(Quartz.kCGWindowNumber, 0) or 0)
        return 0

    def window_rect(self, window_id: int,
                    ) -> Optional[Tuple[int, int, int, int]]:
        import Quartz

        info = self._info_for(window_id)
        if info is None:
            return None
        bounds = info.get(Quartz.kCGWindowBounds)
        if not bounds:
            return None
        left, top = int(bounds["X"]), int(bounds["Y"])
        return (left, top, left + int(bounds["Width"]),
                top + int(bounds["Height"]))

    def window_process_id(self, window_id: int) -> int:
        import Quartz

        info = self._info_for(window_id)
        if info is None:
            return 0
        return int(info.get(Quartz.kCGWindowOwnerPID, 0) or 0)

    # --- acting, via the accessibility API ---------------------------------

    def _ax_windows_for(self, pid: int) -> list:
        """Every accessibility window belonging to a process."""
        import ApplicationServices as ax

        application = ax.AXUIElementCreateApplication(pid)
        error, windows = ax.AXUIElementCopyAttributeValue(
            application, "AXWindows", None)
        return [] if error or not windows else list(windows)

    def _ax_window(self, window_id: int):
        """The ``AXUIElement`` for a ``CGWindowID``, or None.

        Quartz ids and accessibility elements are separate namespaces with no
        public bridge, so the window is found again inside its owning
        application by frame and title — the two properties both APIs report.
        """
        import Quartz

        info = self._info_for(window_id)
        if info is None:
            return None
        pid = int(info.get(Quartz.kCGWindowOwnerPID, 0) or 0)
        if not pid:
            return None
        bounds = info.get(Quartz.kCGWindowBounds) or {}
        return _best_match(
            self._ax_windows_for(pid),
            (int(bounds.get("X", 0)), int(bounds.get("Y", 0))),
            str(info.get(Quartz.kCGWindowName, "") or ""))

    def _require_ax_window(self, window_id: int, operation: str):
        window = self._ax_window(window_id)
        if window is None:
            raise _refusal(operation, window_id)
        return window

    def is_minimized(self, window_id: int) -> bool:
        import ApplicationServices as ax

        window = self._ax_window(window_id)
        if window is None:
            # A minimised window is not in the on-screen list at all, so
            # failing to find it is itself the answer here.
            return self._info_for(window_id) is None
        _error, value = ax.AXUIElementCopyAttributeValue(
            window, "AXMinimized", None)
        return bool(value)

    def set_foreground(self, window_id: int) -> None:
        import AppKit
        import ApplicationServices as ax

        pid = self.window_process_id(window_id)
        if not pid:
            raise _refusal("set_foreground", window_id)
        running = AppKit.NSRunningApplication.runningApplicationWithProcessIdentifier_(pid)
        if running is not None:
            running.activateWithOptions_(
                AppKit.NSApplicationActivateIgnoringOtherApps)
        # Activating the application brings its front window forward, which is
        # not necessarily the one asked for, so raise that one specifically.
        window = self._ax_window(window_id)
        if window is not None:
            ax.AXUIElementPerformAction(window, "AXRaise")

    def restore(self, window_id: int) -> None:
        import ApplicationServices as ax

        window = self._require_ax_window(window_id, "restore")
        ax.AXUIElementSetAttributeValue(window, "AXMinimized", False)

    def show(self, window_id: int, cmd_show: int) -> None:
        code = int(cmd_show)
        if code in (SW_SHOWNORMAL, SW_RESTORE):
            self.restore(window_id)
        elif code in (SW_MINIMIZE, SW_SHOWMINIMIZED):
            self.minimize(window_id)
        else:
            # macOS has no hide-this-window or maximise-this-window that maps
            # onto the remaining Win32 codes; zoom is not maximise and the
            # difference matters to the caller.
            self._unsupported(f"show(cmd_show={code})")

    def close(self, window_id: int) -> bool:
        import ApplicationServices as ax

        window = self._ax_window(window_id)
        if window is None:
            return False
        error, button = ax.AXUIElementCopyAttributeValue(
            window, "AXCloseButton", None)
        if error or button is None:
            return False
        return not ax.AXUIElementPerformAction(button, "AXPress")

    def minimize(self, window_id: int) -> bool:
        import ApplicationServices as ax

        window = self._ax_window(window_id)
        if window is None:
            return False
        return not ax.AXUIElementSetAttributeValue(window, "AXMinimized", True)

    def move(self, window_id: int, x: int, y: int,
             width: int, height: int) -> bool:
        import ApplicationServices as ax
        import Quartz

        window = self._ax_window(window_id)
        if window is None:
            return False
        position = ax.AXValueCreate(
            Quartz.kAXValueCGPointType, Quartz.CGPoint(float(x), float(y)))
        size = ax.AXValueCreate(
            Quartz.kAXValueCGSizeType,
            Quartz.CGSize(float(width), float(height)))
        moved = ax.AXUIElementSetAttributeValue(window, "AXPosition", position)
        resized = ax.AXUIElementSetAttributeValue(window, "AXSize", size)
        return not moved and not resized

    # post_key / post_click are deliberately left to the base class. macOS has
    # no equivalent of PostMessage or XSendEvent: an event goes to whatever
    # has focus, and there is no way to address one window without raising it.
    # Refusing says so; a "success" that focused something else would not.


def _best_match(candidates: list, wanted_origin: Tuple[int, int],
                wanted_title: str):
    """Pick the accessibility window that is the Quartz window described.

    Frame is the stronger signal and is tried first: a title can be empty, or
    duplicated across an application's windows, while two windows cannot share
    an origin at the same moment.
    """
    import ApplicationServices as ax

    fallback = None
    for window in candidates:
        _error, position = ax.AXUIElementCopyAttributeValue(
            window, "AXPosition", None)
        if _point(position) == wanted_origin:
            return window
        if fallback is None and wanted_title:
            _error, title = ax.AXUIElementCopyAttributeValue(
                window, "AXTitle", None)
            if str(title or "") == wanted_title:
                fallback = window
    return fallback


def _point(value: Any) -> Tuple[int, int]:
    """Read an ``AXValue`` point as ``(x, y)``, or ``(-1, -1)``."""
    import ApplicationServices as ax
    import Quartz

    if value is None:
        return (-1, -1)
    ok, point = ax.AXValueGetValue(value, Quartz.kAXValueCGPointType, None)
    if not ok or point is None:
        return (-1, -1)
    return (int(point.x), int(point.y))


def _refusal(operation: str, window_id: int):
    from je_auto_control.utils.exception.exceptions import (
        AutoControlUnsupportedOperationException,
    )

    return AutoControlUnsupportedOperationException(
        f"{operation}: no accessibility element for window {window_id}. "
        "macOS gates window actions behind Accessibility — grant it to this "
        "interpreter in System Settings > Privacy & Security > Accessibility.",
    )
