"""Tests for open questions 2 (fragmentation) and 3 (LIST over channel)."""
import json

import pytest

from je_auto_control.utils.usb.passthrough import (
    AclRule, FLAG_EOF, Frame, MAX_PAYLOAD_BYTES, Opcode, UsbAcl,
    UsbPassthroughClient, UsbPassthroughSession, fragment_payload,
)
from je_auto_control.utils.usb.passthrough.backend import (
    BackendDevice, FakeUsbBackend,
)


_SAMPLE = BackendDevice(vendor_id="1050", product_id="0407", serial="ABC123")
_OTHER = BackendDevice(vendor_id="2222", product_id="3333", serial=None)


# ---------------------------------------------------------------------------
# protocol.fragment_payload
# ---------------------------------------------------------------------------


def test_fragment_empty_payload_is_single_eof_frame():
    frames = fragment_payload(Opcode.LIST, 0, b"")
    assert len(frames) == 1
    assert frames[0].flags & FLAG_EOF
    assert frames[0].payload == b""


def test_fragment_small_payload_single_eof_frame():
    frames = fragment_payload(Opcode.CTRL, 7, b"hello")
    assert len(frames) == 1
    assert frames[0].flags & FLAG_EOF
    assert frames[0].claim_id == 7


def test_fragment_oversize_payload_splits_with_eof_only_on_last():
    payload = b"\xab" * (MAX_PAYLOAD_BYTES * 2 + 100)
    frames = fragment_payload(Opcode.BULK, 3, payload)
    assert len(frames) == 3
    assert not (frames[0].flags & FLAG_EOF)
    assert not (frames[1].flags & FLAG_EOF)
    assert frames[2].flags & FLAG_EOF
    # Every chunk respects the per-frame cap, and they reassemble cleanly.
    assert all(len(f.payload) <= MAX_PAYLOAD_BYTES for f in frames)
    assert b"".join(f.payload for f in frames) == payload


# ---------------------------------------------------------------------------
# Session — LIST over channel (open question 3)
# ---------------------------------------------------------------------------


def _list_devices(replies):
    payload = b"".join(f.payload for f in replies)
    return json.loads(payload.decode("utf-8"))["devices"]


def test_list_without_acl_returns_all_devices():
    session = UsbPassthroughSession(FakeUsbBackend(devices=[_SAMPLE, _OTHER]))
    replies = session.handle_frame(Frame(op=Opcode.LIST))
    assert all(r.op == Opcode.LIST for r in replies)
    devices = _list_devices(replies)
    vids = {d["vendor_id"] for d in devices}
    assert vids == {"1050", "2222"}


def test_list_filters_acl_denied_devices(tmp_path):
    acl = UsbAcl(path=tmp_path / "acl.json")  # default deny
    acl.add_rule(AclRule(vendor_id="1050", product_id="0407", allow=True))
    session = UsbPassthroughSession(
        FakeUsbBackend(devices=[_SAMPLE, _OTHER]), acl=acl,
    )
    devices = _list_devices(session.handle_frame(Frame(op=Opcode.LIST)))
    # Only the allowed device is visible; the denied one is hidden.
    assert [d["vendor_id"] for d in devices] == ["1050"]


def test_list_includes_prompt_devices(tmp_path):
    acl = UsbAcl(path=tmp_path / "acl.json")
    acl.add_rule(AclRule(vendor_id="2222", product_id="3333",
                         allow=True, prompt_on_open=True))
    session = UsbPassthroughSession(
        FakeUsbBackend(devices=[_SAMPLE, _OTHER]), acl=acl,
    )
    devices = _list_devices(session.handle_frame(Frame(op=Opcode.LIST)))
    # prompt is not deny → the device stays visible.
    assert [d["vendor_id"] for d in devices] == ["2222"]


# ---------------------------------------------------------------------------
# Session ↔ client round trips via a synchronous router
# ---------------------------------------------------------------------------


class _SyncLoop:
    """Routes client frames straight through the host and back.

    The host replies synchronously, so the client's pending event is set
    before its ``wait`` runs — no pump thread needed.
    """

    def __init__(self, host: UsbPassthroughSession) -> None:
        self._host = host
        self.client = UsbPassthroughClient(send_frame=self._send)

    def _send(self, frame: Frame) -> None:
        for reply in self._host.handle_frame(frame):
            self.client.feed_frame(reply)


def test_client_list_devices_round_trip(tmp_path):
    acl = UsbAcl(path=tmp_path / "acl.json")
    acl.add_rule(AclRule(vendor_id="1050", product_id="0407", allow=True))
    host = UsbPassthroughSession(
        FakeUsbBackend(devices=[_SAMPLE, _OTHER]), acl=acl,
    )
    loop = _SyncLoop(host)
    try:
        devices = loop.client.list_devices()
        assert [d["vendor_id"] for d in devices] == ["1050"]
        assert devices[0]["serial"] == "ABC123"
    finally:
        loop.client.shutdown()


def test_client_resume_after_reconnect_keeps_claim():
    """A new client RESUMEs a claim the host session still holds."""
    host = UsbPassthroughSession(FakeUsbBackend(devices=[_SAMPLE]))
    loop1 = _SyncLoop(host)
    handle = loop1.client.open(vendor_id="1050", product_id="0407")
    token = handle.resume_token
    claim_id = handle.claim_id
    assert token
    # Simulate a transport drop: tear down the viewer client only; the
    # host session keeps the claim alive (no close_all).
    loop1.client.shutdown()
    assert host.active_claim_count == 1

    # Reconnect with a brand-new client over the same host session.
    loop2 = _SyncLoop(host)
    try:
        resumed = loop2.client.resume(token)
        assert resumed.claim_id == claim_id
        backend_handle = next(
            iter(host._backend._open_handles.values())  # type: ignore[attr-defined]
        )
        backend_handle.transfer_hook = lambda kind, kwargs: b"\x01"
        assert resumed.control_transfer(
            bm_request_type=0xC0, b_request=6, length=1,
        ) == b"\x01"
    finally:
        loop2.client.shutdown()


def test_client_resume_unknown_token_raises():
    host = UsbPassthroughSession(FakeUsbBackend(devices=[_SAMPLE]))
    loop = _SyncLoop(host)
    try:
        with pytest.raises(Exception):
            loop.client.resume("not-a-real-token")
    finally:
        loop.client.shutdown()


def test_client_reassembles_oversize_bulk_in():
    host = UsbPassthroughSession(FakeUsbBackend(devices=[_SAMPLE]))
    loop = _SyncLoop(host)
    try:
        handle = loop.client.open(vendor_id="1050", product_id="0407")
        backend_handle = next(
            iter(host._backend._open_handles.values())  # type: ignore[attr-defined]
        )
        big = bytes(range(256)) * 200  # 51200 bytes → multiple frames
        backend_handle.transfer_hook = lambda kind, kwargs: big
        result = handle.bulk_transfer(
            endpoint=0x81, direction="in", length=len(big),
        )
        assert result == big
    finally:
        loop.client.shutdown()
