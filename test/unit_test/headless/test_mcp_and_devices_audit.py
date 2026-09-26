"""MCP handler and device-helper defects from the 2026-09-24 audit (fakes only; no desktop, no devices).

An OverflowError or IndexError from one argument left an MCP request
unanswered; a failed drag left the button held; sampling replies over HTTP
were dropped; waits crashed on an infinite poll and never looked with
timeout=0; a USB credit arriving between check and wait was missed, two
transfers on one claim swapped data, a failed send leaked its pending entry
and malformed host replies escaped; a callback swallowed assertion failures;
gamepad errors escaped the family; an empty clipboard payload could not be
set; NaN volumes and text timeouts raised bare errors.
"""
import json
import threading
import types

import pytest

from je_auto_control.utils.exception.exceptions import (
    AutoControlActionException, AutoControlAssertionException, AutoControlException,
)
from je_auto_control.utils.mcp_server import _protocol
from je_auto_control.utils.mcp_server.tools import _handlers_input, _handlers_screen
from je_auto_control.utils.mcp_server.tools._handlers_locators import to_model, to_physical
from je_auto_control.utils.mcp_server.tools._handlers_qa import audit_contrast


@pytest.mark.parametrize("error", [OverflowError, IndexError, ZeroDivisionError])
def test_a_tool_error_from_an_argument_is_contained(error):
    assert issubclass(error, _protocol._DISPATCH_ERRORS)


def test_a_failed_drag_releases_the_button(monkeypatch):
    from je_auto_control.wrapper import auto_control_mouse
    events = []

    def move(x, y):
        events.append(("move", x, y))
        if x > 10_000:
            raise AutoControlException("outside the screen")

    monkeypatch.setattr(auto_control_mouse, "set_mouse_position", move)
    monkeypatch.setattr(auto_control_mouse, "press_mouse", lambda *a: events.append(("press",)))
    monkeypatch.setattr(auto_control_mouse, "release_mouse", lambda *a: events.append(("release",)))
    with pytest.raises(AutoControlException):
        _handlers_input.drag(10, 10, 2 ** 31, 10)
    assert events[-1] == ("release",)


def test_sampling_uses_the_connection_aware_request(monkeypatch):
    from je_auto_control.utils.mcp_server.server import MCPServer
    server = MCPServer()
    server._writer = lambda _line: None
    server._client_capabilities = {"sampling": {}}
    sent = []
    monkeypatch.setattr(server, "_send_outbound_request",
                        lambda method, params, timeout: sent.append(method) or {"ok": 1})
    assert server.request_sampling([{"role": "user", "content": "hi"}]) == {"ok": 1}
    assert sent == ["sampling/createMessage"]


class _Ctx:
    def __init__(self):
        self.totals = []

    def check_cancelled(self):
        pass

    def progress(self, value, total=None, message=None):
        self.totals.append((value, total))


def _fake_locator(monkeypatch, found):
    from je_auto_control.utils.exception.exceptions import ImageNotFoundException
    from je_auto_control.wrapper import auto_control_image
    calls = []

    def locate(_path, detect_threshold=1.0):
        calls.append(True)
        if not found:
            raise ImageNotFoundException("not here")
        return 5, 6

    monkeypatch.setattr(auto_control_image, "locate_image_center", locate)
    return calls


def test_a_zero_timeout_still_looks_once(monkeypatch):
    calls = _fake_locator(monkeypatch, found=True)
    assert _handlers_screen.wait_for_image("x.png", timeout=0) == [5, 6]
    assert calls == [True]
    from je_auto_control.wrapper import auto_control_screen
    monkeypatch.setattr(auto_control_screen, "get_pixel", lambda _x, _y: (1, 2, 3))
    assert _handlers_screen.wait_for_pixel(0, 0, [1, 2, 3], timeout=0) == [1, 2, 3]


def test_an_infinite_poll_is_clamped_and_the_wait_ends(monkeypatch):
    _fake_locator(monkeypatch, found=False)
    with pytest.raises(TimeoutError):
        _handlers_screen.wait_for_image("x.png", timeout=0.1, poll=float("inf"))


def test_an_infinite_timeout_reports_valid_progress(monkeypatch):
    _fake_locator(monkeypatch, found=True)
    ctx = _Ctx()
    _handlers_screen.wait_for_image("x.png", timeout=float("inf"), ctx=ctx)
    json.dumps(ctx.totals, allow_nan=False)   # NaN / Infinity are not JSON
    assert ctx.totals[0][1] is None


@pytest.mark.parametrize("call", [
    lambda: to_physical(float("inf"), 1, 100, 100, 10, 10),
    lambda: to_model(1, float("nan"), 100, 100, 10, 10),
    lambda: audit_contrast([], [0, 0, 0]),
    lambda: audit_contrast([10 ** 400, 0, 0], [0, 0, 0]),
])
def test_schema_valid_nonsense_is_a_value_error(call):
    with pytest.raises(ValueError):
        call()


def _usb_client(send=lambda _frame: None, **kwargs):
    from je_auto_control.utils.usb.passthrough import viewer_client
    client = viewer_client.UsbPassthroughClient(send_frame=send, **kwargs)
    return client, client._bind_claim({"claim_id": 5})


def test_a_credit_between_check_and_wait_is_not_missed():
    from je_auto_control.utils.usb.passthrough.protocol import Frame, Opcode
    client, _handle = _usb_client(credit_timeout_s=1.0)
    client._credits[5] = 0
    credit = Frame(op=Opcode.CREDIT, claim_id=5, payload=json.dumps({"credits": 1}).encode())

    class _RacingEvent(threading.Event):
        def wait(self, timeout=None):
            client.feed_frame(credit)   # lands after the check, before the wait
            return super().wait(timeout)

    client._credit_events[5] = _RacingEvent()
    client._consume_credit(5)
    assert client._credits[5] == 0


def test_a_failed_send_leaves_no_pending_entry():
    from je_auto_control.utils.usb.passthrough.viewer_client import UsbClientError

    def refuse(_frame):
        raise OSError("link down")

    client, handle = _usb_client(send=refuse, reply_timeout_s=0.2)
    with pytest.raises(UsbClientError):
        handle.bulk_transfer(endpoint=1, direction="in", length=4)
    assert client._pending == {}


@pytest.mark.parametrize("payload", [b'{"credits": null}', b'{"credits": [1]}', b'{"credits": 1e999}'])
def test_a_malformed_credit_is_ignored(payload):
    from je_auto_control.utils.usb.passthrough.protocol import Frame, Opcode
    client, _handle = _usb_client()
    client.feed_frame(Frame(op=Opcode.CREDIT, claim_id=5, payload=payload))


def test_a_reply_without_a_claim_is_a_client_error():
    from je_auto_control.utils.usb.passthrough.viewer_client import UsbClientError
    client, _handle = _usb_client()
    with pytest.raises(UsbClientError):
        client._bind_claim({"ok": True})


def test_a_callback_trigger_assertion_propagates():
    from je_auto_control.utils.callback.callback_function_executor import callback_executor

    def failing_assertion():
        raise AutoControlAssertionException("expected 1, got 2")

    callback_executor.event_dict["audit_failing_assertion"] = failing_assertion
    try:
        with pytest.raises(AutoControlAssertionException):
            callback_executor.callback_function("audit_failing_assertion", lambda: None)
    finally:
        del callback_executor.event_dict["audit_failing_assertion"]


def test_gamepad_errors_are_in_the_family(monkeypatch):
    import sys
    from je_auto_control.utils.gamepad import _facade
    assert issubclass(_facade.GamepadUnavailable, AutoControlException)

    def no_bus():
        raise AssertionError("The virtual device could not connect to ViGEmBus.")

    monkeypatch.setitem(sys.modules, "vgamepad", types.SimpleNamespace(VX360Gamepad=no_bus))
    assert _facade.is_available() is False
    with pytest.raises(_facade.GamepadUnavailable):
        _facade.VirtualGamepad()


def test_an_empty_clipboard_payload_allocates_a_byte(monkeypatch):
    from je_auto_control.utils.clipboard import win32_clipboard_api as api
    sizes = []

    class _Kernel:
        def GlobalAlloc(self, _flags, size):   # noqa: N802  # reason: the Win32 name
            sizes.append(size)
            return 0

    monkeypatch.setattr(api, "clipboard_api", lambda: (object(), _Kernel()))
    with pytest.raises(RuntimeError):
        api.set_clipboard_format(13, b"")
    assert sizes == [1]


@pytest.mark.parametrize("level", [float("nan"), float("inf"), "abc"])
def test_a_volume_that_is_not_a_finite_number_is_an_action_error(level):
    from je_auto_control.utils.system_volume.system_volume import clamp_percent
    with pytest.raises(AutoControlActionException):
        clamp_percent(level)


def test_a_text_timeout_is_an_assertion_error():
    from je_auto_control.utils.assertion.combinators import assert_eventually
    with pytest.raises(AutoControlAssertionException):
        assert_eventually({"type": "anything"}, timeout="5")
