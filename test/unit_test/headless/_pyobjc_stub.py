"""A pyobjc stand-in for the macOS window backend, usable off macOS.

`macos_backend.py` imports `Quartz`, `AppKit` and `ApplicationServices`
*inside* its methods, so the module loads on every platform and only the
calls need a Mac. Stubs in `sys.modules` therefore reach all of it from all
nine CI squares rather than the two Darwin ones -- which matters because the
coverage floor is the lowest square.

Unlike the Xlib stub, the constants here are sentinels rather than real
values, and deliberately so: every one of them is either a dictionary key
into an info dict this file also creates, or an opaque token handed straight
back to a function this file also provides. Their numeric values never reach
any arithmetic in the code under test, so pinning them would pin nothing.
What *is* worth pinning is that the names exist at all --
`test_pyobjc_stub_names.py` checks that against the installed frameworks on
the macOS squares.

The accessibility half models one thing carefully: **AX functions return an
error code, where zero means success.** `close()` and `minimize()` return
`not ax.AXUIElementPerformAction(...)`, so a stub that returned a truthy
"success" would invert every one of those tests.

Nothing here is a test; the file is named so pytest does not collect it.
"""
from __future__ import annotations

import sys
import types

#: Quartz's window-info dictionary keys, spelled as pyobjc spells them.
WINDOW_KEYS = (
    "kCGWindowNumber", "kCGWindowName", "kCGWindowLayer",
    "kCGWindowOwnerPID", "kCGWindowBounds",
)

#: The rest of the surface the backend names, by module.
QUARTZ_NAMES = WINDOW_KEYS + (
    "kCGWindowListOptionOnScreenOnly", "kCGWindowListExcludeDesktopElements",
    "kCGNullWindowID", "kAXValueCGPointType", "kAXValueCGSizeType",
    "CGWindowListCopyWindowInfo", "CGPoint", "CGSize",
)
APPKIT_NAMES = (
    "NSWorkspace", "NSRunningApplication",
    "NSApplicationActivateIgnoringOtherApps",
)
AX_NAMES = (
    "AXUIElementCreateApplication", "AXUIElementCopyAttributeValue",
    "AXUIElementSetAttributeValue", "AXUIElementPerformAction",
    "AXValueCreate", "AXValueGetValue",
)

#: What an AX call returns when it worked. Zero, and the backend reads it as
#: `not error`, so this is load-bearing in every action test.
AX_SUCCESS = 0
AX_FAILURE = -25200      # kAXErrorCannotComplete, in spirit


def window_info(number: int, *, name: str = "", layer: int = 0,
                pid: int = 0, bounds=None) -> dict:
    """One entry of what `CGWindowListCopyWindowInfo` returns."""
    info = {
        "kCGWindowNumber": number,
        "kCGWindowName": name,
        "kCGWindowLayer": layer,
        "kCGWindowOwnerPID": pid,
    }
    if bounds is not None:
        left, top, width, height = bounds
        info["kCGWindowBounds"] = {"X": left, "Y": top,
                                   "Width": width, "Height": height}
    return info


class AXElement:
    """An accessibility element: attributes, and what was done to it."""

    def __init__(self, **attributes) -> None:
        self.attributes = dict(attributes)
        self.actions = []
        self.assignments = []
        self.set_error = AX_SUCCESS
        self.action_error = AX_SUCCESS
        self.read_error = AX_SUCCESS


class AXPoint:
    """What `AXValueCreate(kAXValueCGPointType, ...)` hands back."""

    def __init__(self, x, y) -> None:
        self.x = x
        self.y = y


class AXSize:
    def __init__(self, width, height) -> None:
        self.width = width
        self.height = height


class World:
    """The Mac the backend thinks it is talking to."""

    def __init__(self, windows=None, ax_windows=None, frontmost_pid=None,
                 running_pids=None):
        self.windows = list(windows or [])
        self.ax_windows = dict(ax_windows or {})     # pid -> [AXElement]
        self.frontmost_pid = frontmost_pid
        # Whether `NSRunningApplication` still answers for a pid. Separate
        # from `ax_windows` on purpose: an application can quit between the
        # pid lookup and the activation, which is its own branch.
        self.running_pids = (set() if running_pids is None
                             else set(running_pids))
        self.list_options = []
        self.activated = []
        self.ax_list_error = AX_SUCCESS

    # -- Quartz --
    def copy_window_info(self, options, relative_to):
        self.list_options.append((options, relative_to))
        return list(self.windows)

    # -- ApplicationServices --
    def ax_application(self, pid):
        return ("application", int(pid))

    def ax_copy_attribute(self, element, attribute, _placeholder):
        if isinstance(element, tuple) and element[0] == "application":
            if attribute == "AXWindows":
                if self.ax_list_error:
                    return (self.ax_list_error, None)
                return (AX_SUCCESS, self.ax_windows.get(element[1], []))
            return (AX_FAILURE, None)
        if element.read_error:
            return (element.read_error, None)
        if attribute not in element.attributes:
            return (AX_FAILURE, None)
        return (AX_SUCCESS, element.attributes[attribute])

    def ax_set_attribute(self, element, attribute, value):
        element.assignments.append((attribute, value))
        if element.set_error:
            return element.set_error
        element.attributes[attribute] = value
        return AX_SUCCESS

    def ax_perform_action(self, element, action):
        element.actions.append(action)
        return element.action_error

    def ax_value_create(self, kind, value):
        return (kind, value)

    def ax_value_get(self, value, kind, _placeholder):
        if not isinstance(value, tuple) or value[0] != kind:
            return (False, None)
        return (True, value[1])


def install(monkeypatch, world: World) -> World:
    """Put Quartz, AppKit and ApplicationServices in `sys.modules`."""
    quartz = types.ModuleType("Quartz")
    for name in WINDOW_KEYS:
        setattr(quartz, name, name)
    quartz.kCGWindowListOptionOnScreenOnly = 1
    quartz.kCGWindowListExcludeDesktopElements = 16
    quartz.kCGNullWindowID = 0
    quartz.kAXValueCGPointType = "point"
    quartz.kAXValueCGSizeType = "size"
    quartz.CGWindowListCopyWindowInfo = world.copy_window_info
    quartz.CGPoint = AXPoint
    quartz.CGSize = AXSize

    appkit = types.ModuleType("AppKit")
    appkit.NSApplicationActivateIgnoringOtherApps = 2
    appkit.NSWorkspace = _Workspace(world)
    appkit.NSRunningApplication = _RunningApplication(world)

    services = types.ModuleType("ApplicationServices")
    services.AXUIElementCreateApplication = world.ax_application
    services.AXUIElementCopyAttributeValue = world.ax_copy_attribute
    services.AXUIElementSetAttributeValue = world.ax_set_attribute
    services.AXUIElementPerformAction = world.ax_perform_action
    services.AXValueCreate = world.ax_value_create
    services.AXValueGetValue = world.ax_value_get

    for name, module in (("Quartz", quartz), ("AppKit", appkit),
                         ("ApplicationServices", services)):
        monkeypatch.setitem(sys.modules, name, module)
    return world


def install_missing(monkeypatch, name: str = "Quartz") -> None:
    """Make one framework import fail, as a Mac without pyobjc does.

    `None` in `sys.modules` is the import system's own way of recording
    "this one is not there": `import Quartz` then raises ImportError without
    going near the filesystem, which is exactly what the probe is written to
    survive.
    """
    monkeypatch.setitem(sys.modules, name, None)


class _Workspace:
    def __init__(self, world: World) -> None:
        self._world = world

    def sharedWorkspace(self):      # noqa: N802  # reason: the AppKit name
        return self

    def frontmostApplication(self):  # noqa: N802  # reason: the AppKit name
        if self._world.frontmost_pid is None:
            return None
        return types.SimpleNamespace(
            processIdentifier=lambda: self._world.frontmost_pid)


class _RunningApplication:
    def __init__(self, world: World) -> None:
        self._world = world

    def runningApplicationWithProcessIdentifier_(self, pid):  # noqa: N802
        if pid not in self._world.running_pids:
            return None
        world = self._world

        return types.SimpleNamespace(
            activateWithOptions_=lambda options: world.activated.append(
                (pid, options)))
