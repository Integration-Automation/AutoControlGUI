"""Headless tests for container selection + views (fake backend seam)."""
import je_auto_control as ac
from je_auto_control.utils.accessibility.backends import base as backend_base
from je_auto_control.utils.selection_view import (
    get_selection, list_views, set_view,
)

_SELECTION = {"items": ["Row 2", "Row 4"], "can_select_multiple": True,
              "is_required": False}
_VIEWS = {"current": "Details", "views": ["List", "Details", "Tiles"]}


class _FakeBackend(backend_base.AccessibilityBackend):
    name = "fake"
    available = True

    def __init__(self):
        self.applied_view = None

    def get_selection(self, name=None, role=None, app_name=None,
                      automation_id=None):
        return dict(_SELECTION)

    def list_views(self, name=None, role=None, app_name=None, automation_id=None):
        return dict(_VIEWS)

    def set_view(self, view="", name=None, role=None, app_name=None,
                 automation_id=None):
        self.applied_view = view
        return view in _VIEWS["views"]


def _inject(monkeypatch, backend):
    import je_auto_control.utils.accessibility.backends as backends
    monkeypatch.setattr(backends, "_cached_backend", backend, raising=False)


def test_get_selection(monkeypatch):
    _inject(monkeypatch, _FakeBackend())
    assert get_selection(name="List") == _SELECTION


def test_list_views(monkeypatch):
    _inject(monkeypatch, _FakeBackend())
    assert list_views(name="Folder") == _VIEWS


def test_set_view_known_and_unknown(monkeypatch):
    fake = _FakeBackend()
    _inject(monkeypatch, fake)
    assert set_view("Tiles", name="Folder") is True
    assert fake.applied_view == "Tiles"
    assert set_view("Nonexistent", name="Folder") is False


def test_unsupported_backend_raises(monkeypatch):
    from je_auto_control.utils.accessibility.element import (
        AccessibilityNotAvailableError)
    _inject(monkeypatch, backend_base.AccessibilityBackend())
    try:
        get_selection(name="x")
        raised = False
    except AccessibilityNotAvailableError:
        raised = True
    assert raised is True


# --- wiring ---------------------------------------------------------------

def test_executor_adapters(monkeypatch):
    _inject(monkeypatch, _FakeBackend())
    from je_auto_control.utils.executor.action_executor import (
        _get_selection, _list_views, _set_view)
    assert _get_selection(name="L")["selection"]["can_select_multiple"] is True
    assert _list_views(name="F")["views"]["current"] == "Details"
    assert _set_view("List", name="F") is True


def test_wiring():
    known = set(ac.executor.known_commands())
    assert {"AC_get_selection", "AC_list_views", "AC_set_view"} <= known
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    names = {t.name for t in build_default_tool_registry()}
    assert {"ac_get_selection", "ac_list_views", "ac_set_view"} <= names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    specs = {s.command for s in _build_specs()}
    assert {"AC_get_selection", "AC_list_views", "AC_set_view"} <= specs


def test_facade_exports():
    for name in ("get_selection", "list_views", "set_view"):
        assert hasattr(ac, name) and name in ac.__all__
