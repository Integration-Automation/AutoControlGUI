"""Headless tests for native UI control actions (get/set/invoke/toggle).

A fake accessibility backend is injected, so the tests exercise the API,
executor commands and MCP wiring without any real UIAutomation/AX/comtypes
or a live GUI. The real Windows UIA path is platform code, validated the
same way the rest of the backend is.
"""
import pytest

import je_auto_control as ac
from je_auto_control.utils.accessibility import accessibility_api as api
from je_auto_control.utils.accessibility.backends.base import (
    AccessibilityBackend,
)
from je_auto_control.utils.accessibility.backends.null_backend import (
    NullAccessibilityBackend,
)
from je_auto_control.utils.accessibility.element import (
    AccessibilityElement, AccessibilityNotAvailableError,
)


class _FakeBackend(AccessibilityBackend):
    name = "fake"
    available = True

    def __init__(self):
        self.values = {"Username": "alice"}
        self.invoked = []
        self.toggled = []

    def list_elements(self, app_name=None, max_results=200):
        return [AccessibilityElement(name="Username", role="edit",
                                     bounds=(0, 0, 10, 10))]

    def get_value(self, name=None, role=None, app_name=None,
                  automation_id=None):
        return self.values.get(name)

    def set_value(self, value, name=None, role=None, app_name=None,
                  automation_id=None):
        self.values[name] = value
        return True

    def invoke(self, name=None, role=None, app_name=None, automation_id=None):
        self.invoked.append(name)
        return True

    def toggle(self, name=None, role=None, app_name=None, automation_id=None):
        self.toggled.append(name)
        return True


@pytest.fixture()
def fake(monkeypatch):
    backend = _FakeBackend()
    monkeypatch.setattr(api, "get_backend", lambda: backend)
    return backend


def test_get_value(fake):
    assert ac.control_get_value(name="Username") == "alice"
    assert ac.control_get_value(name="Missing") is None


def test_set_value(fake):
    assert ac.control_set_value("bob", name="Username") is True
    assert fake.values["Username"] == "bob"


def test_invoke(fake):
    assert ac.control_invoke(name="OK") is True
    assert "OK" in fake.invoked


def test_toggle(fake):
    assert ac.control_toggle(name="Remember me") is True
    assert "Remember me" in fake.toggled


def test_executor_commands(fake):
    ac.execute_action([
        ["AC_control_set_value", {"value": "zoe", "name": "Username"}],
        ["AC_control_invoke", {"name": "Login"}],
        ["AC_control_toggle", {"name": "Stay signed in"}],
    ])
    assert fake.values["Username"] == "zoe"
    assert "Login" in fake.invoked
    assert "Stay signed in" in fake.toggled


def test_facade_and_executor_registered(fake):
    assert ac.control_get_value is api.control_get_value
    assert {"AC_control_get_value", "AC_control_set_value",
            "AC_control_invoke", "AC_control_toggle"} <= ac.executor.known_commands()


def test_mcp_tools_registered():
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    names = {t.name for t in build_default_tool_registry()}
    assert {"ac_control_get_value", "ac_control_set_value",
            "ac_control_invoke", "ac_control_toggle"} <= names


def test_unsupported_backend_raises_clearly():
    backend = NullAccessibilityBackend()
    for call in (lambda: backend.get_value(name="x"),
                 lambda: backend.set_value("v", name="x"),
                 lambda: backend.invoke(name="x"),
                 lambda: backend.toggle(name="x")):
        with pytest.raises(AccessibilityNotAvailableError):
            call()


def test_builder_specs_present_and_wired():
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    known = ac.executor.known_commands()
    cmds = {s.command for s in _build_specs()}
    assert {"AC_control_get_value", "AC_control_set_value",
            "AC_control_invoke", "AC_control_toggle"} <= cmds
    assert {"AC_control_get_value", "AC_control_set_value",
            "AC_control_invoke", "AC_control_toggle"} <= known
