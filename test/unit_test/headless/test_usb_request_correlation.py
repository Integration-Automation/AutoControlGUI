"""Late replies cannot satisfy a newer USB operation on the same channel."""
import base64
import json

import pytest

from je_auto_control.utils.usb.passthrough import (
    Frame, Opcode, UsbClientClosed, UsbClientError, UsbClientTimeout,
    UsbPassthroughClient, UsbPassthroughSession,
)
from je_auto_control.utils.usb.passthrough.backend import BackendDevice, FakeUsbBackend
from je_auto_control.utils.usb.passthrough.protocol import FLAG_EOF, fragment_payload


def _reply(request, op, body, *, claim_id=1, correlated=True):
    if correlated:
        body = dict(body, request_id=json.loads(request.payload).get("request_id", "missing"))
    return Frame(op=op, flags=FLAG_EOF, claim_id=claim_id, payload=json.dumps(body).encode())


def test_late_open_does_not_complete_next_open():
    sent = []
    pending_after_late = []

    def send(frame):
        sent.append(frame)
        if len(sent) == 1:
            client.feed_frame(_reply(frame, Opcode.OPENED, {"ok": True, "claim_id": 1}))
        elif len(sent) == 3:
            client.feed_frame(_reply(sent[1], Opcode.OPENED, {"ok": True, "claim_id": 2}))
            pending_after_late.append(client.pending_count())
            client.feed_frame(_reply(frame, Opcode.OPENED, {"ok": True, "claim_id": 3}))

    client = UsbPassthroughClient(send_frame=send, reply_timeout_s=0.01)
    client.open(vendor_id="1234", product_id="5678")
    with pytest.raises(UsbClientTimeout):
        client.open(vendor_id="1234", product_id="5678")
    latest = client.open(vendor_id="1234", product_id="5678")
    assert pending_after_late == [1]
    assert latest.claim_id == 3


def test_late_transfer_does_not_complete_next_transfer():
    requests = []
    pending_after_late = []

    def send(frame):
        requests.append(frame)
        if frame.op == Opcode.OPEN:
            client.feed_frame(_reply(frame, Opcode.OPENED, {"ok": True, "claim_id": 1}))
        elif len(requests) == 3:
            old_body = {"ok": True, "data": base64.b64encode(b"old").decode(),
                        "request_id": json.loads(requests[1].payload).get("request_id", "missing")}
            for part in fragment_payload(Opcode.BULK, 1, json.dumps(old_body).encode()):
                client.feed_frame(part)
            pending_after_late.append(client.pending_count())
            client.feed_frame(_reply(frame, Opcode.BULK, {"ok": True, "data": base64.b64encode(b"new").decode()}))

    client = UsbPassthroughClient(send_frame=send, reply_timeout_s=0.01)
    handle = client.open(vendor_id="1234", product_id="5678")
    with pytest.raises(UsbClientTimeout):
        handle.bulk_transfer(endpoint=0x81, direction="in", length=3)
    assert handle.bulk_transfer(endpoint=0x81, direction="in", length=3) == b"new"
    assert pending_after_late == [1]


def test_legacy_timeout_requires_reconnect():
    requests = []

    def send(frame):
        requests.append(frame)
        if frame.op == Opcode.OPEN:
            client.feed_frame(_reply(frame, Opcode.OPENED, {"ok": True, "claim_id": 1}, correlated=False))

    client = UsbPassthroughClient(send_frame=send, reply_timeout_s=0.01)
    handle = client.open(vendor_id="1234", product_id="5678")
    with pytest.raises(UsbClientTimeout):
        handle.bulk_transfer(endpoint=0x81, direction="in", length=3)
    with pytest.raises(UsbClientClosed):
        handle.bulk_transfer(endpoint=0x81, direction="in", length=3)
    assert len(requests) == 2
    assert handle.closed is True


def test_host_echoes_identity_in_open_failure_and_error():
    host = UsbPassthroughSession(FakeUsbBackend(devices=[]))
    for op, body in [(Opcode.OPEN, {"vendor_id": "1234", "product_id": "5678"}),
                     (Opcode.BULK, {"endpoint": 0x81, "direction": "in", "length": 3})]:
        request = Frame(op=op, claim_id=2, payload=json.dumps(dict(body, request_id="identity")).encode())
        replies = host.handle_frame(request)
        assert json.loads(replies[0].payload)["request_id"] == "identity"


def test_host_echoes_identity_across_fragmented_transfer_and_credit():
    device = BackendDevice(vendor_id="1234", product_id="5678")
    backend = FakeUsbBackend(devices=[device])
    host = UsbPassthroughSession(backend)
    opened = host.handle_frame(Frame(op=Opcode.OPEN, payload=json.dumps({
        "vendor_id": "1234", "product_id": "5678", "request_id": "open",
    }).encode()))
    claim = json.loads(opened[0].payload)["claim_id"]
    frames = host.handle_frame(Frame(op=Opcode.BULK, claim_id=claim, payload=json.dumps({
        "endpoint": 0x81, "direction": "in", "length": 40000, "request_id": "transfer",
    }).encode()))
    payload = b"".join(f.payload for f in frames if f.op == Opcode.BULK)
    assert json.loads(payload)["request_id"] == "transfer"
    assert len([f for f in frames if f.op == Opcode.BULK]) > 1
    assert json.loads(next(f.payload for f in frames if f.op == Opcode.CREDIT))["request_id"] == "transfer"


def test_credit_identity_rejects_another_claim_and_duplicate_grants():
    requests = []

    def send(frame):
        requests.append(frame)
        if frame.op == Opcode.OPEN:
            client.feed_frame(_reply(frame, Opcode.OPENED, {"ok": True, "claim_id": 1}))

    client = UsbPassthroughClient(send_frame=send, reply_timeout_s=0.01)
    handle = client.open(vendor_id="1234", product_id="5678")
    with pytest.raises(UsbClientTimeout):
        handle.bulk_transfer(endpoint=0x81, direction="in", length=3)
    transfer = requests[-1]
    wrong = _reply(transfer, Opcode.CREDIT, {"credits": 3}, claim_id=2)
    client.feed_frame(wrong)
    assert client.credits_remaining(2) == 0
    correct = _reply(transfer, Opcode.CREDIT, {"credits": 3})
    client.feed_frame(correct)
    client.feed_frame(correct)
    assert client.credits_remaining(1) == 18


def test_late_open_releases_the_orphaned_host_claim():
    backend = FakeUsbBackend(devices=[BackendDevice(vendor_id="1234", product_id="5678")])
    host = UsbPassthroughSession(backend)
    opens = []

    def send(frame):
        replies = host.handle_frame(frame)
        if frame.op == Opcode.OPEN:
            opens.append(replies)
            if len(opens) == 2:
                return
            if len(opens) == 3:
                for late in opens[1]:
                    client.feed_frame(late)
        for reply in replies:
            client.feed_frame(reply)

    client = UsbPassthroughClient(send_frame=send, reply_timeout_s=0.01)
    client.open(vendor_id="1234", product_id="5678")
    with pytest.raises(UsbClientTimeout):
        client.open(vendor_id="1234", product_id="5678")
    client.open(vendor_id="1234", product_id="5678")
    assert backend.open_handle_count == 2


def test_correlated_close_error_is_reported():
    def send(frame):
        if frame.op == Opcode.OPEN:
            client.feed_frame(_reply(frame, Opcode.OPENED, {"ok": True, "claim_id": 1}))
        else:
            client.feed_frame(_reply(frame, Opcode.ERROR, {"error": "close failed"}))

    client = UsbPassthroughClient(send_frame=send)
    handle = client.open(vendor_id="1234", product_id="5678")
    with pytest.raises(UsbClientError, match="close failed"):
        handle.close()


def test_late_error_does_not_fail_a_new_transfer():
    requests = []

    def send(frame):
        requests.append(frame)
        if frame.op == Opcode.OPEN:
            client.feed_frame(_reply(frame, Opcode.OPENED, {"ok": True, "claim_id": 1}))
        elif len(requests) == 3:
            client.feed_frame(_reply(requests[1], Opcode.ERROR, {"error": "old failure"}))
            client.feed_frame(_reply(frame, Opcode.BULK, {"ok": True, "data": "bmV3"}))

    client = UsbPassthroughClient(send_frame=send, reply_timeout_s=0.01)
    handle = client.open(vendor_id="1234", product_id="5678")
    with pytest.raises(UsbClientTimeout):
        handle.bulk_transfer(endpoint=0x81, direction="in", length=3)
    assert handle.bulk_transfer(endpoint=0x81, direction="in", length=3) == b"new"
