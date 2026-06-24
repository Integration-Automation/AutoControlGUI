"""Headless tests for extended control patterns (fake backend via the seam)."""
import je_auto_control as ac
from je_auto_control.utils.accessibility.backends import base as backend_base
from je_auto_control.utils.control_patterns import (
    collapse_control, control_expand_state, control_range, expand_control,
    scroll_control_into_view, select_control_item, set_control_range,
)


class _FakeBackend(backend_base.AccessibilityBackend):
    name = "fake"
    available = True

    def __init__(self):
        self.calls = []

    def expand(self, name=None, role=None, app_name=None, automation_id=None):
        self.calls.append(("expand", {"name": name, "role": role,
                                      "app_name": app_name,
                                      "automation_id": automation_id}))
        return True

    def collapse(self, name=None, role=None, app_name=None, automation_id=None):
        self.calls.append(("collapse", {"name": name, "role": role,
                                        "app_name": app_name,
                                        "automation_id": automation_id}))
        return True

    def expand_state(self, name=None, role=None, app_name=None,
                     automation_id=None):
        return "collapsed"

    def select_item(self, name=None, role=None, app_name=None,
                    automation_id=None):
        self.calls.append(("select", name))
        return True

    def get_range(self, name=None, role=None, app_name=None, automation_id=None):
        return {"value": 30.0, "minimum": 0.0, "maximum": 100.0}

    def set_range_value(self, value, name=None, role=None, app_name=None,
                        automation_id=None):
        self.calls.append(("set_range", value))
        return True

    def scroll_into_view(self, name=None, role=None, app_name=None,
                         automation_id=None):
        return True


def _inject(monkeypatch, backend):
    import je_auto_control.utils.accessibility.backends as backends
    monkeypatch.setattr(backends, "_cached_backend", backend, raising=False)


def test_expand_and_collapse_dispatch(monkeypatch):
    fake = _FakeBackend()
    _inject(monkeypatch, fake)
    assert expand_control(name="Node", role="treeitem") is True
    assert collapse_control(automation_id="tree1") is True
    assert ("expand", {"name": "Node", "role": "treeitem", "app_name": None,
                       "automation_id": None}) in fake.calls


def test_expand_state(monkeypatch):
    _inject(monkeypatch, _FakeBackend())
    assert control_expand_state(name="Node") == "collapsed"


def test_select_item(monkeypatch):
    fake = _FakeBackend()
    _inject(monkeypatch, fake)
    assert select_control_item(name="Option B") is True
    assert fake.calls[0][0] == "select"


def test_range_get_and_set(monkeypatch):
    fake = _FakeBackend()
    _inject(monkeypatch, fake)
    assert control_range(name="Volume") == {"value": 30.0, "minimum": 0.0,
                                            "maximum": 100.0}
    assert set_control_range(75, name="Volume") is True
    assert ("set_range", 75.0) in fake.calls


def test_scroll_into_view(monkeypatch):
    _inject(monkeypatch, _FakeBackend())
    assert scroll_control_into_view(name="Row 50") is True


def test_unsupported_backend_raises(monkeypatch):
    from je_auto_control.utils.accessibility.element import (
        AccessibilityNotAvailableError)
    _inject(monkeypatch, backend_base.AccessibilityBackend())  # all _unsupported
    try:
        expand_control(name="x")
        raised = False
    except AccessibilityNotAvailableError:
        raised = True
    assert raised is True


# --- wiring ---------------------------------------------------------------

def test_wiring():
    known = set(ac.executor.known_commands())
    assert {"AC_expand_control", "AC_set_control_range"} <= known
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    names = {t.name for t in build_default_tool_registry()}
    assert {"ac_expand_control", "ac_set_control_range"} <= names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    specs = {s.command for s in _build_specs()}
    assert {"AC_expand_control", "AC_set_control_range"} <= specs


def test_facade_exports():
    for name in ("expand_control", "collapse_control", "control_expand_state",
                 "select_control_item", "control_range", "set_control_range",
                 "scroll_control_into_view"):
        assert hasattr(ac, name) and name in ac.__all__
