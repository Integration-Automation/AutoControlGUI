"""Headless tests for keyboard focus order (tab sequence / WCAG audit / set-focus)."""
import je_auto_control as ac
from je_auto_control.utils.accessibility.backends import base as backend_base
from je_auto_control.utils.accessibility.element import AccessibilityElement
from je_auto_control.utils.focus_order import (
    audit_focus_order, focus_control, is_interactive_role, tab_order,
)


def _el(name, role, bounds):
    return AccessibilityElement(name=name, role=role, bounds=bounds,
                                app_name="demo.exe")


def _sample():
    return [
        _el("Label", "ControlType_50020", (10, 10, 100, 20)),   # Text: skipped
        _el("OK", "ControlType_50000", (10, 100, 50, 20)),      # Button
        _el("Name", "ControlType_50004", (10, 50, 100, 20)),    # Edit
        _el("Agree", "ControlType_50002", (200, 50, 20, 20)),   # CheckBox, same row
        _el("Hidden", "ControlType_50000", (10, 200, 0, 0)),    # Button, zero-area
    ]


def test_is_interactive_role():
    assert is_interactive_role("ControlType_50000") is True       # Button
    assert is_interactive_role("Edit") is True
    assert is_interactive_role("ControlType_50020") is False      # Text
    assert is_interactive_role("AXApplication") is False


def test_tab_order_filters_and_reads():
    order = [el.name for el in tab_order(_sample())]
    # Text excluded; row y=50 (Name then Agree by x) before y=100 before y=200.
    assert order == ["Name", "Agree", "OK", "Hidden"]


def test_audit_flags_zero_area_focusable():
    report = audit_focus_order(_sample())
    assert report["focusable_count"] == 4
    assert report["issue_count"] == 1
    issue = report["issues"][0]
    assert issue["name"] == "Hidden"
    assert issue["issue"] == "zero_area_focusable"
    assert report["order"][0] == {"tab_index": 0, "name": "Name",
                                  "role": "Edit", "bounds": [10, 50, 100, 20]}


def test_audit_empty_list():
    report = audit_focus_order([])
    assert report == {"order": [], "issues": [], "focusable_count": 0,
                      "issue_count": 0}


# --- device seam + wiring --------------------------------------------------

class _FakeBackend(backend_base.AccessibilityBackend):
    name = "fake"
    available = True

    def __init__(self):
        self.focused = []

    def list_elements(self, app_name=None, max_results=200):
        return _sample()

    def set_focus(self, name=None, role=None, app_name=None, automation_id=None):
        self.focused.append(name)
        return True


def _inject(monkeypatch, backend):
    import je_auto_control.utils.accessibility.backends as backends
    monkeypatch.setattr(backends, "_cached_backend", backend, raising=False)


def test_focus_control_dispatch(monkeypatch):
    fake = _FakeBackend()
    _inject(monkeypatch, fake)
    assert focus_control(name="Name", role="edit") is True
    assert fake.focused == ["Name"]


def test_unsupported_backend_raises(monkeypatch):
    from je_auto_control.utils.accessibility.element import (
        AccessibilityNotAvailableError)
    _inject(monkeypatch, backend_base.AccessibilityBackend())
    try:
        focus_control(name="x")
        raised = False
    except AccessibilityNotAvailableError:
        raised = True
    assert raised is True


def test_executor_tab_order_and_audit(monkeypatch):
    _inject(monkeypatch, _FakeBackend())
    from je_auto_control.utils.executor.action_executor import (
        _audit_focus_order, _tab_order)
    order = [e["name"] for e in _tab_order(app_name="demo.exe")["order"]]
    assert order == ["Name", "Agree", "OK", "Hidden"]
    assert _audit_focus_order(app_name="demo.exe")["issue_count"] == 1


def test_wiring():
    known = set(ac.executor.known_commands())
    assert {"AC_tab_order", "AC_audit_focus_order", "AC_focus_control"} <= known
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    names = {t.name for t in build_default_tool_registry()}
    assert {"ac_tab_order", "ac_audit_focus_order", "ac_focus_control"} <= names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    specs = {s.command for s in _build_specs()}
    assert {"AC_tab_order", "AC_audit_focus_order", "AC_focus_control"} <= specs


def test_facade_exports():
    for name in ("is_interactive_role", "tab_order", "audit_focus_order",
                 "focus_control"):
        assert hasattr(ac, name) and name in ac.__all__
