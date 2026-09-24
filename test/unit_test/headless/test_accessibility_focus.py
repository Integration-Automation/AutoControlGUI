"""The element holding keyboard focus: each backend, the public API, and its surfaces.

The accessibility recorder claimed to follow focus but observed whichever
element a search met first, because no backend could say what was focused.
Windows asks UIA (``GetFocusedElement``), Linux looks for ``STATE_FOCUSED``
inside ``STATE_ACTIVE`` windows, macOS reads the frontmost application's
``AXFocusedUIElement``. Every backend here runs against doubles -- no bus, no
COM, no pyobjc -- and nothing touches real input.
"""
import sys
import types

import pytest

from headless import _pyobjc_stub as objc_stub
from headless._pyobjc_stub import AXElement
from headless._uia_doubles import Automation, RawElement, Rect, UiaModule
from je_auto_control.utils.accessibility import accessibility_api as api
from je_auto_control.utils.accessibility import recorder as recorder_module
from je_auto_control.utils.accessibility.backends import windows_backend as win
from je_auto_control.utils.accessibility.backends import windows_query
from je_auto_control.utils.accessibility.backends.base import AccessibilityBackend
from je_auto_control.utils.accessibility.backends.macos_backend import (
    MacOSAccessibilityBackend,
)
from je_auto_control.utils.accessibility.element import (
    AccessibilityElement, AccessibilityNotAvailableError,
)

FIELD = AccessibilityElement(name="Search", role="edit", bounds=(10, 20, 100, 24),
                             app_name="notepad.exe")


class _FocusBackend(AccessibilityBackend):
    """A backend whose focus answer the test sets."""

    name = "fake"
    available = True

    def __init__(self, focused=None, first=None) -> None:
        self.focused = focused
        self.first = first

    def focused_element(self):
        return self.focused

    def list_elements(self, app_name=None, max_results=200, window_title=None):
        return [] if self.first is None else [self.first]


class _NoFocusBackend(_FocusBackend):
    """A backend written before focus existed: the base class answers."""

    focused_element = AccessibilityBackend.focused_element


@pytest.fixture
def use_backend(monkeypatch):
    def _use(backend):
        monkeypatch.setattr(api, "get_backend", lambda: backend)
        return backend
    return _use


# --- base contract ------------------------------------------------------------

def test_a_backend_without_focus_support_says_so():
    with pytest.raises(AccessibilityNotAvailableError, match="focused_element"):
        AccessibilityBackend().focused_element()


# --- public API ---------------------------------------------------------------

def test_the_api_returns_the_focused_element(use_backend):
    use_backend(_FocusBackend(focused=FIELD))
    assert api.focused_accessibility_element() is FIELD


def test_nothing_focused_is_none(use_backend):
    use_backend(_FocusBackend(focused=None))
    assert api.focused_accessibility_element() is None


def test_app_name_filters_the_answer(use_backend):
    use_backend(_FocusBackend(focused=FIELD))
    assert api.focused_accessibility_element(app_name="notepad.exe") is FIELD
    assert api.focused_accessibility_element(app_name="calc.exe") is None


# --- recorder -----------------------------------------------------------------

def test_the_recorder_follows_focus_rather_than_the_first_element(use_backend):
    other = AccessibilityElement(name="Menu", role="menu", bounds=(0, 0, 50, 20),
                                 app_name="notepad.exe")
    use_backend(_FocusBackend(focused=FIELD, first=other))
    snapshot = recorder_module._default_fetcher(None)
    assert snapshot["name"] == "Search"
    assert snapshot["role"] == "edit"


def test_the_recorder_falls_back_where_focus_is_unreadable(use_backend):
    other = AccessibilityElement(name="Menu", role="menu", bounds=(0, 0, 50, 20),
                                 app_name="notepad.exe")
    use_backend(_NoFocusBackend(first=other))
    assert recorder_module._default_fetcher(None)["name"] == "Menu"


def test_the_recorder_sees_focus_move_between_fields(use_backend):
    backend = use_backend(_FocusBackend(focused=FIELD))
    recorder = recorder_module.AccessibilityRecorder()
    first = recorder.sample_once()
    backend.focused = AccessibilityElement(name="Replace", role="edit", bounds=(10, 60, 100, 24),
                                           app_name="notepad.exe")
    second = recorder.sample_once()
    assert (first.kind, first.name) == ("focus", "Search")
    assert (second.kind, second.name) == ("focus", "Replace")


# --- Windows (UIA) ------------------------------------------------------------

class _FocusAutomation(Automation):
    def __init__(self, focused=None, error=None) -> None:
        super().__init__()
        self.focused = focused
        self.error = error

    def GetFocusedElement(self):    # noqa: N802  # reason: the UIA name
        if self.error is not None:
            raise self.error
        return self.focused


@pytest.fixture
def windows_backend(monkeypatch):
    monkeypatch.setattr(win, "_is_available", lambda: True)
    monkeypatch.setattr(win, "_process_name", lambda pid: f"app{pid}.exe")
    instance = win.WindowsAccessibilityBackend()
    instance._uia_module = UiaModule()
    return instance


def test_windows_converts_the_focused_uia_element(windows_backend):
    raw = RawElement(name="Search", control_type=50004,
                     rect=Rect(10, 20, 110, 44), process_id=7)
    windows_backend._automation = _FocusAutomation(focused=raw)
    element = windows_backend.focused_element()
    assert (element.name, element.role) == ("Search", "ControlType_50004")
    assert element.bounds == (10, 20, 100, 24)
    assert element.app_name == "app7.exe"


def test_windows_treats_a_null_focus_pointer_as_nothing(windows_backend):
    class _NullPointer:
        def __bool__(self):
            return False
    windows_backend._automation = _FocusAutomation(focused=_NullPointer())
    assert windows_backend.focused_element() is None


def test_windows_answers_none_when_uia_cannot_see_the_focus(windows_backend):
    windows_backend._automation = _FocusAutomation(error=OSError("secure desktop"))
    assert windows_backend.focused_element() is None


def test_the_query_helper_only_swallows_uia_errors():
    automation = _FocusAutomation(error=KeyError("a bug, not a UIA answer"))
    with pytest.raises(KeyError):
        windows_query.focused_raw(automation)


# --- Linux (AT-SPI) -----------------------------------------------------------

atspi = pytest.importorskip(
    "je_auto_control.utils.accessibility.backends.linux_backend",
    exc_type=ImportError)

ROOT = ("registry", "/root")
ACTIVE = 1 << 1
FOCUSED = 1 << 12


class _Bus:
    """Just the AT-SPI reads the focus search makes."""

    def __init__(self, tree, names=None, roles=None, states=None) -> None:
        self.tree, self.names = tree, names or {}
        self.roles, self.states = roles or {}, states or {}
        self.visited = []

    def __enter__(self):
        return self

    def __exit__(self, *_exception):
        return None

    root = ROOT

    def children(self, reference):
        self.visited.append(reference)
        return list(self.tree.get(reference, []))

    def property(self, reference, name, interface=None):
        return self.names.get(reference, "")

    def role_name(self, reference):
        return self.roles.get(reference, "")

    def state(self, reference):
        return self.states.get(reference, 0)

    def extents(self, reference):
        return (0, 0, 10, 10)


def _linux(monkeypatch, bus):
    monkeypatch.setattr(atspi, "_AtspiConnection", lambda: bus)
    backend = atspi.LinuxAccessibilityBackend.__new__(atspi.LinuxAccessibilityBackend)
    backend.available = True
    return backend


def test_linux_finds_the_focused_accessible_in_the_active_window(monkeypatch):
    app, inactive, active = ("a", "/app"), ("a", "/w1"), ("a", "/w2")
    field, other = ("a", "/field"), ("a", "/other")
    bus = _Bus(tree={ROOT: [app], app: [inactive, active],
                     inactive: [other], active: [field]},
               names={app: "gedit", field: "Find"},
               roles={field: "text"},
               states={active: ACTIVE, field: FOCUSED, other: FOCUSED})
    element = _linux(monkeypatch, bus).focused_element()
    assert (element.name, element.role, element.app_name) == ("Find", "text", "gedit")
    assert inactive not in bus.visited, "an inactive window is never searched"


def test_linux_without_an_active_window_answers_none(monkeypatch):
    app, window = ("a", "/app"), ("a", "/w")
    bus = _Bus(tree={ROOT: [app], app: [window]}, states={window: 0})
    assert _linux(monkeypatch, bus).focused_element() is None


def test_linux_search_is_bounded(monkeypatch):
    app, window = ("a", "/app"), ("a", "/w")
    rows = [("a", f"/row{index}") for index in range(50)]
    bus = _Bus(tree={ROOT: [app], app: [window], window: rows},
               states={window: ACTIVE})
    found = atspi._focused_below(bus, window, "big", limit=10)
    assert found is None
    assert len(bus.visited) <= 10


def test_linux_without_a_bus_refuses():
    backend = atspi.LinuxAccessibilityBackend.__new__(atspi.LinuxAccessibilityBackend)
    backend.available = False
    with pytest.raises(AccessibilityNotAvailableError):
        backend.focused_element()


# --- macOS (AX) ---------------------------------------------------------------

class _MacWorld(objc_stub.World):
    def __init__(self, focused=None) -> None:
        super().__init__()
        self.focused = focused
        self.asked = []

    def ax_application(self, pid):
        self.asked.append(pid)
        attributes = {} if self.focused is None else {"AXFocusedUIElement": self.focused}
        return AXElement(**attributes)


class _Front:
    def localizedName(self):        # noqa: N802  # reason: the AppKit name
        return "TextEdit"

    def processIdentifier(self):    # noqa: N802  # reason: the AppKit name
        return 42


def _mac(monkeypatch, world, front=_Front()):
    objc_stub.install(monkeypatch, world)
    appkit = types.ModuleType("AppKit")
    appkit.NSWorkspace = types.SimpleNamespace(
        sharedWorkspace=lambda: types.SimpleNamespace(frontmostApplication=lambda: front))
    monkeypatch.setitem(sys.modules, "AppKit", appkit)
    return MacOSAccessibilityBackend()


def test_macos_reads_the_frontmost_applications_focus(monkeypatch):
    world = _MacWorld(focused=AXElement(AXRole="AXTextField", AXTitle="Body"))
    element = _mac(monkeypatch, world).focused_element()
    assert (element.name, element.role) == ("Body", "AXTextField")
    assert (element.app_name, element.process_id) == ("TextEdit", 42)
    assert world.asked == [42]


def test_macos_with_nothing_focused_answers_none(monkeypatch):
    assert _mac(monkeypatch, _MacWorld(focused=None)).focused_element() is None


def test_macos_with_no_frontmost_application_answers_none(monkeypatch):
    assert _mac(monkeypatch, _MacWorld(), front=None).focused_element() is None


# --- surfaces -----------------------------------------------------------------

def test_the_command_returns_the_focused_element_as_a_dict(use_backend):
    from je_auto_control.utils.executor.action_executor import executor
    use_backend(_FocusBackend(focused=FIELD))
    result = executor.event_dict["AC_a11y_focused"]()
    assert result["name"] == "Search"
    assert executor.event_dict["AC_a11y_focused"](app_name="calc.exe") is None


def test_the_mcp_tool_returns_the_focused_element(use_backend):
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    use_backend(_FocusBackend(focused=FIELD))
    tool = {tool.name: tool for tool in build_default_tool_registry()}["ac_a11y_focused"]
    assert tool.handler()["role"] == "edit"


def test_the_feature_is_exported_and_has_a_builder_spec():
    import je_auto_control as ac
    from je_auto_control.gui.script_builder.command_schema import COMMAND_SPECS
    assert "focused_accessibility_element" in ac.__all__
    assert "AC_a11y_focused" in COMMAND_SPECS
