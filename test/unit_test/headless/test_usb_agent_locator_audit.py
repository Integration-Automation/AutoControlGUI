"""USB, agent-loop and locator defects from the 2026-09-24 audit (fakes only; no devices, no screen).

The second of two identical USB devices could not be opened by serial; a
transfer whose direction contradicted the endpoint address went through;
close() reattached kernel drivers while interfaces were still claimed; USB/IP,
self-heal and anchor errors escaped the framework family; a non-object
backend decision crashed the agent run; a screenshot failure escaped self-heal;
the a11y audit took tables for tabs.
"""
import types

import pytest

from je_auto_control.utils.exception.exceptions import (
    AutoControlException, AutoControlScreenException, ImageNotFoundException,
)


class _Device:
    idVendor = 0x046D
    idProduct = 0xC52B

    def __init__(self, serial):
        self.serial_number = serial
        self.transfers = []

    def read(self, endpoint, length, timeout):
        self.transfers.append(("read", endpoint))
        return b"\0" * length

    def write(self, endpoint, data, timeout):
        self.transfers.append(("write", endpoint))

    def reset(self):
        pass


def _backend(devices, disposed):
    from je_auto_control.utils.usb.passthrough.backend import LibusbBackend
    backend = LibusbBackend.__new__(LibusbBackend)

    def find(find_all=False, idVendor=None, idProduct=None):
        matches = [d for d in devices
                   if idVendor in (None, d.idVendor) and idProduct in (None, d.idProduct)]
        return matches if find_all else (matches[0] if matches else None)

    backend._usb_core = types.SimpleNamespace(find=find)
    backend._usb_util = types.SimpleNamespace(dispose_resources=disposed.append)
    return backend


def test_the_second_identical_device_opens_by_serial():
    devices = [_Device("AAA"), _Device("BBB")]
    handle = _backend(devices, []).open(vendor_id="046d", product_id="c52b", serial="BBB")
    handle.bulk_transfer(endpoint=0x81, direction="in", length=4)
    assert devices[1].transfers and not devices[0].transfers


@pytest.mark.parametrize("endpoint, direction", [(0x02, "in"), (0x81, "out")])
def test_a_direction_the_endpoint_contradicts_is_refused(endpoint, direction):
    device = _Device("AAA")
    handle = _backend([device], []).open(vendor_id="046d", product_id="c52b")
    with pytest.raises(RuntimeError):
        handle.bulk_transfer(endpoint=endpoint, direction=direction, data=b"xyz", length=3)
    assert device.transfers == []


def test_close_releases_the_claimed_interfaces():
    disposed = []
    device = _Device("AAA")
    handle = _backend([device], disposed).open(vendor_id="046d", product_id="c52b")
    handle.close()
    assert disposed == [device]


def test_the_errors_are_in_the_framework_family():
    from je_auto_control.utils.anchor_locator.locator import AnchorLocatorError
    from je_auto_control.utils.self_healing.locator import SelfHealError
    from je_auto_control.utils.usbip.protocol import UsbIpError
    for error in (UsbIpError, SelfHealError, AnchorLocatorError):
        assert issubclass(error, AutoControlException), error


class _Backend:
    def __init__(self, decisions):
        self._decisions = list(decisions)

    def decide_next_action(self, _goal, _shot, _steps):
        return self._decisions.pop(0)


@pytest.mark.parametrize("decisions", [
    [{"tool": "AC_type", "input": "hello"}, {"stop": True}],
    [{"tool": "AC_type", "input": ["a", "b"]}, {"stop": True}],
    [None],
])
def test_a_malformed_decision_does_not_crash_the_run(decisions):
    from je_auto_control.utils.agent.agent_loop import AgentLoop
    loop = AgentLoop(_Backend(decisions), tool_runner=lambda *_a: None,
                     screenshot_fn=lambda: b"")
    loop.run("goal")


def test_a_screenshot_failure_in_the_vlm_fallback_is_a_miss(monkeypatch):
    from je_auto_control.utils.self_healing import locator
    from je_auto_control.utils.vision import vlm_api
    from je_auto_control.wrapper import auto_control_image

    def no_template(*_a, **_k):
        raise ImageNotFoundException("no template")

    def no_screen(*_a, **_k):
        raise AutoControlScreenException("capture failed")

    monkeypatch.setattr(auto_control_image, "locate_image_center", no_template)
    monkeypatch.setattr(vlm_api, "locate_by_description", no_screen)
    coords, error = locator._try_vlm("the OK button", None, None)
    assert coords is None and "capture failed" in error


@pytest.mark.parametrize("role, interactive", [
    ("table", False), ("table cell", False), ("DataTable", False),
    ("tab", True), ("TabItem", True), ("push button", True),
])
def test_tables_are_not_tabs(role, interactive):
    from je_auto_control.utils.a11y_audit.audit import is_interactive
    assert is_interactive(role) is interactive
