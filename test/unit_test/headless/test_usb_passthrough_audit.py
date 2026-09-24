"""Regression tests for the USB passthrough defects found in the 2026-09-23 audit.

The surface is security-sensitive — a remote viewer asks this host to claim a
local USB device — and three of the six let a viewer past the ACL.
"""
import json

import pytest

from je_auto_control.utils.usb.passthrough import (
    FakeUsbBackend, Frame, Opcode, UsbPassthroughSession,
)
from je_auto_control.utils.usb.passthrough.acl import (
    AclRule, UsbAcl, normalize_usb_id,
)
from je_auto_control.utils.usb.passthrough.backend import BackendDevice

_DEVICE = BackendDevice(vendor_id="1050", product_id="0407", serial="ABC123",
                        bus_location="1-1")


def _open(session, vid="1050", pid="0407", serial="ABC123"):
    body = {"vendor_id": vid, "product_id": pid}
    if serial is not None:
        body["serial"] = serial
    reply = session.handle_frame(Frame(
        op=Opcode.OPEN, claim_id=0, payload=json.dumps(body).encode("utf-8")))[0]
    return json.loads(reply.payload.decode("utf-8"))


def _bulk(session, claim_id, **body):
    body.setdefault("endpoint", 1)
    body.setdefault("direction", "in")
    body.setdefault("length", 4)
    return session.handle_frame(Frame(
        op=Opcode.BULK, claim_id=claim_id, payload=json.dumps(body).encode("utf-8")))


def _acl(tmp_path, default="allow", rules=()):
    acl = UsbAcl(path=tmp_path / "acl.json")
    acl.set_default_policy(default, persist=False)
    for rule in rules:
        acl.add_rule(rule, persist=False)
    return acl


# --- ids ----------------------------------------------------------------------

@pytest.mark.parametrize("spelling", ["1050", "0x1050", "0X1050", " 1050 "])
def test_every_accepted_spelling_normalises_to_four_hex_digits(spelling):
    assert normalize_usb_id(spelling) == "1050"


@pytest.mark.parametrize("spelling", ["01050", "10_50", "105", "0x10500", "", "zzzz"])
def test_anything_else_is_rejected(spelling):
    with pytest.raises(ValueError):
        normalize_usb_id(spelling)


@pytest.mark.parametrize("spelling", ["0x1050", "01050", "10_50"])
def test_an_alternative_id_spelling_does_not_skip_a_deny_rule(tmp_path, spelling):
    acl = _acl(tmp_path, rules=[AclRule(vendor_id="1050", product_id="0407", allow=False)])
    backend = FakeUsbBackend(devices=[_DEVICE])
    body = _open(UsbPassthroughSession(backend, acl=acl), vid=spelling)
    assert body["ok"] is False
    assert backend.open_handle_count == 0


# --- serials ------------------------------------------------------------------

def test_omitting_the_serial_does_not_skip_a_serial_rule(tmp_path):
    acl = _acl(tmp_path, rules=[AclRule(vendor_id="1050", product_id="0407",
                                        serial="ABC123", allow=False)])
    backend = FakeUsbBackend(devices=[_DEVICE])
    body = _open(UsbPassthroughSession(backend, acl=acl), serial=None)
    assert body["ok"] is False
    assert backend.open_handle_count == 0


def test_a_device_without_serial_rules_opens_without_a_serial(tmp_path):
    backend = FakeUsbBackend(devices=[_DEVICE])
    body = _open(UsbPassthroughSession(backend, acl=_acl(tmp_path)), serial=None)
    assert body["ok"] is True


def test_winusb_refuses_a_serial_it_cannot_select_by():
    winusb = pytest.importorskip("je_auto_control.utils.usb.passthrough.winusb_backend")
    backend = winusb.WinusbBackend.__new__(winusb.WinusbBackend)
    with pytest.raises(RuntimeError, match="serial"):
        backend.open(vendor_id="1050", product_id="0407", serial="ABC123")


# --- credits ------------------------------------------------------------------

def test_the_claim_keeps_working_past_its_initial_allowance():
    """Each reply grants the viewer more credit; our count has to follow."""
    backend = FakeUsbBackend(devices=[_DEVICE])
    session = UsbPassthroughSession(backend, initial_credits=2)
    claim_id = _open(session)["claim_id"]
    for _ in range(20):
        assert _bulk(session, claim_id)[0].op == Opcode.BULK


def test_a_malformed_transfer_does_not_cost_a_credit():
    backend = FakeUsbBackend(devices=[_DEVICE])
    session = UsbPassthroughSession(backend, initial_credits=1)
    claim_id = _open(session)["claim_id"]
    session.handle_frame(Frame(op=Opcode.BULK, claim_id=claim_id, payload=b"{not json"))
    assert _bulk(session, claim_id)[0].op == Opcode.BULK


# --- bounds -------------------------------------------------------------------

@pytest.mark.parametrize("field, value", [
    ("length", 1024 * 1024 + 1), ("length", -1), ("timeout_ms", 60_001),
])
def test_wire_numbers_are_bounded(field, value):
    backend = FakeUsbBackend(devices=[_DEVICE])
    session = UsbPassthroughSession(backend)
    claim_id = _open(session)["claim_id"]
    handle = next(iter(backend._open_handles.values()))
    requested = []
    handle.transfer_hook = lambda kind, kwargs: requested.append(kwargs) or b""
    reply = _bulk(session, claim_id, **{field: value})[0]
    assert json.loads(reply.payload.decode("utf-8"))["ok"] is False
    assert requested == [], "the backend must not see an out-of-range request"


# --- claim ids ----------------------------------------------------------------

def test_a_wrapped_claim_id_skips_one_still_in_use():
    backend = FakeUsbBackend(devices=[_DEVICE])
    session = UsbPassthroughSession(backend)
    first = _open(session)["claim_id"]
    session._next_claim_id = first          # the counter has wrapped round
    second = _open(session)["claim_id"]
    assert second != first
    assert backend.open_handle_count == 2
    session.close_all()
    assert backend.open_handle_count == 0, "no handle may be orphaned"


# --- teardown -----------------------------------------------------------------

class _Channel:
    def __init__(self):
        self.handlers = {}

    def on(self, event):
        def register(callback):
            self.handlers[event] = callback
            return callback
        return register


def test_closing_the_channel_releases_every_claim():
    from je_auto_control.utils.usb.passthrough.webrtc_channel import UsbChannelHost
    backend = FakeUsbBackend(devices=[_DEVICE])
    session = UsbPassthroughSession(backend)
    _open(session)
    channel = _Channel()
    UsbChannelHost(channel, session=session, enabled_check=lambda: True)
    assert backend.open_handle_count == 1
    channel.handlers["close"]()
    assert backend.open_handle_count == 0
