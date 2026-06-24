"""Headless tests for rich UIA element property reads (fake backend seam)."""
import je_auto_control as ac
from je_auto_control.utils.accessibility.backends import base as backend_base
from je_auto_control.utils.ax_props import (
    get_element_properties, is_element_enabled,
)

_PROPS = {"enabled": False, "offscreen": True, "help_text": "Save the file",
          "item_status": "invalid", "accelerator_key": "Ctrl+S",
          "access_key": "S", "orientation": 0}


class _FakeBackend(backend_base.AccessibilityBackend):
    name = "fake"
    available = True

    def __init__(self, props=None):
        self.props = props
        self.calls = []

    def get_properties(self, name=None, role=None, app_name=None,
                       automation_id=None):
        self.calls.append({"name": name, "role": role})
        return self.props


def _inject(monkeypatch, backend):
    import je_auto_control.utils.accessibility.backends as backends
    monkeypatch.setattr(backends, "_cached_backend", backend, raising=False)


def test_get_element_properties_dispatch(monkeypatch):
    fake = _FakeBackend(dict(_PROPS))
    _inject(monkeypatch, fake)
    props = get_element_properties(name="Save", role="button")
    assert props == _PROPS
    assert fake.calls[0] == {"name": "Save", "role": "button"}


def test_get_element_properties_not_found(monkeypatch):
    _inject(monkeypatch, _FakeBackend(None))
    assert get_element_properties(name="missing") is None


def test_is_element_enabled_reads_flag(monkeypatch):
    _inject(monkeypatch, _FakeBackend(dict(_PROPS)))
    assert is_element_enabled(name="Save") is False
    _inject(monkeypatch, _FakeBackend({"enabled": True}))
    assert is_element_enabled(name="OK") is True


def test_is_element_enabled_none_when_not_found(monkeypatch):
    _inject(monkeypatch, _FakeBackend(None))
    assert is_element_enabled(name="x") is None


def test_unsupported_backend_raises(monkeypatch):
    from je_auto_control.utils.accessibility.element import (
        AccessibilityNotAvailableError)
    _inject(monkeypatch, backend_base.AccessibilityBackend())  # all _unsupported
    try:
        get_element_properties(name="x")
        raised = False
    except AccessibilityNotAvailableError:
        raised = True
    assert raised is True


# --- wiring ---------------------------------------------------------------

def test_executor_adapter_wraps_props(monkeypatch):
    _inject(monkeypatch, _FakeBackend(dict(_PROPS)))
    from je_auto_control.utils.executor.action_executor import (
        _get_element_properties)
    out = _get_element_properties(name="Save")
    assert out["found"] is True
    assert out["properties"]["accelerator_key"] == "Ctrl+S"


def test_wiring():
    known = set(ac.executor.known_commands())
    assert "AC_get_element_properties" in known
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    names = {t.name for t in build_default_tool_registry()}
    assert "ac_get_element_properties" in names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    specs = {s.command for s in _build_specs()}
    assert "AC_get_element_properties" in specs


def test_facade_exports():
    for name in ("get_element_properties", "is_element_enabled"):
        assert hasattr(ac, name) and name in ac.__all__
