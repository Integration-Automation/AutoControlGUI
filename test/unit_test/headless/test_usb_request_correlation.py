"""USB passthrough replies are paired with the request that asked for them.

Replies used to be matched by kind only (OPEN / LIST / claim), so a reply
that arrived after its request had timed out completed the *next* request
of that kind: ``open(bbbb)`` bound the claim opened for ``aaaa``, and a
bulk read returned the previous read's data.

The wire is a fake: frames the client sends are captured in a list and the
test plays the host by hand, which is the only way to deliver a reply late.
"""
import base64
import json
import threading

import pytest

from je_auto_control.utils.usb.passthrough import (
    FLAG_EOF, Frame, MAX_PAYLOAD_BYTES, Opcode, UsbClientError,
    UsbClientTimeout, UsbPassthroughClient, UsbPassthroughSession,
    fragment_payload, viewer_client,
)
from je_auto_control.utils.usb.passthrough.backend import (
    BackendDevice, FakeUsbBackend,
)

_SAMPLE = BackendDevice(vendor_id="1050", product_id="0407", serial="ABC123")
_WAIT_S = 5.0
#: Replies a host may split across frames; the last one carries FLAG_EOF.
_FRAGMENTED = (Opcode.LIST, Opcode.CTRL, Opcode.BULK, Opcode.INT)


class _Wire:
    """Captures what the client sends; the test feeds the replies."""

    def __init__(self, *, timeout_s: float = 0.15) -> None:
        self.sent = []
        self._cond = threading.Condition()
        self.client = UsbPassthroughClient(
            send_frame=self._send, reply_timeout_s=timeout_s,
        )

    def _send(self, frame: Frame) -> None:
        with self._cond:
            self.sent.append(frame)
            self._cond.notify_all()

    def wait_sent(self, count: int) -> Frame:
        """Block until the client has sent ``count`` frames; return the last."""
        with self._cond:
            if not self._cond.wait_for(lambda: len(self.sent) >= count, _WAIT_S):
                raise AssertionError(f"client sent {len(self.sent)} frames, wanted {count}")
            return self.sent[count - 1]

    def patient(self) -> None:
        """Later requests must not time out while the test is feeding frames."""
        self.client._reply_timeout = _WAIT_S  # noqa: SLF001  # reason: the first request needs a short timeout, the rest a long one


class _Call:
    """Runs a blocking client call on a thread and keeps its outcome."""

    def __init__(self, function) -> None:
        self.result = None
        self.error = None
        self._thread = threading.Thread(target=self._run, args=(function,), daemon=True)
        self._thread.start()

    def _run(self, function) -> None:
        try:
            self.result = function()
        except Exception as error:  # noqa: BLE001  # reason: the test asserts on whatever the call raised
            self.error = error

    def finish(self):
        self._thread.join(_WAIT_S)
        assert not self._thread.is_alive(), "client call never returned"
        if self.error is not None:
            raise self.error
        return self.result


def _body(frame: Frame) -> dict:
    return json.loads(frame.payload.decode("utf-8")) if frame.payload else {}


def _payload(body: dict, request: Frame = None) -> bytes:
    """A reply payload; echoes ``request``'s id the way a current host does."""
    body = dict(body)
    request_id = _body(request).get("request_id") if request is not None else None
    if request_id is not None:
        body["request_id"] = request_id
    return json.dumps(body).encode("utf-8")


def _reply(op: Opcode, claim_id: int, body: dict, request: Frame = None) -> Frame:
    flags = FLAG_EOF if op in _FRAGMENTED else 0
    return Frame(op=op, flags=flags, claim_id=claim_id, payload=_payload(body, request))


def _data_body(data: bytes) -> dict:
    return {"ok": True, "data": base64.b64encode(data).decode("ascii")}


def _data_reply(op: Opcode, claim_id: int, data: bytes, request: Frame = None) -> Frame:
    return _reply(op, claim_id, _data_body(data), request)


def _big_reply(claim_id: int, data: bytes, request: Frame) -> list:
    """A BULK reply too large for one frame, split the way the host splits it."""
    frames = fragment_payload(Opcode.BULK, claim_id, _payload(_data_body(data), request))
    assert len(frames) > 1
    return frames


def _current_peer(wire: "_Wire") -> None:
    """Answer one LIST with its id echoed, so the client knows the host is current."""
    sent_before = len(wire.sent)
    call = _Call(wire.client.list_devices)
    request = wire.wait_sent(sent_before + 1)
    wire.client.feed_frame(_reply(Opcode.LIST, 0, {"devices": []}, request))
    call.finish()


def _opened(wire: _Wire, claim_id: int, *, echo: bool = True):
    """Open a claim on ``wire``; the reply echoes the id unless told not to."""
    sent_before = len(wire.sent)
    call = _Call(lambda: wire.client.open(vendor_id="1050", product_id="0407"))
    request = wire.wait_sent(sent_before + 1)
    wire.client.feed_frame(_reply(
        Opcode.OPENED, claim_id, {"ok": True, "claim_id": claim_id},
        request if echo else None))
    return call.finish()


def _timed_out_bulk(wire: _Wire, handle) -> Frame:
    """Issue a bulk read nobody answers; return the request that timed out."""
    sent_before = len(wire.sent)
    with pytest.raises(UsbClientTimeout):
        # timeout_ms=0: the client waits the transfer's own timeout on top of
        # reply_timeout_s, and the default 1000 ms would add a second per call.
        handle.bulk_transfer(endpoint=0x81, direction="in", length=8, timeout_ms=0)
    return wire.sent[sent_before]


# --- the two failures the audit reproduced ---------------------------------


def test_late_open_does_not_complete_next_open():
    wire = _Wire()
    _current_peer(wire)
    with pytest.raises(UsbClientTimeout):
        wire.client.open(vendor_id="aaaa", product_id="0001")
    first = wire.sent[1]
    wire.patient()

    call = _Call(lambda: wire.client.open(vendor_id="bbbb", product_id="0002"))
    second = wire.wait_sent(3)
    wire.client.feed_frame(_reply(Opcode.OPENED, 1, {"ok": True, "claim_id": 1}, first))
    assert wire.client.pending_count() == 1, "the late OPENED completed the next open"

    wire.client.feed_frame(_reply(Opcode.OPENED, 2, {"ok": True, "claim_id": 2}, second))
    assert call.finish().claim_id == 2


def test_late_transfer_does_not_complete_next_transfer():
    wire = _Wire()
    handle = _opened(wire, 1)
    first = _timed_out_bulk(wire, handle)
    wire.patient()

    call = _Call(lambda: handle.bulk_transfer(endpoint=0x81, direction="in", length=8))
    second = wire.wait_sent(3)
    wire.client.feed_frame(_data_reply(Opcode.BULK, 1, b"stale", first))
    assert wire.client.pending_count() == 1, "the late BULK completed the next transfer"

    wire.client.feed_frame(_data_reply(Opcode.BULK, 1, b"fresh", second))
    assert call.finish() == b"fresh"


def test_late_list_does_not_complete_next_list():
    wire = _Wire()
    _current_peer(wire)
    with pytest.raises(UsbClientTimeout):
        wire.client.list_devices()
    first = wire.sent[1]
    wire.patient()

    call = _Call(wire.client.list_devices)
    second = wire.wait_sent(3)
    wire.client.feed_frame(_reply(Opcode.LIST, 0, {"devices": [{"vendor_id": "old"}]}, first))
    wire.client.feed_frame(_reply(Opcode.LIST, 0, {"devices": [{"vendor_id": "new"}]}, second))
    assert call.finish() == [{"vendor_id": "new"}]


# --- a peer that echoes ids: only the expired reply is discarded -----------


def test_every_request_carries_a_distinct_string_id():
    wire = _Wire()
    handle = _opened(wire, 1)
    for _ in range(3):
        _timed_out_bulk(wire, handle)
    ids = [_body(frame)["request_id"] for frame in wire.sent]
    assert all(isinstance(value, str) and value for value in ids)
    assert len(set(ids)) == len(ids)


def test_claim_stays_usable_after_timeout_when_peer_echoes_ids():
    wire = _Wire()
    handle = _opened(wire, 1)      # the OPENED echoed an id: the peer is current
    _timed_out_bulk(wire, handle)
    assert wire.client.peer_echoes_request_ids is True
    assert handle.reusable is True


def test_late_open_reply_releases_the_claim_nobody_holds():
    """The host opened the device for a caller that has already given up."""
    wire = _Wire()
    with pytest.raises(UsbClientTimeout):
        wire.client.open(vendor_id="aaaa", product_id="0001")
    wire.client.feed_frame(_reply(
        Opcode.OPENED, 7, {"ok": True, "claim_id": 7}, wire.sent[0]))
    assert wire.client.reusable is True     # the echoed id showed the host is current
    close = wire.wait_sent(2)
    assert (close.op, close.claim_id) == (Opcode.CLOSE, 7)
    # Its CLOSED is expected by nobody and must be dropped quietly.
    wire.client.feed_frame(_reply(Opcode.CLOSED, 7, {"ok": True}, close))
    assert wire.client.pending_count() == 0


def test_late_resume_reply_does_not_close_the_claim():
    """A resumed claim may be in use again by the time the late reply lands."""
    wire = _Wire()
    with pytest.raises(UsbClientTimeout):
        wire.client.resume("token")
    wire.client.feed_frame(_reply(
        Opcode.OPENED, 7, {"ok": True, "claim_id": 7}, wire.sent[0]))
    assert len(wire.sent) == 1


def test_late_fragmented_reply_is_discarded_whole():
    wire = _Wire()
    handle = _opened(wire, 1)
    first = _timed_out_bulk(wire, handle)
    wire.patient()
    stale_frames = _big_reply(1, b"\x01" * (MAX_PAYLOAD_BYTES * 2), first)

    call = _Call(lambda: handle.bulk_transfer(endpoint=0x81, direction="in", length=8))
    second = wire.wait_sent(3)
    for frame in stale_frames:
        wire.client.feed_frame(frame)
    assert wire.client.pending_count() == 1
    for frame in _big_reply(1, b"\x02" * (MAX_PAYLOAD_BYTES * 2), second):
        wire.client.feed_frame(frame)
    assert call.finish() == b"\x02" * (MAX_PAYLOAD_BYTES * 2)


def test_reply_half_received_at_the_timeout_is_still_discarded_whole():
    """The buffer is not reset by the timeout, so the tail is not a new message."""
    wire = _Wire(timeout_s=0.5)
    handle = _opened(wire, 1)
    sent_before = len(wire.sent)
    call = _Call(lambda: handle.bulk_transfer(
        endpoint=0x81, direction="in", length=8, timeout_ms=0))
    first = wire.wait_sent(sent_before + 1)
    stale_frames = _big_reply(1, b"\x01" * (MAX_PAYLOAD_BYTES * 2), first)
    wire.client.feed_frame(stale_frames[0])
    with pytest.raises(UsbClientTimeout):
        call.finish()
    wire.patient()

    call = _Call(lambda: handle.bulk_transfer(endpoint=0x81, direction="in", length=8))
    second = wire.wait_sent(sent_before + 2)
    for frame in stale_frames[1:]:
        wire.client.feed_frame(frame)
    assert wire.client.pending_count() == 1
    wire.client.feed_frame(_data_reply(Opcode.BULK, 1, b"fresh", second))
    assert call.finish() == b"fresh"


def test_late_error_does_not_fail_the_next_transfer():
    wire = _Wire()
    handle = _opened(wire, 1)
    first = _timed_out_bulk(wire, handle)
    wire.patient()

    call = _Call(lambda: handle.bulk_transfer(endpoint=0x81, direction="in", length=8))
    second = wire.wait_sent(3)
    wire.client.feed_frame(_reply(Opcode.ERROR, 1, {"error": "credit exhausted"}, first))
    assert wire.client.pending_count() == 1, "the late ERROR failed the next transfer"
    wire.client.feed_frame(_data_reply(Opcode.BULK, 1, b"fresh", second))
    assert call.finish() == b"fresh"


def test_error_with_an_id_fails_the_open_it_answers():
    """A locked-out host answers OPEN with ERROR on claim 0; it used to time out."""
    wire = _Wire(timeout_s=_WAIT_S)
    call = _Call(lambda: wire.client.open(vendor_id="1050", product_id="0407"))
    request = wire.wait_sent(1)
    wire.client.feed_frame(_reply(
        Opcode.ERROR, 0, {"error": "rate limited; locked out"}, request))
    with pytest.raises(UsbClientError, match="rate limited"):
        call.finish()


def test_credit_from_a_late_reply_is_still_granted():
    """CREDIT is a grant on the claim, not a reply to one request."""
    wire = _Wire()
    handle = _opened(wire, 1)
    before = wire.client.credits_remaining(1)
    first = _timed_out_bulk(wire, handle)
    assert wire.client.credits_remaining(1) == before - 1
    wire.client.feed_frame(_data_reply(Opcode.BULK, 1, b"stale", first))
    wire.client.feed_frame(Frame(op=Opcode.CREDIT, claim_id=1, payload=b'{"credits": 1}'))
    assert wire.client.credits_remaining(1) == before


def test_reply_with_the_wrong_kind_for_its_id_is_dropped():
    wire = _Wire()
    handle = _opened(wire, 1)
    wire.patient()
    call = _Call(lambda: handle.bulk_transfer(endpoint=0x81, direction="in", length=8))
    request = wire.wait_sent(2)
    wire.client.feed_frame(_data_reply(Opcode.CTRL, 1, b"wrong", request))
    assert wire.client.pending_count() == 1
    wire.client.feed_frame(_data_reply(Opcode.BULK, 1, b"right", request))
    assert call.finish() == b"right"


def test_oversize_message_is_skipped_through_its_last_fragment():
    """The tail of a dropped message used to be parsed as a message of its own."""
    wire = _Wire(timeout_s=_WAIT_S)
    handle = _opened(wire, 1)
    call = _Call(lambda: handle.bulk_transfer(endpoint=0x81, direction="in", length=8))
    request = wire.wait_sent(2)
    chunk = b"x" * MAX_PAYLOAD_BYTES
    limit = viewer_client._MAX_REASSEMBLED_BYTES  # noqa: SLF001  # reason: the cap is the thing under test
    for _ in range(limit // MAX_PAYLOAD_BYTES + 1):
        wire.client.feed_frame(Frame(op=Opcode.BULK, claim_id=1, payload=chunk))
    wire.client.feed_frame(Frame(op=Opcode.BULK, claim_id=1, flags=FLAG_EOF, payload=b"tail"))
    assert wire.client.pending_count() == 1, "the tail completed the request"
    wire.client.feed_frame(_data_reply(Opcode.BULK, 1, b"next", request))
    assert call.finish() == b"next"


# --- a peer that does not echo ids: stop, do not guess ---------------------


def test_legacy_timeout_requires_reconnect():
    wire = _Wire()
    handle = _opened(wire, 1, echo=False)
    _timed_out_bulk(wire, handle)
    assert wire.client.peer_echoes_request_ids is False
    assert handle.reusable is False

    sent = len(wire.sent)
    with pytest.raises(viewer_client.UsbClientDesynchronized, match="claim 1"):
        handle.bulk_transfer(endpoint=0x81, direction="in", length=8)
    assert len(wire.sent) == sent, "a request went out on a desynchronised claim"
    # The late reply has nobody to mislead any more.
    wire.client.feed_frame(_data_reply(Opcode.BULK, 1, b"stale"))
    assert wire.client.pending_count() == 0


def test_legacy_desynchronised_claim_can_still_be_closed():
    wire = _Wire()
    handle = _opened(wire, 1, echo=False)
    _timed_out_bulk(wire, handle)
    wire.patient()
    call = _Call(handle.close)
    close = wire.wait_sent(3)
    assert close.op == Opcode.CLOSE
    wire.client.feed_frame(_data_reply(Opcode.BULK, 1, b"stale"))   # wrong kind for CLOSE
    assert wire.client.pending_count() == 1
    wire.client.feed_frame(_reply(Opcode.CLOSED, 1, {"ok": True}))
    call.finish()
    assert handle.closed


def test_legacy_timeout_on_one_claim_leaves_the_others_usable():
    wire = _Wire()
    broken = _opened(wire, 1, echo=False)
    healthy = _opened(wire, 2, echo=False)
    _timed_out_bulk(wire, broken)
    wire.patient()
    assert healthy.reusable is True
    call = _Call(lambda: healthy.bulk_transfer(endpoint=0x81, direction="in", length=8))
    wire.wait_sent(4)
    wire.client.feed_frame(_data_reply(Opcode.BULK, 2, b"fine"))
    assert call.finish() == b"fine"


def test_legacy_open_timeout_blocks_further_opens():
    wire = _Wire()
    with pytest.raises(UsbClientTimeout):
        wire.client.open(vendor_id="aaaa", product_id="0001")
    assert wire.client.reusable is False
    with pytest.raises(viewer_client.UsbClientDesynchronized, match="[Rr]econnect"):
        wire.client.open(vendor_id="bbbb", product_id="0002")
    with pytest.raises(viewer_client.UsbClientDesynchronized):
        wire.client.resume("token")
    assert len(wire.sent) == 1
    # The late, id-less OPENED is dropped rather than handed to anyone.
    wire.client.feed_frame(_reply(Opcode.OPENED, 1, {"ok": True, "claim_id": 1}))
    assert wire.client.reusable is False


def test_legacy_list_timeout_blocks_further_lists():
    wire = _Wire()
    with pytest.raises(UsbClientTimeout):
        wire.client.list_devices()
    with pytest.raises(viewer_client.UsbClientDesynchronized):
        wire.client.list_devices()


def test_desynchronised_error_is_a_client_error():
    from je_auto_control.utils.exception.exceptions import AutoControlException
    assert issubclass(viewer_client.UsbClientDesynchronized, UsbClientError)
    assert issubclass(viewer_client.UsbClientDesynchronized, AutoControlException)


def test_peer_of_unknown_age_is_cleared_once_it_echoes_an_id():
    """The very first request timed out, so nothing says yet what the peer is."""
    wire = _Wire()
    with pytest.raises(UsbClientTimeout):
        wire.client.open(vendor_id="aaaa", product_id="0001")
    assert wire.client.reusable is False
    wire.client.feed_frame(_reply(
        Opcode.OPENED, 0, {"ok": False, "error": "no device"}, wire.sent[0]))
    assert wire.client.peer_echoes_request_ids is True
    assert wire.client.reusable is True
    assert _opened(wire, 3).claim_id == 3


def test_reply_with_an_id_nobody_issued_proves_nothing():
    wire = _Wire()
    with pytest.raises(UsbClientTimeout):
        wire.client.open(vendor_id="aaaa", product_id="0001")
    wire.client.feed_frame(Frame(
        op=Opcode.OPENED, claim_id=1,
        payload=b'{"ok": true, "claim_id": 1, "request_id": "not-ours"}'))
    assert wire.client.peer_echoes_request_ids is False
    assert wire.client.reusable is False


# --- the host --------------------------------------------------------------


def _session() -> UsbPassthroughSession:
    return UsbPassthroughSession(FakeUsbBackend(devices=[_SAMPLE]))


def _request(op: Opcode, claim_id: int = 0, **body) -> Frame:
    return Frame(op=op, claim_id=claim_id, payload=json.dumps(body).encode("utf-8"))


def _joined(replies, op: Opcode) -> dict:
    return json.loads(b"".join(r.payload for r in replies if r.op == op).decode("utf-8"))


_OPEN_BODY = {"vendor_id": "1050", "product_id": "0407", "serial": "ABC123"}
_CTRL_BODY = {"bm_request_type": 0xC0, "b_request": 6, "length": 18}


def test_host_echoes_the_id_on_every_reply_kind():
    session = _session()
    opened = _joined(session.handle_frame(
        _request(Opcode.OPEN, request_id="r-open", **_OPEN_BODY)), Opcode.OPENED)
    assert (opened["ok"], opened["request_id"]) == (True, "r-open")
    claim = opened["claim_id"]

    resumed = _joined(session.handle_frame(_request(
        Opcode.RESUME, resume_token=opened["resume_token"], request_id="r-res")), Opcode.OPENED)
    assert resumed["request_id"] == "r-res"

    listed = _joined(session.handle_frame(
        _request(Opcode.LIST, request_id="r-list")), Opcode.LIST)
    assert listed["request_id"] == "r-list"
    assert len(listed["devices"]) == 1

    for op in (Opcode.CTRL, Opcode.BULK, Opcode.INT):
        body = _CTRL_BODY if op == Opcode.CTRL else {
            "endpoint": 0x81, "direction": "in", "length": 4}
        replies = session.handle_frame(_request(op, claim, request_id=f"r-{op.name}", **body))
        assert _joined(replies, op)["request_id"] == f"r-{op.name}"

    unknown = _joined(session.handle_frame(
        _request(Opcode.BULK, 99, request_id="r-err", endpoint=1, direction="in")), Opcode.ERROR)
    assert unknown["request_id"] == "r-err"

    closed = _joined(session.handle_frame(
        _request(Opcode.CLOSE, claim, request_id="r-close")), Opcode.CLOSED)
    assert closed == {"ok": True, "request_id": "r-close"}


def test_host_does_not_put_an_id_on_credit_frames():
    session = _session()
    claim = _joined(session.handle_frame(
        _request(Opcode.OPEN, request_id="a", **_OPEN_BODY)), Opcode.OPENED)["claim_id"]
    replies = session.handle_frame(_request(Opcode.CTRL, claim, request_id="b", **_CTRL_BODY))
    assert _joined(replies, Opcode.CREDIT) == {"credits": 1}


def test_host_reply_to_a_request_without_an_id_is_unchanged():
    """An older viewer must see exactly the payloads it always saw."""
    session = _session()
    opened = _joined(session.handle_frame(_request(Opcode.OPEN, **_OPEN_BODY)), Opcode.OPENED)
    assert set(opened) == {"ok", "claim_id", "resume_token"}
    claim = opened["claim_id"]
    assert set(_joined(session.handle_frame(Frame(op=Opcode.LIST)), Opcode.LIST)) == {"devices"}
    transfer = session.handle_frame(_request(Opcode.CTRL, claim, **_CTRL_BODY))
    assert set(_joined(transfer, Opcode.CTRL)) == {"ok", "data"}
    assert _joined(session.handle_frame(
        Frame(op=Opcode.CLOSE, claim_id=claim)), Opcode.CLOSED) == {"ok": True}
    assert set(_joined(session.handle_frame(
        Frame(op=Opcode.CLOSE, claim_id=claim)), Opcode.ERROR)) == {"error"}


@pytest.mark.parametrize("bad_id", [7, "", "x" * 65, None, ["a"], {"a": 1}, True])
def test_host_ignores_an_id_it_cannot_echo(bad_id):
    session = _session()
    opened = _joined(session.handle_frame(
        _request(Opcode.OPEN, request_id=bad_id, **_OPEN_BODY)), Opcode.OPENED)
    assert opened["ok"] is True
    assert "request_id" not in opened


def test_host_echoes_the_id_when_the_peer_is_locked_out():
    session = _session()
    for _ in range(40):
        session.handle_frame(Frame(op=Opcode.CLOSE, claim_id=99))
    assert session.is_locked_out()
    reply = _joined(session.handle_frame(
        _request(Opcode.OPEN, request_id="r", **_OPEN_BODY)), Opcode.ERROR)
    assert reply["request_id"] == "r"
    assert "locked out" in reply["error"]


def test_host_echoes_the_id_on_a_fragmented_reply():
    session = _session()
    claim = _joined(session.handle_frame(
        _request(Opcode.OPEN, request_id="a", **_OPEN_BODY)), Opcode.OPENED)["claim_id"]
    replies = session.handle_frame(_request(
        Opcode.BULK, claim, request_id="big", endpoint=0x81, direction="in",
        length=MAX_PAYLOAD_BYTES * 2))
    data_frames = [r for r in replies if r.op == Opcode.BULK]
    assert len(data_frames) > 1
    assert _joined(replies, Opcode.BULK)["request_id"] == "big"


# --- both ends together, across versions -----------------------------------


class _Routed:
    """A real session behind the client; ``legacy_host`` strips echoed ids."""

    def __init__(self, *, legacy_host: bool) -> None:
        self.session = _session()
        self._legacy_host = legacy_host
        self.client = UsbPassthroughClient(send_frame=self._send, reply_timeout_s=_WAIT_S)

    def _send(self, frame: Frame) -> None:
        if self._legacy_host:
            frame = _without_id(frame)       # an old host never reads the field
        threading.Thread(target=self._deliver, args=(frame,), daemon=True).start()

    def _deliver(self, frame: Frame) -> None:
        for reply in self.session.handle_frame(frame):
            self.client.feed_frame(reply)


def _without_id(frame: Frame) -> Frame:
    body = _body(frame)
    body.pop("request_id", None)
    payload = json.dumps(body).encode("utf-8") if body else b""
    return Frame(op=frame.op, flags=frame.flags, claim_id=frame.claim_id, payload=payload)


@pytest.mark.parametrize("legacy_host", [False, True])
def test_full_exchange_against_current_and_legacy_host(legacy_host):
    routed = _Routed(legacy_host=legacy_host)
    assert len(routed.client.list_devices()) == 1
    handle = routed.client.open(vendor_id="1050", product_id="0407", serial="ABC123")
    assert isinstance(handle.control_transfer(
        bm_request_type=0xC0, b_request=6, length=18), bytes)
    assert isinstance(handle.bulk_transfer(
        endpoint=0x81, direction="in", length=MAX_PAYLOAD_BYTES * 2), bytes)
    assert routed.client.resume(handle.resume_token).claim_id == handle.claim_id
    handle.close()
    assert routed.session.active_claim_count == 0
    assert routed.client.peer_echoes_request_ids is (not legacy_host)
    routed.client.shutdown()
