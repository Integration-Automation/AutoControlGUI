"""Owner-service channel tests against an in-process fake service; no socket, helper or desktop."""
import json
import queue
import struct
import threading
import time
from concurrent.futures import CancelledError

import pytest

from je_auto_control.utils.agent_runtime import helper_owner_linux as owner
from je_auto_control.utils.agent_runtime import owner_service_wire as wire
from je_auto_control.utils.agent_runtime.errors import AgentControlBusy, AgentTaskError
from je_auto_control.utils.agent_runtime.helper_owner_linux import OwnerServiceChannel
from je_auto_control.utils.agent_runtime.owner_service_nested import NestedGrant


def _id(raw):
    return struct.unpack("<QQ", raw)


def _ticket(raw):
    return _id(raw[:16]), _id(raw[16:])


def _reply_frame(opcode, nonce, status=wire.STATUS_OK, *, lease=(0, 0), ticket=((0, 0), (0, 0)), flags=0,
                 data_length=0, data=b"", report=wire.REPORT_PENDING):
    pack_id = lambda value: struct.pack("<QQ", *value)  # noqa: E731  # reason: local two-line codec helper
    return wire._REPLY.pack(wire.MAGIC, wire.VERSION, opcode, status, 0, 0, 0, pack_id(nonce), pack_id(lease), 0,
                            pack_id(ticket[0]) + pack_id(ticket[1]), flags, data_length, report, 0, 0, 0, data)


class FakeService:
    """Plays the owner service and its helper: leases, idempotent start, relay buffers, observe."""

    def __init__(self, *, behave=None, accept_limit=wire.DATA_BYTES, start_status=wire.STATUS_OK):
        self.replies = queue.Queue()
        self.lock = threading.Lock()
        self.leases = {}
        self.records = {}
        self.closed = set()
        self.stdin = bytearray()
        self.stdout = bytearray()
        self.eof = False
        self.behave = behave or {}
        self.accept_limit = accept_limit
        self.start_status = start_status
        self.drop_once = set()
        self.stray_before = set()
        self.settled = True
        self.grant = NestedGrant(((142, 1), (0, 3)), bytes(range(32)))
        self.calls = []
        self.transport_closed = False

    # ServiceTransport
    def send(self, frame):
        fields = wire._REQUEST.unpack(frame)
        opcode, nonce, lease = fields[2], _id(fields[3]), _id(fields[4])
        request_id, ticket, data_length, data = _id(fields[5]), _ticket(fields[11]), fields[12], fields[13]
        self.last_parent, self.last_capability = _ticket(fields[6]), fields[9]
        with self.lock:
            self.calls.append(opcode)
            reply = self._handle(opcode, nonce, lease, request_id, ticket, data[:data_length])
            if opcode in self.drop_once:
                self.drop_once.discard(opcode)
                return
            if opcode in self.stray_before:
                self.stray_before.discard(opcode)
                self.replies.put(_reply_frame(opcode, (9, 9)))
            self.replies.put(reply)

    def receive(self, timeout):
        try:
            return self.replies.get(timeout=timeout)
        except queue.Empty:
            return None

    def close(self):
        self.transport_closed = True

    # Service semantics
    def _handle(self, opcode, nonce, lease, request_id, ticket, data):
        if opcode == wire.OP_OPEN_CHILD:
            if (self.last_parent, self.last_capability) != (self.grant.parent, self.grant.capability):
                return _reply_frame(opcode, nonce, wire.STATUS_UNAUTHENTICATED)
            status = wire.STATUS_EXISTING if nonce in self.leases else wire.STATUS_OK
            self.leases.setdefault(nonce, (len(self.leases) + 1, 9))
            return _reply_frame(wire.OP_OPEN_CHILD, nonce, status, lease=self.leases[nonce])
        if opcode == wire.OP_OPEN_TOP:
            status = wire.STATUS_EXISTING if nonce in self.leases else wire.STATUS_OK
            self.leases.setdefault(nonce, (len(self.leases) + 1, 7))
            return _reply_frame(opcode, nonce, status, lease=self.leases[nonce])
        if opcode == wire.OP_START:
            if self.start_status != wire.STATUS_OK:
                return _reply_frame(opcode, nonce, self.start_status)
            status = wire.STATUS_EXISTING if request_id in self.records else wire.STATUS_OK
            self.records.setdefault(request_id, ((5, 5), (0, len(self.records) + 1)))
            return _reply_frame(opcode, nonce, status, ticket=self.records[request_id])
        if opcode == wire.OP_CLOSE:
            self.closed.add(lease)
            return _reply_frame(opcode, nonce)
        if lease in self.closed:
            if opcode == wire.OP_OBSERVE:
                return _reply_frame(opcode, nonce, report=wire.REPORT_RETIRED if self.settled
                                    else wire.REPORT_STICKY_UNKNOWN)
            return _reply_frame(opcode, nonce, wire.STATUS_CLOSED)
        if opcode == wire.OP_WRITE:
            accepted = min(len(data), self.accept_limit)
            self.stdin.extend(data[:accepted])
            self._run_helper()
            return _reply_frame(opcode, nonce, data_length=accepted)
        if opcode == wire.OP_READ:
            chunk = bytes(self.stdout[:wire.DATA_BYTES])
            del self.stdout[:len(chunk)]
            flags = wire.REPLY_EOF if self.eof and not self.stdout else 0
            return _reply_frame(opcode, nonce, flags=flags, data_length=len(chunk), data=chunk)
        return _reply_frame(opcode, nonce, report=wire.REPORT_PENDING)

    def _run_helper(self):
        while b"\n" in self.stdin:
            end = self.stdin.index(b"\n")
            line = json.loads(bytes(self.stdin[:end]))
            del self.stdin[:end + 1]
            if line.get("ack"):
                self._emit({"id": self.pending_event, "result": "acknowledged"})
                continue
            behaviour = self.behave.get(line["operation"], "echo")
            if behaviour == "echo":
                self._emit({"id": line["id"], "result": line["payload"]})
            elif behaviour == "event":
                self.pending_event = line["id"]
                self._emit({"id": line["id"], "event": {"kind": "key_press"}})
            elif behaviour == "busy":
                self._emit({"id": line["id"], "error": "held", "error_type": "AgentControlBusy"})
            elif behaviour == "exit":
                self.eof = True

    def _emit(self, value):
        self.stdout.extend(json.dumps(value).encode() + b"\n")


@pytest.fixture(autouse=True)
def short_calls(monkeypatch):
    monkeypatch.setattr(owner, "_CALL_SECONDS", 0.2)
    monkeypatch.setattr(owner, "_POLL_SECONDS", 0.005)


def test_wire_layout_matches_the_native_frames():
    assert (wire.REQUEST_SIZE, wire.REPLY_SIZE) == (9384, 8312)
    assert wire.REQUEST_OFFSETS["data"] == 1188 and wire.REPLY_OFFSETS["data"] == 120
    frame = wire.ServiceRequest(wire.OP_WRITE, (1, 2), ticket=((3, 4), (5, 6)), data=b"abc").pack()
    assert len(frame) == wire.REQUEST_SIZE
    assert frame[wire.REQUEST_OFFSETS["ticket"]:wire.REQUEST_OFFSETS["ticket"] + 8] == struct.pack("<Q", 3)
    assert frame[wire.REQUEST_OFFSETS["data"]:wire.REQUEST_OFFSETS["data"] + 3] == b"abc"


def test_wire_refuses_oversized_and_malformed_frames():
    with pytest.raises(AgentTaskError):
        wire.ServiceRequest(wire.OP_WRITE, (1, 1), data=b"x" * (wire.DATA_BYTES + 1)).pack()
    with pytest.raises(AgentTaskError):
        wire.ServiceRequest(wire.OP_START, (1, 1), arguments=("x" * wire.ARGUMENT_BYTES,)).pack()
    with pytest.raises(AgentTaskError):
        wire.unpack_reply(b"\0" * wire.REPLY_SIZE)
    with pytest.raises(AgentTaskError):
        wire.unpack_reply(b"\0" * 10)


def test_round_trip_then_idempotent_retirement():
    service = FakeService()
    channel = OwnerServiceChannel(service, 1, ("alpha",))
    assert service.calls == []  # Construction allocates only.
    assert channel.request("echo", {"value": 1}, timeout=5) == {"value": 1}
    assert channel.request("echo", [2], timeout=5) == [2]
    assert len(service.records) == 1
    channel.close()
    channel.close()
    assert channel.retired and service.transport_closed and service.calls.count(wire.OP_CLOSE) == 1


def test_lost_open_and_start_acknowledgments_never_launch_twice():
    service = FakeService()
    service.drop_once = {wire.OP_OPEN_TOP, wire.OP_START}
    channel = OwnerServiceChannel(service, 1)
    assert channel.request("echo", "x", timeout=5) == "x"
    assert len(service.leases) == 1 and len(service.records) == 1
    assert service.calls.count(wire.OP_START) == 2
    channel.close()


def test_stale_replies_are_skipped_by_nonce():
    service = FakeService()
    service.stray_before = {wire.OP_READ, wire.OP_WRITE}
    channel = OwnerServiceChannel(service, 1)
    assert channel.request("echo", "y", timeout=5) == "y"
    channel.close()


def test_partial_writes_deliver_the_whole_line():
    service = FakeService(accept_limit=3)
    channel = OwnerServiceChannel(service, 1)
    assert channel.request("echo", {"text": "a" * 50}, timeout=5) == {"text": "a" * 50}
    channel.close()


def test_input_event_is_acknowledged_after_the_owner_check():
    service = FakeService(behave={"press": "event"})
    channel = OwnerServiceChannel(service, 1)
    events = []
    assert channel.request("press", {}, timeout=5, on_event=events.append) == "acknowledged"
    assert events == [{"kind": "key_press"}]
    channel.close()


def test_helper_error_type_and_end_of_stream_retire_the_channel():
    service = FakeService(behave={"take": "busy"})
    channel = OwnerServiceChannel(service, 1)
    with pytest.raises(AgentControlBusy):
        channel.request("take", {}, timeout=5)
    assert channel.retired
    ending = FakeService(behave={"stop": "exit"})
    second = OwnerServiceChannel(ending, 1)
    with pytest.raises(AgentTaskError, match="closed its reply stream"):
        second.request("stop", {}, timeout=5)
    assert second.retired


def test_unavailable_service_refuses_and_still_retires_without_a_helper():
    service = FakeService(start_status=wire.STATUS_UNAVAILABLE)
    channel = OwnerServiceChannel(service, 1)
    with pytest.raises(AgentTaskError, match="unavailable"):
        channel.request("echo", {}, timeout=5)
    assert channel.retired and not service.records


def test_close_from_another_thread_stops_a_waiting_request():
    service = FakeService(behave={"hang": "silent"})
    channel = OwnerServiceChannel(service, 1)
    outcome = {}

    def wait_for_reply():
        try:
            outcome["result"] = channel.request("hang", {}, timeout=20)
        except AgentTaskError as error:
            outcome["error"] = error

    waiter = threading.Thread(target=wait_for_reply)
    waiter.start()
    time.sleep(0.2)
    started = time.monotonic()
    channel.close()
    waiter.join(timeout=5)
    assert not waiter.is_alive() and time.monotonic() - started < 5
    assert "result" not in outcome and "closed" in str(outcome["error"])
    assert channel.retired


def test_reply_read_after_close_began_is_not_delivered():
    service = FakeService()
    channel = OwnerServiceChannel(service, 1)
    closers = []

    def close_once_the_reply_is_buffered():
        if service.stdout and not closers:
            closer = threading.Thread(target=channel.close)
            closers.append(closer)
            closer.start()
            closer.join(timeout=5)

    with pytest.raises(AgentTaskError, match="closed"):
        channel.request("echo", "late", timeout=5, check=close_once_the_reply_is_buffered)
    assert closers and channel.retired


def test_unsettled_helper_keeps_the_channel_unretired_until_a_later_close():
    service = FakeService()
    service.settled = False
    channel = OwnerServiceChannel(service, 1)
    channel.request("echo", 1, timeout=5)
    with pytest.raises(AgentTaskError, match="not retired"):
        channel.close()
    assert not channel.retired and not service.transport_closed
    service.settled = True
    channel.close()
    assert channel.retired


def test_cancelled_request_retires_its_helper():
    service = FakeService()
    channel = OwnerServiceChannel(service, 1)
    channel.request("echo", 1, timeout=5)

    def cancelled():
        raise CancelledError()

    with pytest.raises(CancelledError):
        channel.request("echo", 2, timeout=5, check=cancelled)
    assert channel.retired
    with pytest.raises(AgentTaskError, match="retired"):
        channel.request("echo", 3, timeout=5)


def test_nested_channel_opens_a_child_lease_of_its_parent():
    service = FakeService()
    service.drop_once = {wire.OP_OPEN_CHILD}
    channel = OwnerServiceChannel(service, 2, parent=service.grant)
    assert channel.request("echo", "nested", timeout=5) == "nested"
    assert service.calls.count(wire.OP_OPEN_CHILD) == 2 and wire.OP_OPEN_TOP not in service.calls
    assert len(service.leases) == 1
    channel.close()
    assert channel.retired


def test_nested_channel_with_a_copied_or_wrong_capability_is_refused_and_retired():
    service = FakeService()
    forged = NestedGrant(service.grant.parent, bytes(32))
    channel = OwnerServiceChannel(service, 2, parent=forged)
    with pytest.raises(AgentTaskError, match="refused to open a lease"):
        channel.request("echo", 1, timeout=5)
    assert channel.retired and not service.leases
