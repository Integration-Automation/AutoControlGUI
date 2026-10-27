"""Fresh presence checks inside owned input helpers, with bounded callers and an independent watchdog."""
from __future__ import annotations

from dataclasses import dataclass, field
import queue
import threading
import time
from typing import Any, Callable

from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from je_auto_control.utils.agent_runtime.presence_frames import (
    decode_frame, encode_frame, presence_body, validate_response,
)
from je_auto_control.utils.agent_runtime.presence_handshake import client_handshake
from je_auto_control.utils.agent_runtime.presence_pipe_windows import WindowsPresencePipe
from je_auto_control.utils.agent_runtime.presence_security_windows import WindowsPresenceSecurity


@dataclass
class _Probe:
    deadline: float
    done: threading.Event = field(default_factory=threading.Event)


@dataclass
class _Transport:
    pipe: Any
    security: Any
    connection: Any = None
    peer: Any = None
    sequence: int = 1
    revision: int | None = None
    opening: bool = False


@dataclass
class _Lifetime:
    stop: threading.Event = field(default_factory=threading.Event)
    retired: threading.Event = field(default_factory=threading.Event)
    threads: list[threading.Thread] = field(default_factory=list)
    failure: BaseException | None = None
    started: bool = False
    closed: bool = False
    watch_deadline: float = 0.0


class PresenceReader:
    """One permanent lease binding; only its private I/O owner touches blocking native resources."""

    def __init__(self, binding: dict, takeover: Callable[[], None], *, pipe: Any = None,
                 security: Any = None) -> None:
        self._binding = presence_body('check', binding)
        self._takeover = takeover
        security = security if security is not None else WindowsPresenceSecurity()
        self._wire = _Transport(pipe if pipe is not None else WindowsPresencePipe(security), security)
        self._state = _Lifetime()
        self._state.retired.set()
        self._mutex = threading.RLock()
        self._probes: queue.Queue[_Probe] = queue.Queue(maxsize=16)

    @property
    def retired(self) -> bool:
        """Require actual local handle and thread retirement; a stop/deadline alone proves neither."""
        with self._mutex:
            return self._state.retired.is_set() and not any(thread.is_alive() for thread in self._state.threads)

    def _require(self) -> None:
        if self._state.stop.is_set() or self._state.failure is not None or self._state.closed:
            raise AgentTaskError('physical presence reader is unavailable; explicit resume is required')

    def _fail(self, error: BaseException) -> None:
        with self._mutex:
            first = self._state.failure is None and not self._state.closed
            self._state.failure = self._state.failure or error
            self._state.stop.set()
        if first:
            self._takeover()

    def ready(self) -> None:
        """Start once and freshly check the host capability within0.25seconds, never reacquiring it."""
        self._start()
        self._probe()

    def check(self) -> None:
        """Perform a new bounded check of the exact binding; cached watch results cannot grant input."""
        if not self._state.started:
            raise AgentTaskError('physical presence reader has not been bound')
        self._probe()

    def _start(self) -> None:
        with self._mutex:
            self._require()
            if self._state.started:
                return
            self._state.started = True
            self._state.watch_deadline = time.monotonic() + 0.25
            self._state.retired.clear()
            self._launch(self._run, 'PresenceReaderIO')
            self._launch(self._watch, 'PresenceReaderWatch')

    def _launch(self, target: Callable[[], None], name: str) -> None:
        thread = threading.Thread(target=target, name=name, daemon=True)
        self._state.threads.append(thread)
        try:
            thread.start()
        except (RuntimeError, OSError) as error:
            if thread.ident is None:
                self._state.threads.remove(thread)
                if not self._state.threads and not self._wire.opening:
                    self._state.retired.set()
            self._fail(error)
            raise AgentTaskError('physical presence reader thread could not start') from error

    def _probe(self, deadline: float | None = None) -> None:
        self._require()
        deadline = min(time.monotonic() + 0.25, deadline) if deadline is not None else time.monotonic() + 0.25
        probe = _Probe(deadline)
        try:
            self._probes.put_nowait(probe)
        except queue.Full as error:
            self._fail(error)
            raise AgentTaskError('physical presence reader capacity is busy') from error
        if not probe.done.wait(max(0.0, deadline - time.monotonic())) or time.monotonic() >= deadline:
            expired = AgentTaskError('physical presence reader deadline exhausted')
            self._fail(expired)
            raise expired
        self._require()

    def _watch(self) -> None:
        while not self._state.stop.wait(0.05):
            try:
                with self._mutex:
                    deadline = self._state.watch_deadline
                self._probe(deadline)
            except AgentTaskError:
                return

    def _ensure(self) -> None:
        if self._wire.connection is None:
            self._wire.opening = True
            self._wire.connection = self._wire.pipe.connect()
            self._wire.opening = False
            self._require()
            self._wire.opening = True
            generation, self._wire.peer = client_handshake(self._wire.connection, self._wire.security)
            self._wire.opening = False
            self._require()
            if generation != self._binding['generation']:
                raise AgentTaskError('physical presence reader source generation changed')

    def _query(self, probe: _Probe) -> None:
        self._require()
        if time.monotonic() >= probe.deadline:
            raise AgentTaskError('physical presence reader queued check expired')
        self._ensure()
        self._require()
        if not self._wire.peer.alive():
            raise AgentTaskError('physical presence reader source process has exited')
        sequence = self._wire.sequence
        self._wire.connection.send_bytes(encode_frame(
            {'request_id': sequence, 'operation': 'check', 'body': self._binding}))
        reply = decode_frame(self._wire.connection.recv_bytes(4096))
        validate_response(reply, 'check', sequence, self._binding['generation'])
        if not self._wire.peer.alive() or reply['status'] != 'ok':
            raise AgentTaskError('physical presence reader lease has been revoked')
        result = reply['result']
        if not result['interactive'] or result['state'] not in {'monitoring', 'waiting_idle'}:
            raise AgentTaskError('physical presence reader session is unavailable')
        with self._mutex:
            self._require()
            if time.monotonic() >= probe.deadline:
                raise AgentTaskError('physical presence reader reply arrived too late')
            if self._wire.revision is not None and result['revision'] != self._wire.revision:
                raise AgentTaskError('physical presence reader physical revision changed')
            self._wire.revision = result['revision']
            self._wire.sequence += 1
            self._state.watch_deadline = time.monotonic() + 0.25
            probe.done.set()

    def _run(self) -> None:
        try:
            while not self._state.stop.is_set():
                try:
                    probe = self._probes.get(timeout=0.01)
                except queue.Empty:
                    continue
                self._query(probe)
        except (OSError, EOFError, RuntimeError, ValueError, TypeError) as error:
            self._fail(error)
        finally:
            self._state.stop.set()
            self._retire()

    def _retire(self) -> None:
        for name in ('peer', 'connection'):
            resource = getattr(self._wire, name)
            if resource is not None:
                try:
                    resource.close()
                    setattr(self._wire, name, None)
                except (OSError, RuntimeError, ValueError, TypeError) as error:
                    self._fail(error)
        if self._wire.peer is None and self._wire.connection is None and not self._wire.opening:
            self._state.retired.set()

    def close(self) -> None:
        """Retire only reader resources under0.25seconds; the parent Job fences any blocked I/O."""
        deadline = time.monotonic() + 0.25
        with self._mutex:
            self._state.closed = True
            self._state.stop.set()
            if (not any(thread.is_alive() for thread in self._state.threads) and not self.retired
                    and (self._wire.peer is not None or self._wire.connection is not None)):
                self._launch(self._retire, 'PresenceReaderRetire')
            threads = tuple(self._state.threads)
        for thread in threads:
            thread.join(timeout=max(0.0, deadline - time.monotonic()))
        if not self.retired:
            raise AgentTaskError('physical presence reader retirement is unproven; owned helper must retire')
