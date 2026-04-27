"""Tests for UsbPassthroughClient (round 40).

Wires the viewer client to a host session via a manual frame router so
the protocol round-trip can be exercised without a real WebRTC
DataChannel.
"""
import threading
import time

import pytest

from je_auto_control.utils.usb.passthrough import (
    Frame, Opcode, UsbClientClosed, UsbClientError, UsbClientTimeout,
    UsbPassthroughClient, UsbPassthroughSession,
)
from je_auto_control.utils.usb.passthrough.backend import (
    BackendDevice, FakeUsbBackend,
)


_SAMPLE = BackendDevice(vendor_id="1050", product_id="0407", serial="ABC123")


class _Loop:
    """Wires a UsbPassthroughClient to a UsbPassthroughSession.

    Frames sent by either side are routed to the other on a dedicated
    pump thread so the client's blocking calls actually unblock when
    the host's reply arrives.
    """

    def __init__(self, host: UsbPassthroughSession,
                 *, initial_credit_guess: int = 16) -> None:
        self._host = host
        self._client_to_host: list = []
        self._lock = threading.Lock()
        self._cond = threading.Condition(self._lock)
        self._stop = False
        self._client = UsbPassthroughClient(
            send_frame=self._enqueue,
            reply_timeout_s=2.0,
            credit_timeout_s=2.0,
            initial_credit_guess=initial_credit_guess,
        )
        self._thread = threading.Thread(target=self._pump, daemon=True)
        self._thread.start()

    @property
    def client(self) -> UsbPassthroughClient:
        return self._client

    def stop(self) -> None:
        with self._cond:
            self._stop = True
            self._cond.notify_all()
        self._thread.join(timeout=2.0)
        self._client.shutdown()

    def _enqueue(self, frame: Frame) -> None:
        with self._cond:
            self._client_to_host.append(frame)
            self._cond.notify_all()

    def _pump(self) -> None:
        while True:
            with self._cond:
                while not self._client_to_host and not self._stop:
                    self._cond.wait(timeout=0.5)
                if self._stop and not self._client_to_host:
                    return
                pending = list(self._client_to_host)
                self._client_to_host.clear()
            for inbound in pending:
                replies = self._host.handle_frame(inbound)
                for reply in replies:
                    self._client.feed_frame(reply)


@pytest.fixture()
def loop():
    backend = FakeUsbBackend(devices=[_SAMPLE])
    host = UsbPassthroughSession(backend)
    pipe = _Loop(host)
    yield pipe, host, backend
    pipe.stop()


# ---------------------------------------------------------------------------
# Open / close
# ---------------------------------------------------------------------------


def test_open_and_close_round_trip(loop):
    pipe, _host, _backend = loop
    handle = pipe.client.open(vendor_id="1050", product_id="0407",
                              serial="ABC123")
    assert handle.claim_id >= 1
    assert pipe.client.credits_remaining(handle.claim_id) == 16
    handle.close()
    assert handle.closed is True
    # Credits forgotten after close.
    assert pipe.client.credits_remaining(handle.claim_id) == 0


def test_open_failure_propagates_as_error(loop):
    pipe, _host, _backend = loop
    with pytest.raises(UsbClientError) as exc_info:
        pipe.client.open(vendor_id="dead", product_id="beef")
    assert "no fake device" in str(exc_info.value)


def test_close_is_idempotent(loop):
    pipe, _host, _backend = loop
    handle = pipe.client.open(vendor_id="1050", product_id="0407")
    handle.close()
    handle.close()  # second close must not raise


# ---------------------------------------------------------------------------
# Transfers — happy path
# ---------------------------------------------------------------------------


def test_control_transfer_returns_bytes(loop):
    pipe, _host, backend = loop
    handle = pipe.client.open(vendor_id="1050", product_id="0407")
    backend_handle = next(iter(backend._open_handles.values()))
    backend_handle.transfer_hook = lambda kind, kwargs: b"\xde\xad\xbe\xef"
    result = handle.control_transfer(
        bm_request_type=0xC0, b_request=6, w_value=0x0100, length=4,
    )
    assert result == b"\xde\xad\xbe\xef"


def test_bulk_in_returns_bytes(loop):
    pipe, _host, backend = loop
    handle = pipe.client.open(vendor_id="1050", product_id="0407")
    backend_handle = next(iter(backend._open_handles.values()))
    backend_handle.transfer_hook = lambda kind, kwargs: b"hello"
    result = handle.bulk_transfer(endpoint=0x81, direction="in", length=64)
    assert result == b"hello"


def test_bulk_out_round_trip(loop):
    pipe, _host, backend = loop
    handle = pipe.client.open(vendor_id="1050", product_id="0407")
    backend_handle = next(iter(backend._open_handles.values()))
    handle.bulk_transfer(endpoint=0x01, direction="out", data=b"world")
    assert backend_handle.calls[0]["data"] == b"world"
    assert backend_handle.calls[0]["direction"] == "out"


def test_interrupt_transfer_round_trip(loop):
    pipe, _host, backend = loop
    handle = pipe.client.open(vendor_id="1050", product_id="0407")
    backend_handle = next(iter(backend._open_handles.values()))
    backend_handle.transfer_hook = lambda kind, kwargs: b"\xff"
    result = handle.interrupt_transfer(endpoint=0x82, direction="in", length=8)
    assert result == b"\xff"


# ---------------------------------------------------------------------------
# Transfers — failure paths
# ---------------------------------------------------------------------------


def test_backend_error_raises_on_client(loop):
    pipe, _host, backend = loop
    handle = pipe.client.open(vendor_id="1050", product_id="0407")
    backend_handle = next(iter(backend._open_handles.values()))

    def boom(_kind, _kwargs):
        raise RuntimeError("device stalled")
    backend_handle.transfer_hook = boom

    with pytest.raises(UsbClientError) as exc_info:
        handle.bulk_transfer(endpoint=0x81, direction="in", length=64)
    assert "device stalled" in str(exc_info.value)


def test_transfer_after_close_raises_closed(loop):
    pipe, _host, _backend = loop
    handle = pipe.client.open(vendor_id="1050", product_id="0407")
    handle.close()
    with pytest.raises(UsbClientClosed):
        handle.bulk_transfer(endpoint=0x81, direction="in", length=64)


def test_bad_direction_raises(loop):
    pipe, _host, _backend = loop
    handle = pipe.client.open(vendor_id="1050", product_id="0407")
    with pytest.raises(ValueError):
        handle.bulk_transfer(endpoint=0x81, direction="sideways", length=4)


# ---------------------------------------------------------------------------
# Credit handling
# ---------------------------------------------------------------------------


def test_each_transfer_consumes_then_replenishes_one_credit(loop):
    pipe, _host, backend = loop
    handle = pipe.client.open(vendor_id="1050", product_id="0407")
    backend_handle = next(iter(backend._open_handles.values()))
    backend_handle.transfer_hook = lambda kind, kwargs: b""

    # Net change should be zero — host returns CREDIT(1) per reply.
    initial = pipe.client.credits_remaining(handle.claim_id)
    handle.bulk_transfer(endpoint=0x01, direction="out", data=b"hi")
    # Pumping is async; give the inbound CREDIT a moment to land.
    for _ in range(40):
        if pipe.client.credits_remaining(handle.claim_id) == initial:
            break
        time.sleep(0.025)
    assert pipe.client.credits_remaining(handle.claim_id) == initial


def test_credit_exhaustion_blocks_then_resumes():
    """If the client starts with fewer credits than the host grants,
    requests block on the credit semaphore until CREDIT arrives.
    """
    backend = FakeUsbBackend(devices=[_SAMPLE])
    host = UsbPassthroughSession(backend, initial_credits=16)
    # Tiny client-side guess so we burn through it quickly.
    pipe = _Loop(host, initial_credit_guess=2)
    try:
        handle = pipe.client.open(vendor_id="1050", product_id="0407")
        backend_handle = next(iter(backend._open_handles.values()))
        backend_handle.transfer_hook = lambda kind, kwargs: b""
        # Two transfers consume the budget; CREDIT(1) replies refill 1 each.
        # Three transfers will need at least one credit-wait but should still
        # complete since the host keeps returning CREDIT(1).
        for _ in range(5):
            handle.bulk_transfer(endpoint=0x01, direction="out", data=b"!")
        assert backend_handle.calls
    finally:
        pipe.stop()


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


def test_shutdown_unblocks_pending_transfers():
    """Shutting down the client mid-flight should release any waiter
    with UsbClientClosed instead of hanging on the reply event.
    """
    backend = FakeUsbBackend(devices=[_SAMPLE])
    host = UsbPassthroughSession(backend)

    # Build a client that doesn't get a transport-pump partner — sends
    # are sent to a sink and never return.
    sent: list = []
    client = UsbPassthroughClient(
        send_frame=sent.append,
        reply_timeout_s=10.0,  # large; we want shutdown to short-circuit it
        credit_timeout_s=10.0,
    )

    def trigger_open():
        try:
            client.open(vendor_id="1050", product_id="0407")
        except UsbClientClosed:
            opens.append("closed")
        except UsbClientError as error:  # noqa: F841  # reason: shutdown ordering may surface as either
            opens.append(f"error:{error}")

    opens: list = []
    t = threading.Thread(target=trigger_open)
    t.start()
    # Give the open thread a moment to register its pending request.
    time.sleep(0.1)
    client.shutdown()
    t.join(timeout=2.0)
    assert not t.is_alive()
    assert opens, opens
    _ = host  # silence unused


def test_two_concurrent_opens_rejected(loop):
    pipe, _host, _backend = loop
    # Block the first open by stealing the pump thread temporarily.
    blocker = threading.Event()
    original = pipe.client._send_frame

    def slow_send(frame):
        if frame.op == Opcode.OPEN:
            blocker.wait(timeout=2.0)
        original(frame)
    pipe.client._send_frame = slow_send

    results: list = []

    def attempt():
        try:
            handle = pipe.client.open(vendor_id="1050", product_id="0407")
            results.append(("ok", handle.claim_id))
        except UsbClientError as error:
            results.append(("err", str(error)))

    t1 = threading.Thread(target=attempt)
    t2 = threading.Thread(target=attempt)
    t1.start()
    time.sleep(0.05)
    t2.start()
    time.sleep(0.05)
    blocker.set()
    t1.join(timeout=3.0)
    t2.join(timeout=3.0)
    pipe.client._send_frame = original

    kinds = [r[0] for r in results]
    # Exactly one should succeed and one should hit "another open in progress".
    assert sorted(kinds) == ["err", "ok"], results


def test_open_timeout_when_host_silent():
    """If the host never replies, OPEN raises UsbClientTimeout."""
    sent: list = []
    client = UsbPassthroughClient(
        send_frame=sent.append, reply_timeout_s=0.2, credit_timeout_s=0.5,
    )
    try:
        with pytest.raises(UsbClientTimeout):
            client.open(vendor_id="1050", product_id="0407")
    finally:
        client.shutdown()
