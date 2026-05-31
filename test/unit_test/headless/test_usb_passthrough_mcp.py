"""Tests for the first-class ac_usb_* MCP passthrough tools."""
import pytest

from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
from je_auto_control.utils.usb.passthrough.backend import (
    BackendDevice, FakeUsbBackend,
)

_SAMPLE = BackendDevice(vendor_id="1050", product_id="0407", serial="ABC123")

_USB_TOOLS = {
    "ac_usb_passthrough_enable", "ac_usb_passthrough_status",
    "ac_usb_acl_list", "ac_usb_acl_add", "ac_usb_acl_remove",
    "ac_usb_acl_set_default", "ac_usb_loopback_list", "ac_usb_loopback_open",
    "ac_usb_remote_list", "ac_usb_remote_open",
}


@pytest.fixture(autouse=True)
def isolated_usb(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "je_auto_control.utils.usb.passthrough.acl.default_acl_path",
        lambda: tmp_path / "usb_acl.json",
    )
    monkeypatch.setattr(
        "je_auto_control.utils.usb.passthrough.loopback.default_passthrough_backend",
        lambda: FakeUsbBackend(devices=[_SAMPLE]),
    )


def _by_name(read_only=False):
    return {t.name: t for t in build_default_tool_registry(
        read_only=read_only, aliases=False,
    )}


def test_all_usb_tools_registered():
    names = set(_by_name())
    assert _USB_TOOLS <= names


def test_usb_tools_have_valid_schema_and_handler():
    tools = _by_name()
    for name in _USB_TOOLS:
        tool = tools[name]
        assert isinstance(tool.input_schema, dict)
        assert callable(tool.handler)


def test_acl_add_then_list_via_handlers():
    tools = _by_name()
    added = tools["ac_usb_acl_add"].handler(vendor_id="1050", product_id="0407")
    assert added["added"] is True
    listed = tools["ac_usb_acl_list"].handler()
    assert any(r["vendor_id"] == "1050" for r in listed["rules"])


def test_loopback_list_via_handler():
    tools = _by_name()
    tools["ac_usb_acl_add"].handler(vendor_id="1050", product_id="0407")
    devices = tools["ac_usb_loopback_list"].handler()["devices"]
    assert [d["vendor_id"] for d in devices] == ["1050"]


def test_read_only_registry_keeps_reads_drops_writes():
    ro = _by_name(read_only=True)
    # Reads survive the read-only filter…
    assert "ac_usb_acl_list" in ro
    assert "ac_usb_passthrough_status" in ro
    # …state-changing tools are filtered out.
    assert "ac_usb_acl_add" not in ro
    assert "ac_usb_passthrough_enable" not in ro
