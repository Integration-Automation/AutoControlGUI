"""Headless tests for realizing virtualized list/grid items (fake backend seam)."""
import je_auto_control as ac
from je_auto_control.utils.accessibility.backends import base as backend_base
from je_auto_control.utils.accessibility.element import AccessibilityElement
from je_auto_control.utils.virtualized import realize_item


class _FakeBackend(backend_base.AccessibilityBackend):
    name = "fake"
    available = True

    def __init__(self, items=None):
        # items: {name: AccessibilityElement} the container can realize
        self.items = items or {}
        self.calls = []

    def find_virtual_item(self, item_name=None, by="name", container_name=None,
                          container_role=None, app_name=None, automation_id=None):
        self.calls.append({"item_name": item_name, "by": by,
                           "container_name": container_name})
        return self.items.get(item_name)


def _inject(monkeypatch, backend):
    import je_auto_control.utils.accessibility.backends as backends
    monkeypatch.setattr(backends, "_cached_backend", backend, raising=False)


def test_realize_item_returns_realized_element(monkeypatch):
    row = AccessibilityElement(name="Order 5000", role="ControlType_50007",
                               bounds=(10, 900, 200, 24), app_name="grid.exe")
    fake = _FakeBackend({"Order 5000": row})
    _inject(monkeypatch, fake)
    element = realize_item("Order 5000", container_name="Orders")
    assert element is row
    assert fake.calls[0]["item_name"] == "Order 5000"
    assert fake.calls[0]["by"] == "name"
    assert fake.calls[0]["container_name"] == "Orders"


def test_realize_item_not_found_returns_none(monkeypatch):
    _inject(monkeypatch, _FakeBackend())
    assert realize_item("missing-row", container_name="Orders") is None


def test_realize_item_by_automation_id(monkeypatch):
    fake = _FakeBackend()
    _inject(monkeypatch, fake)
    realize_item("row-42", by="automation_id", container_name="Grid")
    assert fake.calls[0]["by"] == "automation_id"


def test_unsupported_backend_raises(monkeypatch):
    from je_auto_control.utils.accessibility.element import (
        AccessibilityNotAvailableError)
    _inject(monkeypatch, backend_base.AccessibilityBackend())  # all _unsupported
    try:
        realize_item("x")
        raised = False
    except AccessibilityNotAvailableError:
        raised = True
    assert raised is True


# --- wiring ---------------------------------------------------------------

def test_executor_adapter_wraps_element(monkeypatch):
    row = AccessibilityElement(name="Row 9", role="ControlType_50007",
                               bounds=(1, 2, 3, 4), app_name="x")
    _inject(monkeypatch, _FakeBackend({"Row 9": row}))
    from je_auto_control.utils.executor.action_executor import _realize_item
    out = _realize_item("Row 9", container_name="List")
    assert out["found"] is True
    assert out["element"]["name"] == "Row 9"
    assert _realize_item("nope")["found"] is False


def test_wiring():
    known = set(ac.executor.known_commands())
    assert "AC_realize_item" in known
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    names = {t.name for t in build_default_tool_registry()}
    assert "ac_realize_item" in names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    specs = {s.command for s in _build_specs()}
    assert "AC_realize_item" in specs


def test_facade_export():
    assert hasattr(ac, "realize_item") and "realize_item" in ac.__all__
