"""Headless tests for reactive UIA focus-change waits (fake backend seam)."""
import je_auto_control as ac
from je_auto_control.utils.accessibility.backends import base as backend_base
from je_auto_control.utils.ax_events import wait_for_focus_change

_FOCUSED = {"name": "Username", "role": "ControlType_50004",
            "app_name": "login.exe", "bounds": [10, 20, 200, 24]}


class _FakeBackend(backend_base.AccessibilityBackend):
    name = "fake"
    available = True

    def __init__(self, result=None):
        self.result = result
        self.timeouts = []

    def wait_for_focus_change(self, timeout=5.0):
        self.timeouts.append(timeout)
        return self.result


def _inject(monkeypatch, backend):
    import je_auto_control.utils.accessibility.backends as backends
    monkeypatch.setattr(backends, "_cached_backend", backend, raising=False)


def test_focus_change_returns_element(monkeypatch):
    fake = _FakeBackend(dict(_FOCUSED))
    _inject(monkeypatch, fake)
    assert wait_for_focus_change(timeout=2.0) == _FOCUSED
    assert fake.timeouts == [2.0]


def test_focus_change_timeout_returns_none(monkeypatch):
    _inject(monkeypatch, _FakeBackend(None))
    assert wait_for_focus_change(timeout=0.1) is None


def test_unsupported_backend_raises(monkeypatch):
    from je_auto_control.utils.accessibility.element import (
        AccessibilityNotAvailableError)
    _inject(monkeypatch, backend_base.AccessibilityBackend())  # all _unsupported
    try:
        wait_for_focus_change(timeout=0.1)
        raised = False
    except AccessibilityNotAvailableError:
        raised = True
    assert raised is True


# --- wiring ---------------------------------------------------------------

def test_executor_adapter_wraps_element(monkeypatch):
    _inject(monkeypatch, _FakeBackend(dict(_FOCUSED)))
    from je_auto_control.utils.executor.action_executor import (
        _wait_for_focus_change)
    out = _wait_for_focus_change(1.5)
    assert out["changed"] is True and out["element"]["name"] == "Username"
    _inject(monkeypatch, _FakeBackend(None))
    assert _wait_for_focus_change(0.1)["changed"] is False


def test_wiring():
    known = set(ac.executor.known_commands())
    assert "AC_wait_for_focus_change" in known
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    names = {t.name for t in build_default_tool_registry()}
    assert "ac_wait_for_focus_change" in names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    specs = {s.command for s in _build_specs()}
    assert "AC_wait_for_focus_change" in specs


def test_facade_export():
    assert hasattr(ac, "wait_for_focus_change")
    assert "wait_for_focus_change" in ac.__all__
