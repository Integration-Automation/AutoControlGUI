"""A presence-only source actor; native observation stays on its dedicated helper thread."""
from __future__ import annotations

from dataclasses import dataclass, field
from contextlib import contextmanager
import queue
import threading
import time
from typing import Any, Callable, Iterator

from je_auto_control.utils.agent_runtime.errors import AgentControlBusy, AgentTaskError
from je_auto_control.utils.agent_runtime.models import positive
from je_auto_control.utils.agent_runtime.presence_state import PresenceState
from je_auto_control.utils.agent_runtime.presence_win32 import Win32PresenceAPI
from je_auto_control.utils.agent_runtime.presence_frames import presence_body as _body


@dataclass
class _Ticket:
    operation: str
    body: dict
    deadline: float
    reply: queue.Queue = field(default_factory=lambda: queue.Queue(maxsize=1), init=False)
    abandoned: threading.Event = field(default_factory=threading.Event, init=False)
    accepted: threading.Event = field(default_factory=threading.Event, init=False)
    lease: dict | None = field(default=None, init=False)


@dataclass
class _Lifecycle:
    ready: threading.Event = field(default_factory=threading.Event)
    stop: threading.Event = field(default_factory=threading.Event)
    started: bool = False
    closed: bool = False
    cleanup_failed: bool = False
    api: Any = field(default=None, init=False)


class WindowsPresenceSource:
    """Keep physical state independent of input helpers, with fresh bounded actor requests."""

    def __init__(self, api_factory: Callable[[], Any] | None = None,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self._api_factory = api_factory
        self._state = PresenceState(clock)
        self._mutex = threading.Lock()
        self._lifecycle = _Lifecycle()
        self._queue: queue.Queue[_Ticket] = queue.Queue(maxsize=16)
        self._pending: list[_Ticket] = []
        self._thread: threading.Thread | None = None

    @property
    def _ready(self) -> threading.Event:
        return self._lifecycle.ready

    @property
    def _stop(self) -> threading.Event:
        return self._lifecycle.stop

    def start(self) -> None:
        """Explicitly start the helper's observer; construction and inspection stay inert."""
        with self._mutex:
            if self._lifecycle.closed:
                raise AgentTaskError('physical presence source has retired')
            if self._thread is None:
                self._thread = threading.Thread(target=self._run, name='AgentPhysicalSource', daemon=True)
                self._thread.start()
            thread = self._thread
        if (not self._ready.wait(5) or not self._lifecycle.started or self._lifecycle.closed or not thread.is_alive()
                or self._state.inspect()['state'] == 'unavailable'):
            self.close()
            raise AgentTaskError('physical presence observer did not become ready')

    def _api(self) -> Any:
        if self._api_factory is not None:
            return self._api_factory()
        return Win32PresenceAPI()

    def _run(self) -> None:
        api = None
        try:
            if self._stop.is_set():
                return
            api = self._api()
            self._lifecycle.api = api
            if self._stop.is_set():
                return
            api.open(self._state.physical)
            while not self._stop.is_set():
                try:
                    self._state.refresh(*api.poll(0.05))
                except AgentControlBusy:
                    self._reject_queued(AgentControlBusy('physical presence input queue is still active'))
                    self._reap()
                    continue
                self._lifecycle.started = True
                self._ready.set()
                self._reap()
                self._serve(api)
        except (OSError, ValueError, TypeError, AttributeError, RuntimeError):
            self._state.fail()
        finally:
            self._state.close()
            if api is not None:
                self._retire_api(api)
            self._ready.set()
            self._reject_queued(AgentTaskError('physical presence source is unavailable'))

    def _retire_api(self, api: Any) -> None:
        try:
            api.close()
            self._lifecycle.api = None
        except (OSError, ValueError, TypeError, AttributeError, RuntimeError):
            self._lifecycle.cleanup_failed = True

    def _reject_queued(self, error: AgentTaskError) -> None:
        for _index in range(16):
            try:
                ticket = self._queue.get_nowait()
            except queue.Empty:
                return
            ticket.reply.put_nowait(error)

    def _dispatch(self, ticket: _Ticket) -> dict:
        if ticket.operation == 'inspect':
            return self._state.inspect()
        if ticket.operation == 'acquire':
            return self._state.acquire()
        if ticket.operation == 'check':
            return self._state.check(**ticket.body)
        self._state.release(**ticket.body)
        return {'released': True}

    def _fresh(self, api: Any, ticket: _Ticket) -> bool:
        try:
            self._state.refresh(*api.poll(0))
            return True
        except AgentControlBusy:
            ticket.reply.put_nowait(AgentControlBusy('physical presence input queue is still active'))
            return False
        except (OSError, ValueError, TypeError, AttributeError, RuntimeError):
            ticket.reply.put_nowait(AgentTaskError('physical presence observation is unavailable'))
            raise

    def _serve(self, api: Any) -> None:
        for _index in range(16):
            try:
                ticket = self._queue.get_nowait()
            except queue.Empty:
                return
            if self._expired(ticket):
                ticket.reply.put_nowait(AgentTaskError('physical presence request deadline exhausted'))
                continue
            if not self._fresh(api, ticket):
                continue
            if self._expired(ticket):
                ticket.reply.put_nowait(AgentTaskError('physical presence request deadline exhausted'))
                continue
            try:
                result: Any = self._dispatch(ticket)
            except AgentTaskError as error:
                result = error
            if ticket.operation == 'acquire' and isinstance(result, dict):
                ticket.lease = result
                self._pending.append(ticket)
            ticket.reply.put_nowait(result)

    def _expired(self, ticket: _Ticket) -> bool:
        return self._stop.is_set() or ticket.abandoned.is_set() or time.monotonic() >= ticket.deadline

    def _reap(self) -> None:
        retained = []
        for ticket in self._pending:
            if ticket.accepted.is_set():
                continue
            if ticket.abandoned.is_set() or time.monotonic() >= ticket.deadline:
                if ticket.lease is not None:
                    self._state.release(**ticket.lease)
            else:
                retained.append(ticket)
        self._pending = retained

    @contextmanager
    def _locked(self, deadline: float) -> Iterator[None]:
        if not self._mutex.acquire(timeout=max(0, deadline - time.monotonic())):
            raise AgentTaskError('physical presence request deadline exhausted')
        try:
            if time.monotonic() >= deadline:
                raise AgentTaskError('physical presence request deadline exhausted')
            yield
        finally:
            self._mutex.release()

    def _enqueue(self, operation: str, body: dict, deadline: float) -> _Ticket:
        with self._locked(deadline):
            if self._lifecycle.closed or self._thread is None or not self._thread.is_alive():
                raise AgentTaskError('physical presence source is unavailable')
            ticket = _Ticket(operation, body, deadline)
            try:
                self._queue.put_nowait(ticket)
            except queue.Full as error:
                raise AgentControlBusy('physical presence request capacity is busy') from error
            return ticket

    def request(self, operation: str, body: dict, timeout: float = 0.25) -> dict:
        """Apply one closed request after a fresh native poll, never a cached heartbeat alone."""
        positive(timeout, 'physical presence request deadline', 0.25)
        deadline = time.monotonic() + timeout
        body = _body(operation, body)
        if operation == 'inspect':
            with self._locked(deadline):
                if self._thread is None or self._lifecycle.closed:
                    return self._state.inspect()
        ticket = self._enqueue(operation, body, deadline)
        try:
            result = ticket.reply.get(timeout=max(0, ticket.deadline - time.monotonic()))
        except queue.Empty as error:
            ticket.abandoned.set()
            raise AgentTaskError('physical presence request deadline exhausted') from error
        if time.monotonic() >= ticket.deadline:
            ticket.abandoned.set()
            raise AgentTaskError('physical presence request deadline exhausted')
        if isinstance(result, AgentTaskError):
            raise result
        ticket.accepted.set()
        return result

    def status(self) -> dict:
        """Read passive availability only; this cannot authorize input or start native monitoring."""
        return self._state.inspect()

    def release(self, generation: str, lease_id: str) -> None:
        """Revoke a presence token without waiting for observation or releasing keyboard/mouse input."""
        self._state.release(generation, lease_id)

    def close(self) -> None:
        """Fence presence before bounded thread retirement; native failure remains an owned-helper concern."""
        with self._mutex:
            self._lifecycle.closed = True
            self._stop.set()
            self._state.close()
            thread = self._thread
        if thread is not None:
            thread.join(timeout=1)
            if thread.is_alive():
                raise AgentTaskError('physical presence observer has not retired')
        if self._lifecycle.cleanup_failed:
            raise AgentTaskError('physical presence native resources have not retired')
