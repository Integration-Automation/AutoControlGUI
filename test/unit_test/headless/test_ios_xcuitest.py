"""Headless tests for the iOS XCUITest surface.

``facebook-wda`` is an optional dependency that wants a live
WebDriverAgent endpoint. We stub the device handle with a recorder
so the tests assert the selector → wda-API translation and
executor / MCP wiring without touching real hardware.
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Dict, List

import pytest

from je_auto_control.ios import (
    ElementNotFoundError, IOSDevice,
    click_element, dump_source, find_element, screen_size, screenshot,
    tap, type_text,
)


class _FakeBounds:
    def __init__(self, x: int, y: int, width: int, height: int) -> None:
        self.x = x
        self.y = y
        self.width = width
        self.height = height


class _FakeQuery:
    def __init__(self, available: bool, bounds=_FakeBounds(10, 20, 100, 60)) -> None:
        self._available = available
        self._bounds = bounds

    def wait(self, timeout: float) -> bool:  # noqa: ARG002
        return self._available

    @property
    def bounds(self) -> _FakeBounds:
        return self._bounds


class _FakeHandle:
    def __init__(self, query: _FakeQuery, source_xml: str = "<root/>") -> None:
        self._query = query
        self._source = source_xml
        self.calls: List[Dict[str, Any]] = []

    def __call__(self, **selectors) -> _FakeQuery:
        self.calls.append({"op": "select", **selectors})
        return self._query

    def tap(self, x: int, y: int) -> None:
        self.calls.append({"op": "tap", "x": x, "y": y})

    def send_keys(self, text: str) -> None:
        self.calls.append({"op": "send_keys", "text": text})

    def window_size(self) -> Dict[str, int]:
        return {"width": 390, "height": 844}

    def source(self) -> str:
        return self._source

    def screenshot(self, file_path: str) -> None:
        self.calls.append({"op": "screenshot", "path": file_path})
        # Write a tiny PNG so file existence assertions in callers pass.
        from PIL import Image
        Image.new("RGB", (4, 4), (255, 0, 0)).save(file_path, format="PNG")


def _device(query: _FakeQuery, source_xml: str = "<root/>") -> tuple:
    handle = _FakeHandle(query, source_xml)
    device = IOSDevice(handle=handle)
    return device, handle


# === input ==================================================================

def test_tap_dispatches_via_handle():
    device, handle = _device(_FakeQuery(True))
    tap(120, 240, device=device)
    assert handle.calls == [{"op": "tap", "x": 120, "y": 240}]


def test_type_text_calls_send_keys():
    device, handle = _device(_FakeQuery(True))
    type_text("hello", device=device)
    assert handle.calls == [{"op": "send_keys", "text": "hello"}]


def test_type_text_requires_str():
    device, _ = _device(_FakeQuery(True))
    with pytest.raises(TypeError):
        type_text(123, device=device)  # type: ignore[arg-type]


# === screen =================================================================

def test_screen_size_returns_dict_pair():
    device, _ = _device(_FakeQuery(True))
    assert screen_size(device=device) == (390, 844)


def test_screenshot_writes_file(tmp_path):
    device, handle = _device(_FakeQuery(True))
    target = tmp_path / "frame.png"
    out = screenshot(str(target), device=device)
    assert out == str(target)
    assert target.exists()
    assert any(c["op"] == "screenshot" for c in handle.calls)


# === find / click ===========================================================

def test_find_element_returns_bounds():
    device, handle = _device(_FakeQuery(True, _FakeBounds(50, 50, 200, 100)))
    rect = find_element(name="Sign in", device=device)
    assert rect == (50, 50, 250, 150)
    assert handle.calls[0] == {"op": "select", "name": "Sign in"}


def test_find_element_raises_on_timeout():
    device, _ = _device(_FakeQuery(False))
    with pytest.raises(ElementNotFoundError):
        find_element(name="Missing", device=device, timeout_s=0.0)


def test_find_element_requires_selector():
    device, _ = _device(_FakeQuery(True))
    with pytest.raises(ValueError, match="at least one"):
        find_element(device=device)


def test_click_element_taps_centre():
    device, handle = _device(_FakeQuery(True, _FakeBounds(100, 200, 200, 100)))
    centre = click_element(class_name="XCUIElementTypeButton", device=device)
    assert centre == (200, 250)
    tap_calls = [c for c in handle.calls if c["op"] == "tap"]
    assert tap_calls == [{"op": "tap", "x": 200, "y": 250}]


def test_dump_source_returns_xml():
    device, _ = _device(_FakeQuery(True), source_xml="<XCUIElementTypeWindow/>")
    assert dump_source(device=device) == "<XCUIElementTypeWindow/>"


# === executor + MCP wiring ==================================================

_EXPECTED_AC_COMMANDS = {
    "AC_ios_tap", "AC_ios_swipe", "AC_ios_type", "AC_ios_screenshot",
    "AC_ios_find_element", "AC_ios_click_element", "AC_ios_dump_source",
}
_EXPECTED_MCP_TOOLS = {
    "ac_ios_tap", "ac_ios_swipe", "ac_ios_type", "ac_ios_screenshot",
    "ac_ios_find_element", "ac_ios_click_element", "ac_ios_dump_source",
}


def test_executor_registers_ios_commands():
    from je_auto_control.utils.executor.action_executor import executor
    assert _EXPECTED_AC_COMMANDS <= executor.known_commands()


def test_mcp_registry_exposes_ios_tools():
    from je_auto_control.utils.mcp_server.tools import (
        build_default_tool_registry,
    )
    names = {tool.name for tool in build_default_tool_registry()}
    assert _EXPECTED_MCP_TOOLS <= names


def test_executor_tap_routes_through_ios_module(monkeypatch):
    seen = {}

    def fake_tap(x, y, *, device):
        seen["coords"] = (x, y)
        seen["device"] = device

    monkeypatch.setattr("je_auto_control.ios.tap", fake_tap)
    from je_auto_control.utils.executor.action_executor import _ac_ios_tap
    result = _ac_ios_tap(x=11, y=22, url="http://example:8100")
    assert result == {"x": 11, "y": 22}
    assert seen["coords"] == (11, 22)
    assert seen["device"].url == "http://example:8100"


# === optional-dep + import probe ============================================

def test_ios_package_imports_without_wda(monkeypatch):
    import importlib
    import sys
    monkeypatch.setitem(sys.modules, "wda", None)
    module = importlib.reload(
        importlib.import_module("je_auto_control.ios.client"),
    )
    device = module.IOSDevice()
    assert device.url == module.IOSDevice.DEFAULT_URL
