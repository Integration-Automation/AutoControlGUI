"""Bounded, cancellable JSON transport for a process-owned native EI session."""
from __future__ import annotations

import atexit
from dataclasses import asdict, dataclass
import json
import math
import socket
import subprocess  # nosec B404  # reason: launches the fixed native helper without a shell
import sys
import tempfile
import threading
import time
from typing import Any, Callable, Mapping, Protocol, Sequence
from uuid import uuid4

from je_auto_control.linux_wayland.libei import LibeiOutOfBounds, LibeiUnavailable
from je_auto_control.linux_wayland.permission import WaylandDependencyRequired, WaylandPermissionRequired

MAX_MESSAGE_BYTES = 65536
MAX_BATCH_EVENTS = 128
INPUT_TIMEOUT = 3.0
CONNECT_TIMEOUT = 38.0
_ARITIES = {"press_key": 1, "release_key": 1, "press_button": 1, "release_button": 1,
            "set_position": 2, "scroll": 2}


class _Diagnostics(Protocol):
    """Common binary file contract for Unix files and Windows temporary wrappers."""

    def read(self, size: int = -1) -> bytes:
        """Read binary diagnostic output."""

    def seek(self, offset: int, whence: int = 0) -> int:
        """Locate a bounded tail of diagnostic output."""

    def close(self) -> None:
        """Release the temporary file."""


@dataclass
class _WorkerResources:
    """Process-owned resources and final diagnostics, released together."""

    process: subprocess.Popen[bytes] | None = None
    channel: socket.socket | None = None
    diagnostics: _Diagnostics | None = None
    crash_details: str = ""
    exit_code: int | None = None


class EiWorkerError(LibeiUnavailable):
    """The worker stopped or its result is uncertain; input must not be retried."""

    capability = "input"


class _PeerClosed(EiWorkerError):
    """The owner closed a complete-message boundary, ending the worker session."""


@dataclass(frozen=True)
class InputEvent:
    """One validated native input operation; arguments are signed 32-bit integers."""

    kind: str
    args: tuple[int, ...]

    def validate(self) -> None:
        """Reject malformed events before any of the batch can be emitted."""
        if not isinstance(self.kind, str) or self.kind not in _ARITIES or len(self.args) != _ARITIES[self.kind]:
            raise EiWorkerError("invalid EI input operation or argument count")
        _validate_arguments(self.args)
        _validate_native_range(self.kind, self.args)


def _validate_arguments(args: Sequence[int]) -> None:
    """Reject boolean/coerced or overflowing native integers."""
    if any(isinstance(value, bool) or not isinstance(value, int) or not -(2**31) <= value < 2**31 for value in args):
        raise EiWorkerError("EI input arguments must be signed 32-bit integers")


def _validate_native_range(kind: str, args: Sequence[int]) -> None:
    """Keep codes and converted scroll values in the native ABI range."""
    if kind not in ("set_position", "scroll") and not 0 <= args[0] <= 0xffff:
        raise EiWorkerError("invalid evdev key or button code")
    if kind == "scroll" and any(abs(value) > (2**31 - 1) // 120 for value in args):
        raise EiWorkerError("EI scroll exceeds the native discrete-scroll range")


@dataclass(frozen=True)
class InputAck:
    """A matching worker acknowledgement and measured total IPC round-trip time."""

    request_id: str
    applied: int
    elapsed_s: float


def _budget(timeout_s: float) -> float:
    try:
        value = float(timeout_s)
    except (TypeError, ValueError, OverflowError) as error:
        raise EiWorkerError("invalid EI timeout") from error
    if not math.isfinite(value) or value <= 0 or value > 120:
        raise EiWorkerError("EI timeout must be finite and between 0 and 120 seconds")
    return value


def _read_exact(channel: socket.socket, size: int, deadline: float | None) -> bytes:
    parts = bytearray()
    while len(parts) < size:
        if deadline is not None:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("EI worker timed out reading a message")
            channel.settimeout(remaining)
        chunk = channel.recv(size - len(parts))
        if not chunk:
            if not parts:
                raise _PeerClosed("EI worker closed its channel")
            raise EiWorkerError("EI worker closed its channel")
        parts.extend(chunk)
    return bytes(parts)


def read_message(channel: socket.socket) -> dict[str, Any]:
    """Read a size-limited JSON object; no pickle or executable wire content."""
    timeout = channel.gettimeout()
    deadline = None if timeout is None else time.monotonic() + timeout
    size = int.from_bytes(_read_exact(channel, 4, deadline), "big")
    if not 0 < size <= MAX_MESSAGE_BYTES:
        raise EiWorkerError("invalid EI message size")
    try:
        value = json.loads(_read_exact(channel, size, deadline))
    except (ValueError, UnicodeError, RecursionError) as error:
        raise EiWorkerError("invalid EI JSON message") from error
    if not isinstance(value, dict):
        raise EiWorkerError("EI message must be an object")
    return value


def write_message(channel: socket.socket, message: Mapping[str, object]) -> None:
    """Send one bounded JSON envelope over the private worker channel."""
    try:
        data = json.dumps(message, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError, RecursionError) as error:
        raise EiWorkerError("invalid EI JSON message") from error
    if not 0 < len(data) <= MAX_MESSAGE_BYTES:
        raise EiWorkerError("invalid EI message size")
    channel.sendall(len(data).to_bytes(4, "big") + data)


def open_worker_channel(descriptor: str) -> socket.socket:
    """Open an inherited Unix socket or an explicitly shared Windows socket."""
    if descriptor != "shared":
        return socket.socket(fileno=int(descriptor))
    if sys.platform == "win32":
        size = int.from_bytes(sys.stdin.buffer.read(4), "big")
        if not 0 < size <= 1024:
            raise EiWorkerError("invalid shared socket size")
        return socket.fromshare(sys.stdin.buffer.read(size))
    raise EiWorkerError("shared sockets are only used by Windows offline tests")


def _spawn_process(peer: socket.socket, argv: Sequence[str], stderr: Any = None) -> subprocess.Popen[bytes]:
    """Pass only the worker socket, without inheriting unrelated Windows handles."""
    if sys.platform != "win32":
        return subprocess.Popen(  # nosec B603  # reason: fixed helper argv, shell disabled, private socket fd only
            [*argv, str(peer.fileno())], pass_fds=(peer.fileno(),),
            stdout=subprocess.DEVNULL, stderr=stderr,
        )
    # pylint: disable-next=consider-using-with  # reason: client owns process across requests and reaps it in close
    process = subprocess.Popen(  # nosec B603  # reason: fixed helper argv, shell disabled, socket shared to child PID
        [*argv, "shared"], stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=stderr,
    )
    try:
        shared = peer.share(process.pid)
        if process.stdin is None:
            raise EiWorkerError("EI worker has no socket bootstrap channel")
        process.stdin.write(len(shared).to_bytes(4, "big") + shared)
        process.stdin.close()
    except (OSError, EiWorkerError):
        process.kill()
        process.wait(timeout=3)
        raise
    return process


class EiWorkerClient:
    """Own a helper and its channel; never call native session code in the parent.

    A timeout/crash revokes the connection, reaps the process and refuses all
    subsequent sends. Explicitly create a new client to retry authorization.
    ``process_factory`` supplies controlled subprocesses for offline tests.
    """

    def __init__(self, *, process_factory: Callable[[socket.socket], subprocess.Popen[bytes]] | None = None) -> None:
        self._factory = process_factory
        self._resources = _WorkerResources()
        self._lock = threading.Lock()
        self._lifecycle_lock = threading.RLock()
        self._connected = False
        self._closed = False
        self._failure = "input has not been authorized"
        atexit.register(self.close)

    @property
    def crash_details(self) -> str:
        """Return the bounded faulthandler tail retained after worker exit."""
        return self._resources.crash_details

    @property
    def worker_exit_code(self) -> int | None:
        """Return the final child exit status after cleanup."""
        return self._resources.exit_code

    @property
    def worker_running(self) -> bool:
        """Whether this client owns a live process (without native dispatch)."""
        process = self._resources.process
        return process is not None and process.poll() is None

    @property
    def open_channel(self) -> bool:
        """Whether a private socket is still owned by this client."""
        return self._resources.channel is not None

    @property
    def is_connected(self) -> bool:
        """Return cached authorization and worker liveness without injecting input."""
        return self._connected and not self._closed and self.worker_running

    @property
    def permission_status(self) -> tuple[str, str]:
        """Return passive state for the shared capability diagnostics."""
        return ("available", "authorized process-owned EI session") if self.is_connected else (
            "needs_permission", self._failure,
        )

    def _start(self) -> None:
        """Create exactly one helper while holding the cancellation boundary."""
        with self._lifecycle_lock:
            if self._closed:
                raise EiWorkerError("EI worker is closed; explicitly retry authorization")
            if self._resources.process is not None:
                return
            parent, peer = socket.socketpair()
            try:
                self._resources.diagnostics = tempfile.TemporaryFile()
                self._resources.process = self._factory(peer) if self._factory else _spawn_process(
                    peer, [sys.executable, "-m", "je_auto_control.linux_wayland.ei_worker"],
                    self._resources.diagnostics,
                )
                self._resources.channel = parent
            except (OSError, ValueError):
                parent.close()
                self.close()
                raise
            finally:
                peer.close()

    def _request(self, operation: str, payload: Mapping[str, object], timeout_s: float) -> dict[str, Any]:
        timeout = _budget(timeout_s)
        deadline = time.monotonic() + timeout
        # pylint: disable-next=consider-using-with  # reason: timed acquire has no context form; finally releases it
        if not self._lock.acquire(timeout=timeout):
            raise EiWorkerError("EI worker request timed out waiting for another request")
        try:
            self._start()
            channel = self._resources.channel
            if channel is None:
                raise EiWorkerError("EI worker channel is closed")
            request_id = uuid4().hex
            channel.settimeout(max(0.001, deadline - time.monotonic()))
            write_message(channel, {**payload, "operation": operation, "request_id": request_id})
            channel.settimeout(max(0.001, deadline - time.monotonic()))
            reply = read_message(channel)
            if reply.get("request_id") != request_id:
                raise EiWorkerError("EI worker reply has the wrong request identity")
            self._check_error(reply)
            return reply
        except TimeoutError as error:
            self._failure = "EI worker timed out; delivery is uncertain; explicitly retry authorization"
            self.close()
            raise EiWorkerError(self._failure) from error
        except (OSError, ValueError, EiWorkerError) as error:
            self._failure = str(error) if isinstance(error, EiWorkerError) else "EI worker connection failed"
            self.close()
            raise EiWorkerError(self._failure) from error
        except (WaylandPermissionRequired, WaylandDependencyRequired, LibeiOutOfBounds):
            self.close()
            raise
        finally:
            self._lock.release()

    def _check_error(self, reply: Mapping[str, Any]) -> None:
        """Preserve dependency, grant and coordinate refusals across the IPC boundary."""
        kind = reply.get("error")
        if not kind:
            return
        reason = str(reply.get("reason", "EI worker refused input"))[:2048]
        self._failure = reason
        if kind == "dependency":
            raise WaylandDependencyRequired(reason)
        if kind == "permission":
            raise WaylandPermissionRequired("input", reason)
        if kind == "bounds":
            raise LibeiOutOfBounds(reason)
        raise EiWorkerError(reason)

    def connect(self, *, timeout: float = CONNECT_TIMEOUT, socket_path: bytes | None = None) -> None:
        """Authorize and complete the EI handshake within a total wall-clock budget."""
        if self.is_connected:
            return
        _budget(timeout)
        payload: dict[str, object] = {"timeout_s": timeout}
        if socket_path is not None:
            payload["socket_path"] = socket_path.decode("utf-8")
        self._request("connect", payload, timeout)
        with self._lifecycle_lock:
            if self._closed:
                raise EiWorkerError("EI worker was canceled during authorization")
            self._connected = True

    def send(self, batch: Sequence[InputEvent], *, timeout_s: float) -> InputAck:
        """Validate a bounded batch before emission; never replay an uncertain batch."""
        _budget(timeout_s)
        if not 0 < len(batch) <= MAX_BATCH_EVENTS:
            raise EiWorkerError("EI batch must contain between 1 and 128 events")
        for event in batch:
            event.validate()
        if not self.is_connected:
            self.close()
            raise EiWorkerError("EI worker is not connected; explicitly retry authorization")
        started = time.monotonic()
        reply = self._request("send", {"events": [asdict(event) for event in batch]}, timeout_s)
        applied = reply.get("applied")
        if isinstance(applied, bool) or not isinstance(applied, int) or applied != len(batch):
            self.close()
            raise EiWorkerError("EI worker acknowledged an incomplete batch")
        return InputAck(str(reply["request_id"]), applied, time.monotonic() - started)

    def check_permission(self) -> None:
        """Dispatch revocations inside the worker before CLI text or native input."""
        if not self.is_connected:
            raise EiWorkerError("EI worker is not connected")
        self._request("permission", {}, INPUT_TIMEOUT)

    def press_key(self, keycode: int) -> None:
        """Send one evdev key down."""
        self.send([InputEvent("press_key", (keycode,))], timeout_s=INPUT_TIMEOUT)

    def release_key(self, keycode: int) -> None:
        """Send one evdev key up."""
        self.send([InputEvent("release_key", (keycode,))], timeout_s=INPUT_TIMEOUT)

    def press_button(self, button_code: int) -> None:
        """Send one evdev button down."""
        self.send([InputEvent("press_button", (button_code,))], timeout_s=INPUT_TIMEOUT)

    def release_button(self, button_code: int) -> None:
        """Send one evdev button up."""
        self.send([InputEvent("release_button", (button_code,))], timeout_s=INPUT_TIMEOUT)

    def click_button(self, button_code: int) -> None:
        """Press and release one button in a single bounded request."""
        self.send([InputEvent("press_button", (button_code,)), InputEvent("release_button", (button_code,))],
                  timeout_s=INPUT_TIMEOUT)

    def set_position(self, x: int, y: int) -> None:
        """Send an absolute layout coordinate for native region validation."""
        self.send([InputEvent("set_position", (x, y))], timeout_s=INPUT_TIMEOUT)

    def scroll(self, dx: int, dy: int) -> None:
        """Send signed wheel-click counts; native conversion remains in the worker."""
        self.send([InputEvent("scroll", (dx, dy))], timeout_s=INPUT_TIMEOUT)

    def disconnect(self) -> None:
        """Close this session; a new client is required for a new authorization."""
        self.close()

    def close(self) -> None:
        """Cancel in-flight IPC, revoke the native connection and reap the worker."""
        with self._lifecycle_lock:
            if self._closed:
                return
            self._closed = True
            self._connected = False
            channel, self._resources.channel = self._resources.channel, None
            if channel is not None:
                try:
                    channel.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                channel.close()
            process = self._resources.process
            if process is not None:
                try:
                    process.wait(timeout=0.5)
                except subprocess.TimeoutExpired:
                    process.terminate()
                    try:
                        process.wait(timeout=0.5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=3)
                self._resources.exit_code = process.returncode
                self._resources.process = None
            diagnostics, self._resources.diagnostics = self._resources.diagnostics, None
            if diagnostics is not None:
                try:
                    size = diagnostics.seek(0, 2)
                    diagnostics.seek(max(0, size - 16384))
                    self._resources.crash_details = diagnostics.read().decode("utf-8", errors="replace")
                finally:
                    diagnostics.close()
            atexit.unregister(self.close)
