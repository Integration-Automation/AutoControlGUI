"""Headless tests for the uiautomator2-backed Android surface.

Real ``uiautomator2`` is an optional dependency that wants a live
adb device. We stub the device handle with a small recorder so the
tests assert the selector → uiautomator2-API translation and the
executor + MCP wiring without touching real hardware.
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Dict, List

import pytest

from je_auto_control.android import (
    ElementNotFoundError, UIAutomatorDevice, click_element,
    dump_hierarchy, find_element,
)


class _FakeQuery:
    """Stand-in for ``uiautomator2`` selector queries."""

    def __init__(self, available: bool, bounds=(10, 20, 110, 80)) -> None:
        self._available = available
        self._bounds = bounds

    def wait(self, timeout: float) -> bool:  # noqa: ARG002
        return self._available

    @property
    def info(self) -> Dict[str, Any]:
        x1, y1, x2, y2 = self._bounds
        return {"bounds": {"left": x1, "top": y1, "right": x2, "bottom": y2}}


class _FakeHandle:
    """Records every call so tests can assert what uiautomator2 saw."""

    def __init__(self, query: _FakeQuery, hierarchy: str = "<root/>") -> None:
        self._query = query
        self._hierarchy = hierarchy
        self.calls: List[Dict[str, Any]] = []

    def __call__(self, **selectors) -> _FakeQuery:
        self.calls.append({"op": "select", **selectors})
        return self._query

    def click(self, x: int, y: int) -> None:
        self.calls.append({"op": "click", "x": x, "y": y})

    def dump_hierarchy(self) -> str:
        self.calls.append({"op": "dump"})
        return self._hierarchy


def _device(query: _FakeQuery, hierarchy: str = "<root/>") -> tuple:
    handle = _FakeHandle(query, hierarchy)
    device = UIAutomatorDevice(handle=handle)
    return device, handle


# === find / click ===========================================================

def test_find_element_returns_bounds_when_query_matches():
    device, handle = _device(_FakeQuery(True, (5, 10, 105, 60)))
    rect = find_element(text="Login", device=device)
    assert rect == (5, 10, 105, 60)
    assert handle.calls[0] == {"op": "select", "text": "Login"}


def test_find_element_raises_on_timeout():
    device, _ = _device(_FakeQuery(False))
    with pytest.raises(ElementNotFoundError):
        find_element(resource_id="com.app:id/x", device=device, timeout_s=0.0)


def test_find_element_requires_at_least_one_selector():
    device, _ = _device(_FakeQuery(True))
    with pytest.raises(ValueError, match="at least one"):
        find_element(device=device)


def test_click_element_taps_centre_via_handle():
    device, handle = _device(_FakeQuery(True, (100, 200, 300, 400)))
    centre = click_element(description="OK button", device=device)
    assert centre == (200, 300)
    ops = [c["op"] for c in handle.calls]
    assert "click" in ops
    click_call = next(c for c in handle.calls if c["op"] == "click")
    assert (click_call["x"], click_call["y"]) == (200, 300)


def test_dump_hierarchy_returns_xml_string():
    device, _ = _device(_FakeQuery(True), hierarchy="<hierarchy/>")
    assert dump_hierarchy(device=device) == "<hierarchy/>"


# === executor + MCP wiring ==================================================

def test_executor_registers_uiautomator_commands():
    from je_auto_control.utils.executor.action_executor import executor
    commands = executor.known_commands()
    assert {
        "AC_android_find_element",
        "AC_android_click_element",
        "AC_android_dump_hierarchy",
    } <= commands


def test_mcp_registry_exposes_uiautomator_tools():
    from je_auto_control.utils.mcp_server.tools import (
        build_default_tool_registry,
    )
    names = {tool.name for tool in build_default_tool_registry()}
    assert {
        "ac_android_find_element",
        "ac_android_click_element",
        "ac_android_dump_hierarchy",
    } <= names


def test_executor_find_element_dispatches_to_device(monkeypatch):
    captured = {}

    def fake_find(*, text, resource_id, description, class_name,
                  timeout_s, device):
        captured["device"] = device
        captured["text"] = text
        captured["timeout"] = timeout_s
        return (1, 2, 3, 4)

    monkeypatch.setattr(
        "je_auto_control.android.find_element", fake_find,
    )
    from je_auto_control.utils.executor.action_executor import (
        _ac_android_find_element,
    )
    rect = _ac_android_find_element(text="Hello", serial="emulator-5554")
    assert rect == {"x1": 1, "y1": 2, "x2": 3, "y2": 4}
    assert isinstance(captured["device"], UIAutomatorDevice)
    assert captured["device"].serial == "emulator-5554"
    assert captured["text"] == "Hello"


def test_mcp_handler_round_trip(monkeypatch):
    monkeypatch.setattr(
        "je_auto_control.android.click_element",
        lambda **kw: (50, 75),
    )
    from je_auto_control.utils.mcp_server.tools._handlers import (
        android_click_element,
    )
    assert android_click_element(text="Next") == {"x": 50, "y": 75}


# === package import probe ===================================================

def test_android_module_imports_without_uiautomator(monkeypatch):
    """Top-level import must not fail when uiautomator2 is absent."""
    import importlib
    import sys
    # Pretend uiautomator2 is not installed; the module-level imports
    # should still succeed because the dependency loads lazily.
    monkeypatch.setitem(sys.modules, "uiautomator2", None)
    module = importlib.reload(
        importlib.import_module("je_auto_control.android.client"),
    )
    # Instantiating the wrapper is fine; only .handle would fail.
    device = module.UIAutomatorDevice()
    assert device.serial is None
