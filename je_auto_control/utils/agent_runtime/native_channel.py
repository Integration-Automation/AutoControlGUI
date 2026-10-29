"""Bounded JSON IPC to an owned helper, with cancellable writes, replies and retirement."""
from __future__ import annotations

import json
import os
import queue
import signal
import subprocess  # nosec B404  # reason: fixed host-owned helper argv; never model-provided or a shell
import sys
import threading
import time
import uuid
from typing import Any, Callable, Sequence

from je_auto_control.utils.agent_runtime.errors import AgentControlBusy, AgentTaskError, AgentHumanReview
from je_auto_control.utils.agent_runtime.wire_data import detached, positive
from je_auto_control.utils.exception.cancellation import cancellation_checkpoint

_PACKET_LIMIT = 1_100_000
_ERROR_TYPES = {"AgentControlBusy": AgentControlBusy, "AgentHumanReview": AgentHumanReview}


def classify_reply(reply: Any, request_id: str) -> tuple[bool, Any]:
    """Return ``(True, event)`` for an input announcement or ``(False, result)``; a helper error raises its type."""
    if not isinstance(reply, dict) or reply.get("id") != request_id:
        raise AgentTaskError("native helper returned an unexpected reply")
    if "event" in reply:
        return True, reply["event"]
    if "error" in reply:
        raise _ERROR_TYPES.get(str(reply.get("error_type")), AgentTaskError)(str(reply["error"]))
    return False, detached(reply.get("result"))


def require_event_owner(event: Any, callback: Callable[[dict], None] | None) -> None:
    """Refuse an input announcement that is malformed or that no caller agreed to handle."""
    if not isinstance(event, dict) or callback is None:
        raise AgentTaskError("native helper announced unexpected input")


class OwnedChannel:
    """One serial native RPC owner; late replies and expired generations cannot be reused.

    Request admission and retirement are separate: ``close`` never waits for the
    request lock, so another thread can stop a request that is waiting for its
    reply. The stop intent is monotone, and no reply is delivered once it is set.
    """

    def __init__(self, argv: Sequence[str], *, on_control: Callable[[str], None] | None = None) -> None:
        self._request_lock = threading.Lock()
        self._close_lock = threading.Lock()
        self._stop = threading.Event()
        self._replies: queue.Queue[Any] = queue.Queue(maxsize=32)
        self._outbound: queue.Queue[bytes] = queue.Queue(maxsize=2)
        self._retired = False
        self._job: Any = None
        self._on_control = on_control
        if sys.platform != "win32" and signal.getsignal(signal.SIGCHLD) == signal.SIG_IGN:
            # The kernel would reap the leader at once, and its group ID could be reused
            # before close signals it.
            raise AgentTaskError("native helper cannot be owned while SIGCHLD is ignored")
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0
        self._process = subprocess.Popen(  # nosec B603  # reason: trusted host factory supplies explicit argv
            list(argv), stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            bufsize=0, creationflags=flags, start_new_session=sys.platform != "win32")
        try:
            if sys.platform == "win32":
                from je_auto_control.utils.agent_runtime.native_job import NativeJob
                self._job = NativeJob(self._process)
            self._reader = threading.Thread(target=self._read, name="NativeReply", daemon=True)
            self._writer = threading.Thread(target=self._write, name="NativeRequest", daemon=True)
            self._reader.start()
            self._writer.start()
        except BaseException:  # reason: a failed start must retire only the just-created owned process
            self._stop_process()
            raise

    @property
    def retired(self) -> bool:
        """True only after the owned process has been reaped, not merely asked to stop."""
        return self._retired

    def _emit(self, value: Any) -> None:
        while not self._stop.is_set():
            try:
                self._replies.put(value, timeout=0.05)
                return
            except queue.Full:
                continue

    def _read(self) -> None:
        stream = self._process.stdout
        if stream is None:
            self._emit(AgentTaskError("native helper has no reply pipe"))
            return
        try:
            while not self._stop.is_set():
                line = stream.readline(_PACKET_LIMIT + 1)
                if not line:
                    raise AgentTaskError("native helper closed its reply pipe")
                if len(line) > _PACKET_LIMIT or not line.endswith(b"\n"):
                    raise AgentTaskError("native helper reply exceeds its bound")
                message = json.loads(line)
                if isinstance(message, dict) and "control" in message:
                    self._control(message["control"])
                else:
                    self._emit(message)
        except (OSError, ValueError) as error:
            self._emit(AgentTaskError(f"native helper protocol failed: {type(error).__name__}"))

    def _control(self, value: Any) -> None:
        if value != "physical_input" or self._on_control is None:
            raise AgentTaskError("unexpected native control notification")
        self._on_control(value)

    def _write(self) -> None:
        stream = self._process.stdin
        if stream is None:
            self._emit(AgentTaskError("native helper has no request pipe"))
            return
        try:
            while not self._stop.is_set():
                try:
                    packet = self._outbound.get(timeout=0.05)
                except queue.Empty:
                    continue
                offset = 0
                while offset < len(packet):
                    written = stream.write(packet[offset:])
                    if not written:
                        raise AgentTaskError("native helper request pipe stopped writing")
                    offset += written
                stream.flush()
        except (OSError, ValueError) as error:
            self._emit(AgentTaskError(f"native helper request failed: {type(error).__name__}"))

    def _send(self, value: Any) -> None:
        packet = json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8") + b"\n"
        if len(packet) > _PACKET_LIMIT:
            raise AgentTaskError("native helper request exceeds its bound")
        try:
            self._outbound.put_nowait(packet)
        except queue.Full as error:
            raise AgentTaskError("native helper request capacity is busy") from error

    def request(self, operation: str, payload: Any, *, timeout: float,
                check: Callable[[], None] = cancellation_checkpoint,
                on_event: Callable[[dict], None] | None = None) -> Any:
        """Validate one proposal, wait within its deadline, and reap on every failed operation."""
        positive(timeout, "native deadline", 3600)
        with self._request_lock:
            if self._retired or self._stop.is_set():
                raise AgentTaskError("native helper has retired")
            try:
                check()
                request_id = uuid.uuid4().hex
                self._send({"id": request_id, "operation": operation, "payload": detached(payload)})
                return self._receive(request_id, time.monotonic() + timeout, check, on_event, operation)
            except BaseException as primary:  # reason: every failed/cancelled RPC must retire its owned native process
                try:
                    self.close()
                except AgentTaskError as cleanup:
                    raise primary from cleanup
                raise

    def _receive(self, request_id: str, deadline: float, check: Callable[[], None],
                 on_event: Callable[[dict], None] | None, operation: str = "operation") -> Any:
        while time.monotonic() < deadline:
            self._fenced()
            check()
            try:
                reply = self._replies.get(timeout=0.05)
            except queue.Empty:
                continue
            self._fenced()
            if isinstance(reply, AgentTaskError):
                raise reply
            is_event, value = classify_reply(reply, request_id)
            if is_event:
                self._event(value, on_event, check)
                continue
            check()
            self._fenced()
            return value
        raise AgentTaskError(f"native helper {operation} deadline exhausted")

    def _fenced(self) -> None:
        """Refuse delivery once close has begun, even for a reply already queued."""
        if self._stop.is_set():
            raise AgentTaskError("native helper was closed while a request was waiting")

    def _event(self, event: Any, callback: Callable[[dict], None] | None, check: Callable[[], None]) -> None:
        require_event_owner(event, callback)
        check()
        callback(detached(event))
        self._fenced()
        self._send({"ack": True})

    def _stop_process(self) -> None:
        deadline = time.monotonic() + 3
        # Never poll/reap the POSIX leader before killing its owned group: the
        # unreaped child reserves that PID, preventing a signal to a reused ID.
        if sys.platform == "win32":
            if self._job is not None:
                self._job.close(timeout=max(0, deadline - time.monotonic()))
            else:
                self._process.kill()
        else:
            self._signal_owned_group()
        try:
            self._process.wait(timeout=max(0, deadline - time.monotonic()))
        except subprocess.TimeoutExpired as error:
            raise AgentTaskError("native helper has not retired") from error

    def _signal_owned_group(self) -> None:
        """Signal the helper's group only while its unreaped leader still holds the group ID."""
        waitid = getattr(os, "waitid", None)
        if waitid is not None:
            try:
                # Alive or a zombie, the leader keeps its PID, and with it the group ID.
                waitid(os.P_PID, self._process.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT)
            except ChildProcessError as error:
                raise AgentTaskError("native helper was reaped elsewhere; its group cannot be signalled "
                                     "safely") from error
        try:
            os.killpg(self._process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass

    def close(self) -> None:
        """Stop and reap only this owned tree before returning control to another task.

        Safe from any thread, including while another thread waits in ``request``;
        that request then fails instead of returning a reply.
        """
        self._stop.set()
        with self._close_lock:
            if self._retired:
                return
            self._stop_process()
            self._reader.join(timeout=1)
            self._writer.join(timeout=1)
            if self._reader.is_alive() or self._writer.is_alive():
                raise AgentTaskError("native helper pipe workers have not retired")
            for stream in (self._process.stdin, self._process.stdout):
                if stream is not None:
                    stream.close()
            self._retired = True
