"""The viewer waits as long as the transfer it asked for, and hears channel errors.

Two things a caller could only learn from a timeout:

* a transfer with ``timeout_ms`` longer than the client's ``reply_timeout_s``
  was abandoned while the host was still, correctly, waiting on the device;
* an ERROR the channel adapter sends before any session sees the frame
  (feature off, undecodable frame, no session, backend unavailable) carried
  no request id, so the client could not hand it to the request it answered.

Fake channels and a fake backend throughout: no aiortc, no USB device.
"""
import base64
import json
import threading
import time

import pytest

from je_auto_control.utils.usb.passthrough import (
    ClientHandle, Frame, Opcode, UsbChannelClient, UsbChannelHost,
    UsbClientClosed, UsbClientDesynchronized, UsbClientError,
    UsbClientTimeout, UsbPassthroughClient, UsbPassthroughSession,
    decode_frame, encode_frame,
)
from je_auto_control.utils.usb.passthrough import (
    _client_requests, client_errors, client_handle, viewer_client,
)
from je_auto_control.utils.usb.passthrough.backend import (
    BackendDevice, FakeUsbBackend,
)
from je_auto_control.utils.usb.passthrough.protocol import (
    FLAG_EOF, HEADER_BYTES, MAX_PAYLOAD_BYTES,
)

_SAMPLE = BackendDevice(vendor_id="1050", product_id="0407", serial="ABC123")
_WAIT_S = 5.0


# --- the wait follows the request ------------------------------------------


class _Wire:
    """Captures what the client sends; the test feeds the replies."""

    def __init__(self, reply_timeout_s: float) -> None:
        self.sent = []
        self._cond = threading.Condition()
        self.client = UsbPassthroughClient(
            send_frame=self._send, reply_timeout_s=reply_timeout_s)

    def _send(self, frame: Frame) -> None:
        with self._cond:
            self.sent.append(frame)
            self._cond.notify_all()

    def wait_sent(self, count: int) -> Frame:
        with self._cond:
            if not self._cond.wait_for(lambda: len(self.sent) >= count, _WAIT_S):
                raise AssertionError(f"client sent {len(self.sent)} frames, wanted {count}")
            return self.sent[count - 1]

    def open_claim(self, claim_id: int = 1) -> ClientHandle:
        outcome = {}
        sent_before = len(self.sent)
        self.client._reply_timeout, short = _WAIT_S, self.client._reply_timeout  # noqa: SLF001  # reason: only the transfer under test gets the short timeout
        thread = threading.Thread(
            target=lambda: outcome.update(handle=self.client.open(
                vendor_id="1050", product_id="0407")), daemon=True)
        thread.start()
        request = self.wait_sent(sent_before + 1)
        self.client._reply_timeout = short  # noqa: SLF001  # reason: see above
        self.client.feed_frame(Frame(op=Opcode.OPENED, claim_id=claim_id, payload=_echo(
            {"ok": True, "claim_id": claim_id}, request)))
        thread.join(_WAIT_S)
        return outcome["handle"]


def _echo(body: dict, request: Frame) -> bytes:
    body = dict(body)
    body["request_id"] = json.loads(request.payload)["request_id"]
    return json.dumps(body).encode("utf-8")


def test_transfer_waits_for_the_timeout_it_asked_for():
    """A reply inside ``timeout_ms`` but after ``reply_timeout_s`` is the answer."""
    wire = _Wire(reply_timeout_s=0.1)
    handle = wire.open_claim()
    outcome = {}

    def read() -> None:
        try:
            outcome["data"] = handle.bulk_transfer(
                endpoint=0x81, direction="in", length=4, timeout_ms=3000)
        except UsbClientError as error:
            outcome["error"] = error

    thread = threading.Thread(target=read, daemon=True)
    thread.start()
    request = wire.wait_sent(2)
    time.sleep(0.4)     # four times reply_timeout_s, well inside timeout_ms
    wire.client.feed_frame(Frame(
        op=Opcode.BULK, flags=FLAG_EOF, claim_id=1, payload=_echo(
            {"ok": True, "data": base64.b64encode(b"late").decode("ascii")}, request)))
    thread.join(_WAIT_S)
    assert outcome == {"data": b"late"}
    assert handle.reusable


def test_transfer_still_times_out_after_its_timeout_and_the_margin():
    wire = _Wire(reply_timeout_s=0.1)
    handle = wire.open_claim()
    started = time.monotonic()
    with pytest.raises(UsbClientTimeout, match="BULK timed out for claim 1"):
        handle.bulk_transfer(endpoint=0x81, direction="in", length=4, timeout_ms=200)
    waited = time.monotonic() - started
    assert 0.28 <= waited < _WAIT_S


def test_request_without_a_device_timeout_waits_reply_timeout_only():
    wire = _Wire(reply_timeout_s=0.1)
    started = time.monotonic()
    with pytest.raises(UsbClientTimeout, match="LIST timed out"):
        wire.client.list_devices()
    assert time.monotonic() - started < 1.0


@pytest.mark.parametrize("body, expected", [
    ({}, 0.0),
    ({"timeout_ms": 1000}, 1.0),
    ({"timeout_ms": 30_000}, 30.0),
    ({"timeout_ms": 60_000}, 60.0),
    ({"timeout_ms": 600_000}, 60.0),        # the host refuses more than 60 s
    ({"timeout_ms": 0}, 0.0),
    ({"timeout_ms": -5}, 0.0),
    ({"timeout_ms": True}, 0.0),
    ({"timeout_ms": "1000"}, 0.0),
    ({"timeout_ms": None}, 0.0),
    ({"timeout_ms": float("nan")}, 0.0),
    ({"timeout_ms": float("inf")}, 60.0),
])
def test_device_timeout_of_a_request_body(body, expected):
    assert _client_requests.device_timeout_s(body) == expected


def test_client_cap_is_the_hosts_cap():
    from je_auto_control.utils.usb.passthrough import session
    assert _client_requests.MAX_DEVICE_TIMEOUT_MS == session.MAX_TIMEOUT_MS


# --- channel-level errors reach the request --------------------------------


class _ImmediateBridge:
    @staticmethod
    def call_soon(fn, *args):
        fn(*args)


class _LinkedChannel:
    """Fake RTCDataChannel whose ``send`` delivers to its peer's handler."""

    def __init__(self):
        self._peer = None
        self.handlers = {}

    def link(self, peer):
        self._peer = peer

    def on(self, event):
        def _register(fn):
            self.handlers[event] = fn
            return fn
        return _register

    def send(self, data):
        handler = self._peer.handlers.get("message")
        if handler is not None:
            handler(data)


def _channel(**host_kwargs):
    """A host adapter and a real client joined by fake channels."""
    host_ch, client_ch = _LinkedChannel(), _LinkedChannel()
    host_ch.link(client_ch)
    client_ch.link(host_ch)
    host_kwargs.setdefault("enabled_check", lambda: True)
    UsbChannelHost(host_ch, bridge=_ImmediateBridge(), **host_kwargs)
    # Long enough that a test passing in well under it did not time out.
    client = UsbChannelClient(client_ch, bridge=_ImmediateBridge(), reply_timeout_s=_WAIT_S)
    return host_ch, client


def _refused(call) -> UsbClientError:
    """Run ``call``; it must be refused by the host, promptly, not time out."""
    started = time.monotonic()
    with pytest.raises(UsbClientError) as raised:
        call()
    assert not isinstance(raised.value, UsbClientTimeout)
    assert time.monotonic() - started < _WAIT_S / 2
    return raised.value


def _session() -> UsbPassthroughSession:
    return UsbPassthroughSession(FakeUsbBackend(devices=[_SAMPLE]))


@pytest.mark.parametrize("call", [
    lambda client: client.list_devices(),
    lambda client: client.open(vendor_id="1050", product_id="0407"),
    lambda client: client.resume("some-token"),
], ids=["list", "open", "resume"])
def test_disabled_passthrough_is_reported_to_the_caller(call):
    _host, client = _channel(session=_session(), enabled_check=lambda: False)
    try:
        assert "usb passthrough disabled" in str(_refused(lambda: call(client)))
        assert client.client.reusable       # nothing timed out, nothing to reconnect
    finally:
        client.shutdown()


def test_host_without_a_session_is_reported_to_the_caller():
    _host, client = _channel()
    try:
        error = _refused(lambda: client.open(vendor_id="1050", product_id="0407"))
        assert "no usb session on host" in str(error)
    finally:
        client.shutdown()


def test_unavailable_backend_is_reported_to_the_caller():
    def factory():
        raise OSError("libusb not found")

    _host, client = _channel(session_factory=factory)
    try:
        error = _refused(client.list_devices)
        assert "usb backend unavailable: libusb not found" in str(error)
    finally:
        client.shutdown()


def _raw_reply(host_ch: _LinkedChannel, raw) -> dict:
    """Hand ``raw`` to the host adapter; return its one reply (ERROR) body."""
    sent = []
    host_ch._peer.handlers["message"] = sent.append
    host_ch.handlers["message"](raw)
    assert len(sent) == 1
    frame = decode_frame(sent[0])
    assert frame.op == Opcode.ERROR
    return json.loads(frame.payload)


def test_bad_frame_error_echoes_the_id_it_can_read():
    host_ch, client = _channel(session=_session())
    client.shutdown()
    payload = json.dumps({"request_id": "abc-7"}).encode("utf-8")
    raw = bytes([0x7E, 0, 0, 0]) + payload      # 0x7E is not an opcode
    body = _raw_reply(host_ch, raw)
    assert body["request_id"] == "abc-7"
    assert body["error"].startswith("bad frame: unknown opcode")


@pytest.mark.parametrize("raw", [
    "not-binary",
    b"\x02",                                                    # shorter than a header
    bytes([0x7E, 0, 0, 0]) + b"not json",
    bytes([0x7E, 0, 0, 0]) + b'["request_id"]',
    bytes([0x7E, 0, 0, 0]) + json.dumps({"request_id": "x" * 65}).encode(),
    bytes([0x7E, 0, 0, 0]) + json.dumps({"request_id": 7}).encode(),
    bytes([0x02, 0, 0, 0]) + json.dumps(
        {"request_id": "abc", "pad": "p" * MAX_PAYLOAD_BYTES}).encode(),   # over the cap
], ids=["text", "short", "not-json", "not-object", "long-id", "int-id", "oversize"])
def test_bad_frame_without_a_readable_id_gets_a_plain_error(raw):
    host_ch, client = _channel(session=_session())
    client.shutdown()
    body = _raw_reply(host_ch, raw)
    assert "request_id" not in body
    assert body["error"].startswith("bad frame")


def test_channel_error_for_a_request_without_an_id_is_unchanged():
    """A viewer older than request ids gets exactly the frame it always got."""
    host_ch, client = _channel(session=_session(), enabled_check=lambda: False)
    client.shutdown()
    raw = encode_frame(Frame(op=Opcode.LIST, payload=b""))
    assert len(raw) == HEADER_BYTES
    assert _raw_reply(host_ch, raw) == {"error": "usb passthrough disabled"}


# --- the split keeps every name where it was -------------------------------


def test_public_names_are_the_same_objects_wherever_they_are_imported_from():
    assert viewer_client.ClientHandle is client_handle.ClientHandle is ClientHandle
    for name, exported in (("UsbClientError", UsbClientError),
                           ("UsbClientTimeout", UsbClientTimeout),
                           ("UsbClientClosed", UsbClientClosed),
                           ("UsbClientDesynchronized", UsbClientDesynchronized)):
        assert getattr(viewer_client, name) is getattr(client_errors, name) is exported
    assert set(viewer_client.__all__) == {
        "ClientHandle", "UsbClientClosed", "UsbClientDesynchronized",
        "UsbClientError", "UsbClientTimeout", "UsbPassthroughClient",
    }
