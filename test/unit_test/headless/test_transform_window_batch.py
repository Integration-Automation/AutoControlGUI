"""Headless tests for Transform + Window patterns (fake backend seam)."""
import je_auto_control as ac
from je_auto_control.utils.accessibility.backends import base as backend_base
from je_auto_control.utils.transform_window import (
    move_element, resize_element, set_window_state, window_interaction_state,
)


class _FakeBackend(backend_base.AccessibilityBackend):
    name = "fake"
    available = True

    def __init__(self, interaction="ready"):
        self.interaction = interaction
        self.calls = []

    def move_element(self, x=0.0, y=0.0, name=None, role=None, app_name=None,
                     automation_id=None):
        self.calls.append(("move", x, y, name))
        return True

    def resize_element(self, width=0.0, height=0.0, name=None, role=None,
                       app_name=None, automation_id=None):
        self.calls.append(("resize", width, height, name))
        return True

    def set_window_state(self, state="normal", name=None, role=None,
                         app_name=None, automation_id=None):
        self.calls.append(("state", state, name))
        return state in ("normal", "maximized", "minimized")

    def window_interaction_state(self, name=None, role=None, app_name=None,
                                 automation_id=None):
        return self.interaction


def _inject(monkeypatch, backend):
    import je_auto_control.utils.accessibility.backends as backends
    monkeypatch.setattr(backends, "_cached_backend", backend, raising=False)


def test_move_and_resize_dispatch(monkeypatch):
    fake = _FakeBackend()
    _inject(monkeypatch, fake)
    assert move_element(100, 200, name="Panel") is True
    assert resize_element(640, 480, name="Panel") is True
    assert ("move", 100.0, 200.0, "Panel") in fake.calls
    assert ("resize", 640.0, 480.0, "Panel") in fake.calls


def test_set_window_state(monkeypatch):
    fake = _FakeBackend()
    _inject(monkeypatch, fake)
    assert set_window_state("maximized", name="Editor") is True
    assert ("state", "maximized", "Editor") in fake.calls


def test_window_interaction_state(monkeypatch):
    _inject(monkeypatch, _FakeBackend(interaction="blocked_by_modal"))
    assert window_interaction_state(name="Editor") == "blocked_by_modal"


def test_unsupported_backend_raises(monkeypatch):
    from je_auto_control.utils.accessibility.element import (
        AccessibilityNotAvailableError)
    _inject(monkeypatch, backend_base.AccessibilityBackend())
    try:
        move_element(1, 2, name="x")
        raised = False
    except AccessibilityNotAvailableError:
        raised = True
    assert raised is True


def test_base_set_window_state_rejects_unknown():
    # the real Windows backend returns False for an unknown state; the base
    # ABC default still routes through _unsupported, so verify the mapping guard
    from je_auto_control.utils.accessibility.backends import windows_backend
    backend = windows_backend.WindowsAccessibilityBackend.__new__(
        windows_backend.WindowsAccessibilityBackend)
    assert backend.set_window_state("not-a-state", name="x") is False


# --- wiring ---------------------------------------------------------------

def test_executor_adapters(monkeypatch):
    _inject(monkeypatch, _FakeBackend(interaction="not_responding"))
    from je_auto_control.utils.executor.action_executor import (
        _move_element, _set_window_state, _window_interaction_state)
    assert _move_element(1, 2, name="P") is True
    assert _set_window_state("minimized", name="W") is True
    assert _window_interaction_state(name="W") == {"state": "not_responding"}


def test_wiring():
    known = set(ac.executor.known_commands())
    assert {"AC_move_element", "AC_resize_element", "AC_set_window_state",
            "AC_window_interaction_state"} <= known
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    names = {t.name for t in build_default_tool_registry()}
    assert {"ac_move_element", "ac_resize_element", "ac_set_window_state",
            "ac_window_interaction_state"} <= names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    specs = {s.command for s in _build_specs()}
    assert {"AC_move_element", "AC_resize_element", "AC_set_window_state",
            "AC_window_interaction_state"} <= specs


def test_facade_exports():
    for name in ("move_element", "resize_element", "set_window_state",
                 "window_interaction_state"):
        assert hasattr(ac, name) and name in ac.__all__
