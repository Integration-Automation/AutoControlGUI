"""Tests for USB passthrough Phase 2a (round 37)."""
import json

import pytest

from je_auto_control.utils.usb.passthrough import (
    FakeUsbBackend, Frame, MAX_PAYLOAD_BYTES, Opcode, ProtocolError,
    UsbPassthroughSession, decode_frame, enable_usb_passthrough,
    encode_frame, is_usb_passthrough_enabled,
)
from je_auto_control.utils.usb.passthrough.backend import (
    BackendDevice, FakeUsbHandle, UsbHandle,
)


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


def test_frame_round_trip():
    original = Frame(
        op=Opcode.OPEN, flags=0, claim_id=42, payload=b"hello",
    )
    encoded = encode_frame(original)
    decoded = decode_frame(encoded)
    assert decoded == original


def test_decode_rejects_unknown_opcode():
    raw = bytes([0x7E, 0x00, 0x00, 0x00])
    with pytest.raises(ProtocolError) as exc_info:
        decode_frame(raw)
    assert "0x7e" in str(exc_info.value)


def test_decode_rejects_short_buffer():
    with pytest.raises(ProtocolError):
        decode_frame(b"\x01")


def test_decode_rejects_oversize_payload():
    payload = b"\x00" * (MAX_PAYLOAD_BYTES + 1)
    raw = bytes([Opcode.BULK, 0, 0, 0]) + payload
    with pytest.raises(ProtocolError):
        decode_frame(raw)


def test_frame_constructor_validates():
    with pytest.raises(ProtocolError):
        Frame(op=Opcode.OPEN, claim_id=99999)
    with pytest.raises(ProtocolError):
        Frame(op=Opcode.OPEN, payload=b"\x00" * (MAX_PAYLOAD_BYTES + 1))
    with pytest.raises(ProtocolError):
        Frame(op="not-an-opcode")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Session — happy path
# ---------------------------------------------------------------------------


_SAMPLE_DEVICE = BackendDevice(
    vendor_id="1050", product_id="0407", serial="ABC123",
)


def _make_open_frame(vid="1050", pid="0407", serial="ABC123") -> Frame:
    body = {"vendor_id": vid, "product_id": pid}
    if serial is not None:
        body["serial"] = serial
    return Frame(op=Opcode.OPEN,
                 payload=json.dumps(body).encode("utf-8"))


def test_open_success_emits_opened_with_claim_id():
    backend = FakeUsbBackend(devices=[_SAMPLE_DEVICE])
    session = UsbPassthroughSession(backend)
    replies = session.handle_frame(_make_open_frame())
    assert len(replies) == 1
    reply = replies[0]
    assert reply.op == Opcode.OPENED
    body = json.loads(reply.payload.decode("utf-8"))
    assert body["ok"] is True
    assert body["claim_id"] >= 1
    assert reply.claim_id == body["claim_id"]
    assert session.active_claim_count == 1


def test_open_then_close_round_trip():
    backend = FakeUsbBackend(devices=[_SAMPLE_DEVICE])
    session = UsbPassthroughSession(backend)
    open_reply = session.handle_frame(_make_open_frame())[0]
    claim_id = open_reply.claim_id
    close_reply = session.handle_frame(
        Frame(op=Opcode.CLOSE, claim_id=claim_id),
    )
    assert len(close_reply) == 1
    assert close_reply[0].op == Opcode.CLOSED
    assert close_reply[0].claim_id == claim_id
    assert session.active_claim_count == 0


def test_close_unknown_claim_returns_error():
    session = UsbPassthroughSession(FakeUsbBackend(devices=[]))
    replies = session.handle_frame(
        Frame(op=Opcode.CLOSE, claim_id=999),
    )
    assert replies[0].op == Opcode.ERROR
    body = json.loads(replies[0].payload.decode("utf-8"))
    assert "999" in body["error"]


# ---------------------------------------------------------------------------
# Session — failure paths
# ---------------------------------------------------------------------------


def test_open_with_unknown_device_returns_failure():
    session = UsbPassthroughSession(FakeUsbBackend(devices=[]))
    replies = session.handle_frame(_make_open_frame())
    body = json.loads(replies[0].payload.decode("utf-8"))
    assert replies[0].op == Opcode.OPENED
    assert body["ok"] is False
    assert "no fake device" in body["error"]


def test_open_with_bad_payload_returns_failure():
    session = UsbPassthroughSession(FakeUsbBackend(devices=[_SAMPLE_DEVICE]))
    replies = session.handle_frame(
        Frame(op=Opcode.OPEN, payload=b"not json"),
    )
    body = json.loads(replies[0].payload.decode("utf-8"))
    assert replies[0].op == Opcode.OPENED
    assert body["ok"] is False
    assert "bad OPEN payload" in body["error"]


def test_open_with_serial_mismatch_returns_failure():
    backend = FakeUsbBackend(devices=[_SAMPLE_DEVICE])
    session = UsbPassthroughSession(backend)
    replies = session.handle_frame(_make_open_frame(serial="WRONG"))
    body = json.loads(replies[0].payload.decode("utf-8"))
    assert body["ok"] is False


def test_max_concurrent_claims_enforced():
    devices = [
        BackendDevice(vendor_id="00ab", product_id=f"{i:04x}")
        for i in range(5)
    ]
    backend = FakeUsbBackend(devices=devices)
    session = UsbPassthroughSession(backend, max_claims=2)
    success = []
    for dev in devices[:3]:
        reply = session.handle_frame(
            _make_open_frame(vid=dev.vendor_id, pid=dev.product_id, serial=None),
        )[0]
        body = json.loads(reply.payload.decode("utf-8"))
        success.append(body["ok"])
    assert success == [True, True, False]
    assert session.active_claim_count == 2


# ---------------------------------------------------------------------------
# Phase 2a.1 — transfers
# ---------------------------------------------------------------------------


def _open_and_get_claim(session: UsbPassthroughSession,
                        backend: FakeUsbBackend) -> int:
    """Helper: run an OPEN cycle and return the granted claim_id."""
    reply = session.handle_frame(_make_open_frame())[0]
    body = json.loads(reply.payload.decode("utf-8"))
    assert body["ok"], body
    return body["claim_id"]


def _transfer_frame(op: Opcode, claim_id: int, body: dict) -> Frame:
    import json as _json
    return Frame(
        op=op, claim_id=claim_id,
        payload=_json.dumps(body).encode("utf-8"),
    )


def test_control_transfer_round_trip():
    backend = FakeUsbBackend(devices=[_SAMPLE_DEVICE])
    session = UsbPassthroughSession(backend)
    claim_id = _open_and_get_claim(session, backend)
    # Hook the just-opened handle to return canned bytes.
    handle = next(iter(backend._open_handles.values()))
    handle.transfer_hook = lambda kind, kwargs: b"\x01\x02\x03"

    request = {
        "bm_request_type": 0xC0, "b_request": 6,
        "w_value": 0x0100, "w_index": 0,
        "length": 18, "timeout_ms": 500,
    }
    replies = session.handle_frame(
        _transfer_frame(Opcode.CTRL, claim_id, request),
    )
    assert len(replies) == 2
    ctrl_reply, credit_reply = replies
    assert ctrl_reply.op == Opcode.CTRL
    body = json.loads(ctrl_reply.payload.decode("utf-8"))
    assert body["ok"] is True
    import base64 as _b64
    assert _b64.b64decode(body["data"]) == b"\x01\x02\x03"
    assert credit_reply.op == Opcode.CREDIT
    credit_body = json.loads(credit_reply.payload.decode("utf-8"))
    assert credit_body["credits"] == 1


def test_bulk_in_round_trip():
    backend = FakeUsbBackend(devices=[_SAMPLE_DEVICE])
    session = UsbPassthroughSession(backend)
    claim_id = _open_and_get_claim(session, backend)
    handle = next(iter(backend._open_handles.values()))
    handle.transfer_hook = lambda kind, kwargs: b"hello"

    replies = session.handle_frame(_transfer_frame(Opcode.BULK, claim_id, {
        "endpoint": 0x81, "direction": "in", "length": 64,
    }))
    body = json.loads(replies[0].payload.decode("utf-8"))
    import base64 as _b64
    assert body["ok"] is True
    assert _b64.b64decode(body["data"]) == b"hello"


def test_bulk_out_round_trip():
    backend = FakeUsbBackend(devices=[_SAMPLE_DEVICE])
    session = UsbPassthroughSession(backend)
    claim_id = _open_and_get_claim(session, backend)
    handle = next(iter(backend._open_handles.values()))

    import base64 as _b64
    payload_data = _b64.b64encode(b"hello").decode("ascii")
    replies = session.handle_frame(_transfer_frame(Opcode.BULK, claim_id, {
        "endpoint": 0x01, "direction": "out", "data": payload_data,
    }))
    body = json.loads(replies[0].payload.decode("utf-8"))
    assert body["ok"] is True
    # Verify the backend saw the actual bytes (round-trip through b64 + JSON).
    assert handle.calls[0]["data"] == b"hello"
    assert handle.calls[0]["direction"] == "out"


def test_interrupt_transfer_round_trip():
    backend = FakeUsbBackend(devices=[_SAMPLE_DEVICE])
    session = UsbPassthroughSession(backend)
    claim_id = _open_and_get_claim(session, backend)
    handle = next(iter(backend._open_handles.values()))
    handle.transfer_hook = lambda kind, kwargs: b"\xff"

    replies = session.handle_frame(_transfer_frame(Opcode.INT, claim_id, {
        "endpoint": 0x82, "direction": "in", "length": 8,
    }))
    body = json.loads(replies[0].payload.decode("utf-8"))
    import base64 as _b64
    assert body["ok"] is True
    assert _b64.b64decode(body["data"]) == b"\xff"


def test_backend_error_translates_to_ok_false():
    backend = FakeUsbBackend(devices=[_SAMPLE_DEVICE])
    session = UsbPassthroughSession(backend)
    claim_id = _open_and_get_claim(session, backend)
    handle = next(iter(backend._open_handles.values()))

    def boom(_kind, _kwargs):
        raise RuntimeError("transfer stalled")
    handle.transfer_hook = boom

    replies = session.handle_frame(_transfer_frame(Opcode.BULK, claim_id, {
        "endpoint": 0x81, "direction": "in", "length": 64,
    }))
    assert replies[0].op == Opcode.BULK
    body = json.loads(replies[0].payload.decode("utf-8"))
    assert body["ok"] is False
    assert "transfer stalled" in body["error"]
    # Credit is still emitted so the peer doesn't deadlock on a bad transfer.
    assert replies[1].op == Opcode.CREDIT


def test_transfer_on_unknown_claim_returns_error():
    session = UsbPassthroughSession(FakeUsbBackend(devices=[]))
    replies = session.handle_frame(_transfer_frame(Opcode.BULK, 999, {
        "endpoint": 1, "direction": "in", "length": 8,
    }))
    assert replies[0].op == Opcode.ERROR
    body = json.loads(replies[0].payload.decode("utf-8"))
    assert "999" in body["error"]


def test_bad_transfer_payload_returns_error():
    backend = FakeUsbBackend(devices=[_SAMPLE_DEVICE])
    session = UsbPassthroughSession(backend)
    claim_id = _open_and_get_claim(session, backend)
    replies = session.handle_frame(
        Frame(op=Opcode.BULK, claim_id=claim_id, payload=b"not json"),
    )
    assert replies[0].op == Opcode.ERROR


# ---------------------------------------------------------------------------
# Phase 2a.1 — credit tracking
# ---------------------------------------------------------------------------


def test_initial_credits_set_on_open():
    backend = FakeUsbBackend(devices=[_SAMPLE_DEVICE])
    session = UsbPassthroughSession(backend, initial_credits=5)
    claim_id = _open_and_get_claim(session, backend)
    credits = session.credits_for(claim_id)
    assert credits == {"inbound": 5, "outbound": 5}


def test_credit_exhaustion_returns_error():
    backend = FakeUsbBackend(devices=[_SAMPLE_DEVICE])
    # Tiny budget so we can hit the wall quickly.
    session = UsbPassthroughSession(backend, initial_credits=2)
    claim_id = _open_and_get_claim(session, backend)
    handle = next(iter(backend._open_handles.values()))
    handle.transfer_hook = lambda kind, kwargs: b""

    transfer = _transfer_frame(Opcode.BULK, claim_id, {
        "endpoint": 1, "direction": "in", "length": 4,
    })
    # 2 successful transfers, then exhausted.
    for _ in range(2):
        replies = session.handle_frame(transfer)
        assert replies[0].op == Opcode.BULK
    exhausted = session.handle_frame(transfer)
    assert exhausted[0].op == Opcode.ERROR
    body = json.loads(exhausted[0].payload.decode("utf-8"))
    assert "credit exhausted" in body["error"]


def test_credit_message_replenishes_outbound():
    backend = FakeUsbBackend(devices=[_SAMPLE_DEVICE])
    session = UsbPassthroughSession(backend, initial_credits=3)
    claim_id = _open_and_get_claim(session, backend)

    credit_payload = json.dumps({"credits": 7}).encode("utf-8")
    replies = session.handle_frame(
        Frame(op=Opcode.CREDIT, claim_id=claim_id, payload=credit_payload),
    )
    # CREDIT messages produce no reply.
    assert replies == []
    credits = session.credits_for(claim_id)
    assert credits["outbound"] == 10  # 3 initial + 7 grant


def test_credit_message_with_bad_payload_is_ignored():
    backend = FakeUsbBackend(devices=[_SAMPLE_DEVICE])
    session = UsbPassthroughSession(backend, initial_credits=4)
    claim_id = _open_and_get_claim(session, backend)
    bad = Frame(op=Opcode.CREDIT, claim_id=claim_id, payload=b"garbage")
    assert session.handle_frame(bad) == []
    # Outbound credits unchanged.
    assert session.credits_for(claim_id)["outbound"] == 4


def test_credit_message_for_unknown_claim_is_silent():
    session = UsbPassthroughSession(FakeUsbBackend(devices=[]))
    payload = json.dumps({"credits": 5}).encode("utf-8")
    assert session.handle_frame(
        Frame(op=Opcode.CREDIT, claim_id=999, payload=payload),
    ) == []


# ---------------------------------------------------------------------------
# Session — cleanup
# ---------------------------------------------------------------------------


def test_close_all_releases_every_outstanding_claim():
    devices = [
        BackendDevice(vendor_id="00cd", product_id=f"{i:04x}")
        for i in range(3)
    ]
    backend = FakeUsbBackend(devices=devices)
    session = UsbPassthroughSession(backend, max_claims=10)
    for dev in devices:
        session.handle_frame(_make_open_frame(
            vid=dev.vendor_id, pid=dev.product_id, serial=None,
        ))
    assert session.active_claim_count == 3
    assert backend.open_handle_count == 3
    session.close_all()
    assert session.active_claim_count == 0
    assert backend.open_handle_count == 0


def test_backend_handle_close_is_idempotent():
    handle = FakeUsbHandle(FakeUsbBackend(), 1, _SAMPLE_DEVICE)
    handle.close()
    handle.close()  # second call must not raise


# ---------------------------------------------------------------------------
# Backend ABC
# ---------------------------------------------------------------------------


def test_fake_handle_default_transfer_returns_zeroed_buffer_for_in():
    """Default behaviour (no transfer_hook) returns ``length`` zero bytes."""
    handle = FakeUsbHandle(FakeUsbBackend(), 1, _SAMPLE_DEVICE)
    out = handle.bulk_transfer(endpoint=1, direction="in", length=4)
    assert out == b"\x00\x00\x00\x00"


def test_fake_handle_default_transfer_for_out_returns_empty():
    handle = FakeUsbHandle(FakeUsbBackend(), 1, _SAMPLE_DEVICE)
    out = handle.bulk_transfer(endpoint=1, direction="out", data=b"hi")
    assert out == b""
    assert handle.calls[0]["data"] == b"hi"


def test_fake_handle_transfer_after_close_raises():
    handle = FakeUsbHandle(FakeUsbBackend(), 1, _SAMPLE_DEVICE)
    handle.close()
    with pytest.raises(RuntimeError):
        handle.bulk_transfer(endpoint=1, direction="in", length=4)


def test_usb_handle_is_an_abc():
    """``UsbHandle`` exposes ``close`` as an abstract method."""
    assert "close" in UsbHandle.__abstractmethods__


# ---------------------------------------------------------------------------
# Feature flag — default off
# ---------------------------------------------------------------------------


def test_feature_flag_defaults_off(monkeypatch):
    """Override env + state to a clean baseline, then check default."""
    monkeypatch.delenv("JE_AUTOCONTROL_USB_PASSTHROUGH", raising=False)
    enable_usb_passthrough(False)
    assert is_usb_passthrough_enabled() is False


def test_feature_flag_explicit_enable(monkeypatch):
    monkeypatch.delenv("JE_AUTOCONTROL_USB_PASSTHROUGH", raising=False)
    enable_usb_passthrough(True)
    try:
        assert is_usb_passthrough_enabled() is True
    finally:
        enable_usb_passthrough(False)


def test_feature_flag_env_var(monkeypatch):
    """Env var only takes effect when there's no explicit override."""
    enable_usb_passthrough(False)  # establish baseline
    # Reset the explicit override so env can win.
    import je_auto_control.utils.usb.passthrough.flags as flags_module
    monkeypatch.setattr(flags_module, "_explicit_state", None)
    monkeypatch.setenv("JE_AUTOCONTROL_USB_PASSTHROUGH", "1")
    assert is_usb_passthrough_enabled() is True
