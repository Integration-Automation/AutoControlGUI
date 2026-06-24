"""Headless tests for native TextPattern reads + find/select/attrs (fake seam)."""
import je_auto_control as ac
from je_auto_control.utils.accessibility.backends import base as backend_base
from je_auto_control.utils.ax_text import (
    control_text_attributes, find_control_text, get_control_text,
    get_selected_text, get_visible_text, select_control_text,
)

_ATTRS = {"font_name": "Consolas", "font_size": 11.0, "bold": True,
          "italic": False, "foreground_color": 16711680}


class _FakeBackend(backend_base.AccessibilityBackend):
    name = "fake"
    available = True

    def __init__(self):
        self.calls = []

    def document_text(self, name=None, role=None, app_name=None,
                      automation_id=None):
        self.calls.append(("document", {"name": name, "role": role,
                                        "app_name": app_name,
                                        "automation_id": automation_id}))
        return "line 1\nline 2\nline 3"

    def selected_text(self, name=None, role=None, app_name=None,
                      automation_id=None):
        self.calls.append(("selected", name))
        return "line 2"

    def visible_text(self, name=None, role=None, app_name=None,
                     automation_id=None):
        self.calls.append(("visible", name))
        return "line 1\nline 2"

    def find_text(self, text="", ignore_case=True, name=None, role=None,
                  app_name=None, automation_id=None):
        self.calls.append(("find", text, ignore_case))
        return "line 2" in str(text)

    def select_text(self, text="", ignore_case=True, name=None, role=None,
                    app_name=None, automation_id=None):
        self.calls.append(("select", text))
        return "line 2" in str(text)

    def text_attributes(self, name=None, role=None, app_name=None,
                        automation_id=None):
        return dict(_ATTRS)


def _inject(monkeypatch, backend):
    import je_auto_control.utils.accessibility.backends as backends
    monkeypatch.setattr(backends, "_cached_backend", backend, raising=False)


def test_document_text_dispatch(monkeypatch):
    fake = _FakeBackend()
    _inject(monkeypatch, fake)
    assert get_control_text(name="Editor", role="document") == "line 1\nline 2\nline 3"
    assert ("document", {"name": "Editor", "role": "document", "app_name": None,
                         "automation_id": None}) in fake.calls


def test_selected_text(monkeypatch):
    fake = _FakeBackend()
    _inject(monkeypatch, fake)
    assert get_selected_text(automation_id="edit1") == "line 2"
    assert fake.calls[0][0] == "selected"


def test_visible_text(monkeypatch):
    fake = _FakeBackend()
    _inject(monkeypatch, fake)
    assert get_visible_text(name="Editor") == "line 1\nline 2"
    assert fake.calls[0][0] == "visible"


def test_find_control_text(monkeypatch):
    fake = _FakeBackend()
    _inject(monkeypatch, fake)
    assert find_control_text("line 2", name="Editor") is True
    assert find_control_text("absent", name="Editor") is False
    assert ("find", "line 2", True) in fake.calls


def test_select_control_text(monkeypatch):
    fake = _FakeBackend()
    _inject(monkeypatch, fake)
    assert select_control_text("line 2", ignore_case=False, name="Editor") is True
    assert ("select", "line 2") in fake.calls


def test_control_text_attributes(monkeypatch):
    _inject(monkeypatch, _FakeBackend())
    assert control_text_attributes(name="Editor") == _ATTRS


def test_unsupported_backend_raises(monkeypatch):
    from je_auto_control.utils.accessibility.element import (
        AccessibilityNotAvailableError)
    _inject(monkeypatch, backend_base.AccessibilityBackend())  # all _unsupported
    try:
        get_control_text(name="x")
        raised = False
    except AccessibilityNotAvailableError:
        raised = True
    assert raised is True


# --- wiring ---------------------------------------------------------------

def test_executor_adapter_wraps_text(monkeypatch):
    _inject(monkeypatch, _FakeBackend())
    from je_auto_control.utils.executor.action_executor import _get_control_text
    assert _get_control_text(name="Editor") == {"text": "line 1\nline 2\nline 3"}


def test_wiring():
    known = set(ac.executor.known_commands())
    assert {"AC_get_control_text", "AC_get_selected_text", "AC_get_visible_text",
            "AC_find_control_text", "AC_select_control_text",
            "AC_control_text_attributes"} <= known
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    names = {t.name for t in build_default_tool_registry()}
    assert {"ac_get_control_text", "ac_find_control_text",
            "ac_select_control_text", "ac_control_text_attributes"} <= names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    specs = {s.command for s in _build_specs()}
    assert {"AC_get_control_text", "AC_find_control_text",
            "AC_select_control_text", "AC_control_text_attributes"} <= specs


def test_facade_exports():
    for name in ("get_control_text", "get_selected_text", "get_visible_text",
                 "find_control_text", "select_control_text",
                 "control_text_attributes"):
        assert hasattr(ac, name) and name in ac.__all__
