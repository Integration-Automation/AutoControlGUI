"""Tests for the WebRTC usb-channel adapters (no aiortc needed).

A pair of LinkedChannels plus an immediate bridge gives a synchronous
loopback over the channel abstraction, so the host/client adapters are
exercised end to end exactly as they would be over a real DataChannel.
"""
import pytest

from je_auto_control.utils.usb.passthrough import (
    AclRule, Opcode, UsbAcl, UsbChannelClient, UsbChannelHost,
    UsbClientError, UsbPassthroughSession, decode_frame,
)
from je_auto_control.utils.usb.passthrough.backend import (
    BackendDevice, FakeUsbBackend,
)

_SAMPLE = BackendDevice(vendor_id="1050", product_id="0407", serial="ABC123")


class _ImmediateBridge:
    @staticmethod
    def call_soon(fn, *args):
        fn(*args)


class _LinkedChannel:
    """Fake RTCDataChannel whose ``send`` delivers to its peer's handler."""

    def __init__(self):
        self._peer = None
        self._handlers = {}

    def link(self, peer):
        self._peer = peer

    def on(self, event):
        def _register(fn):
            self._handlers[event] = fn
            return fn
        return _register

    def send(self, data):
        handler = self._peer._handlers.get("message")
        if handler is not None:
            handler(data)


def _linked_pair():
    host_ch, client_ch = _LinkedChannel(), _LinkedChannel()
    host_ch.link(client_ch)
    client_ch.link(host_ch)
    return host_ch, client_ch


def _wire(session, *, enabled=True):
    host_ch, client_ch = _linked_pair()
    host = UsbChannelHost(
        host_ch, session=session, bridge=_ImmediateBridge(),
        enabled_check=lambda: enabled,
    )
    client = UsbChannelClient(client_ch, bridge=_ImmediateBridge())
    return host, client


def _allow_acl(tmp_path, *devices):
    acl = UsbAcl(path=tmp_path / "acl.json")
    for dev in devices:
        acl.add_rule(AclRule(vendor_id=dev.vendor_id,
                             product_id=dev.product_id, allow=True))
    return acl


def test_channel_list_devices_round_trip(tmp_path):
    session = UsbPassthroughSession(
        FakeUsbBackend(devices=[_SAMPLE]), acl=_allow_acl(tmp_path, _SAMPLE),
    )
    _host, client = _wire(session)
    try:
        devices = client.list_devices()
        assert [d["vendor_id"] for d in devices] == ["1050"]
    finally:
        client.shutdown()


def test_channel_open_and_transfer(tmp_path):
    backend = FakeUsbBackend(devices=[_SAMPLE])
    session = UsbPassthroughSession(backend, acl=_allow_acl(tmp_path, _SAMPLE))
    _host, client = _wire(session)
    try:
        handle = client.open(vendor_id="1050", product_id="0407")
        backend_handle = next(iter(backend._open_handles.values()))
        backend_handle.transfer_hook = lambda kind, kwargs: b"\xaa\xbb"
        assert handle.control_transfer(
            bm_request_type=0xC0, b_request=6, length=2,
        ) == b"\xaa\xbb"
        assert handle.resume_token
    finally:
        client.shutdown()


def test_channel_resume_after_reconnect(tmp_path):
    backend = FakeUsbBackend(devices=[_SAMPLE])
    session = UsbPassthroughSession(backend, acl=_allow_acl(tmp_path, _SAMPLE))
    _host1, client1 = _wire(session)
    handle = client1.open(vendor_id="1050", product_id="0407")
    token = handle.resume_token
    client1.shutdown()  # transport drop; host keeps the claim
    assert session.active_claim_count == 1
    _host2, client2 = _wire(session)
    try:
        resumed = client2.resume(token)
        assert resumed.claim_id == handle.claim_id
    finally:
        client2.shutdown()


def test_channel_disabled_flag_rejects(tmp_path):
    session = UsbPassthroughSession(
        FakeUsbBackend(devices=[_SAMPLE]), acl=_allow_acl(tmp_path, _SAMPLE),
    )
    _host, client = _wire(session, enabled=False)
    try:
        with pytest.raises(UsbClientError):
            client.list_devices()
    finally:
        client.shutdown()


def test_host_lazy_session_factory(tmp_path):
    backend = FakeUsbBackend(devices=[_SAMPLE])
    built = []

    def factory():
        built.append(1)
        return UsbPassthroughSession(backend, acl=_allow_acl(tmp_path, _SAMPLE))

    host_ch, client_ch = _linked_pair()
    UsbChannelHost(host_ch, session_factory=factory,
                   bridge=_ImmediateBridge(), enabled_check=lambda: True)
    client = UsbChannelClient(client_ch, bridge=_ImmediateBridge())
    try:
        assert client.list_devices() == [
            {"vendor_id": "1050", "product_id": "0407",
             "serial": "ABC123", "bus_location": None},
        ]
        assert built == [1]  # session built lazily on first message
    finally:
        client.shutdown()


def test_host_rejects_non_binary_frame(tmp_path):
    session = UsbPassthroughSession(FakeUsbBackend(devices=[_SAMPLE]))
    host_ch, client_ch = _linked_pair()
    sent = []
    client_ch.on("message")(sent.append)
    UsbChannelHost(host_ch, session=session, bridge=_ImmediateBridge(),
                   enabled_check=lambda: True)
    # A str (not bytes) is invalid on the binary usb channel → ERROR back.
    host_ch._handlers["message"]("not-binary")
    assert len(sent) == 1
    reply = decode_frame(sent[0])
    assert reply.op == Opcode.ERROR
