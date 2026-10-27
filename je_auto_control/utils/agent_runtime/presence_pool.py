"""Host-only shared presence ownership; task cancellation never cancels another runtime's source."""
from __future__ import annotations

from concurrent.futures import CancelledError
from dataclasses import dataclass, field
import math
import queue
import sys
import threading
import time
from typing import Any, Callable

from je_auto_control.utils.agent_runtime.errors import AgentControlBusy, AgentTaskError
from je_auto_control.utils.agent_runtime.native_channel import OwnedChannel
from je_auto_control.utils.agent_runtime.presence_frames import (
    identifier, presence_body, unsigned, validate_response,
)


@dataclass(eq=False)
class _Reference:
    closed: threading.Event = field(default_factory=threading.Event)
    tokens: dict[str, Any] = field(default_factory=dict)


@dataclass(eq=False)
class _Ticket:
    owner: _Reference
    deadline: float
    reply: queue.Queue[Any] = field(default_factory=lambda: queue.Queue(maxsize=1))
    abandoned: threading.Event = field(default_factory=threading.Event)
    accepted: threading.Event = field(default_factory=threading.Event)


@dataclass
class _Grant:
    ticket: _Ticket
    binding: dict
    released: threading.Event = field(default_factory=threading.Event)


@dataclass
class _Owner:
    channel: Any = None
    generation: str | None = None
    thread: threading.Thread | None = None
    stop: threading.Event = field(default_factory=threading.Event)
    retired: threading.Event = field(default_factory=threading.Event)
    failure: BaseException | None = None
    constructing: bool = False


def _deadline(timeout: float) -> float:
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)):
        raise AgentTaskError('presence wait deadline must be numeric')
    if not 0 < timeout <= 3600 or not math.isfinite(timeout):
        raise AgentTaskError('presence wait deadline must be finite and positive')
    return time.monotonic() + timeout


class PresenceReference:
    """One host runtime's lifetime and presence capabilities; never serialized as model authority."""

    def __init__(self, pool: PresencePool, owner: _Reference) -> None:
        self._pool, self._owner = pool, owner

    @property
    def closed(self) -> bool:
        """Report this reference's permanent closure without touching a native source."""
        return self._owner.closed.is_set()

    @property
    def retired(self) -> bool:
        """Report actual shared process/thread retirement, never a native-input cleanup proof."""
        return self._pool.retired

    def status(self) -> dict:
        """Inspect this reference's shared source without creating resources or granting input."""
        return self._pool.status()

    def acquire(self, check: Callable[[], None], timeout: float) -> dict:
        """Wait within this caller's budget; cancellation abandons only this caller's grant."""
        return self._pool.acquire_reference(self._owner, check, timeout)

    def release(self, binding: dict) -> None:
        """Schedule negative-only retirement of a token issued to this exact reference."""
        self._pool.release_reference(self._owner, binding)

    def close(self) -> None:
        """Close this runtime's reference; only the last reference ends the shared source lifetime."""
        self._pool.close_reference(self._owner)


class PresencePool:
    """One lazy broker and I/O owner, shared independently of task helpers and caller cancellation."""

    def __init__(self, *, channel_factory: Callable[[list[str]], Any] = OwnedChannel) -> None:
        self._factory = channel_factory
        self._mutex = threading.RLock()
        self._references: set[_Reference] = set()
        self._tickets: queue.Queue[_Ticket] = queue.Queue(maxsize=16)
        self._owner = _Owner()
        self._owner.retired.set()

    @property
    def retired(self) -> bool:
        """True only with no unretired process/owner thread, not merely after a stop request."""
        thread = self._owner.thread
        return self._owner.retired.is_set() and (thread is None or not thread.is_alive())

    def status(self) -> dict:
        """Return passive connection availability, never an input permission or native evidence claim."""
        with self._mutex:
            if self._owner.stop.is_set() or self._owner.failure is not None:
                state = 'unavailable' if self._owner.failure is not None else 'closed'
            elif self._owner.thread is None:
                state = 'not_started'
            else:
                state = 'binding' if self._owner.generation is None else 'available'
            return {'state': state, 'references': sum(not ref.closed.is_set() for ref in self._references),
                    'native_evidence': 'not_recorded'}

    def reference(self) -> PresenceReference:
        """Allocate only local bookkeeping; no helper, pipe or observation starts here."""
        with self._mutex:
            self._check_owner()
            owner = _Reference()
            self._references.add(owner)
            return PresenceReference(self, owner)

    def _check_owner(self) -> None:
        if self._owner.stop.is_set() or self._owner.failure is not None:
            raise AgentTaskError('shared presence owner is unavailable')

    def _live(self, ticket: _Ticket) -> bool:
        return (not ticket.owner.closed.is_set() and not ticket.abandoned.is_set()
                and time.monotonic() < ticket.deadline)

    def acquire_reference(self, owner: _Reference, check: Callable[[], None], timeout: float) -> dict:
        """Queue a bounded ticket; caller checkpoints are never passed into the shared owned RPC."""
        ticket = _Ticket(owner, _deadline(timeout))
        check()
        try:
            with self._mutex:
                self._check_owner()
                if owner not in self._references or owner.closed.is_set():
                    raise AgentTaskError('presence reference has closed')
                try:
                    self._tickets.put_nowait(ticket)
                except queue.Full as error:
                    raise AgentControlBusy('shared presence admission is busy') from error
                self._start()
            return self._wait(ticket, check)
        except BaseException:
            ticket.abandoned.set()
            raise

    def _start(self) -> None:
        if self._owner.thread is None:
            self._owner.retired.clear()
            self._start_thread(self._run, 'PresenceOwner')

    def _start_thread(self, target: Callable[[], None], name: str) -> None:
        previous = self._owner.thread
        thread = threading.Thread(target=target, name=name, daemon=True)
        self._owner.thread = thread
        try:
            thread.start()
        except (RuntimeError, OSError) as error:
            self._owner.failure = error
            self._owner.stop.set()
            if thread.ident is None:
                self._owner.thread = previous
                if self._owner.channel is None and not self._owner.constructing:
                    self._owner.retired.set()
            raise AgentTaskError('shared presence thread could not start') from error

    def _wait(self, ticket: _Ticket, check: Callable[[], None]) -> dict:
        while True:
            check()
            self._check_owner()
            if ticket.owner.closed.is_set():
                raise AgentTaskError('presence reference closed while waiting')
            remaining = ticket.deadline - time.monotonic()
            if remaining <= 0:
                raise AgentTaskError('presence caller deadline exhausted')
            try:
                value = ticket.reply.get(timeout=min(0.01, remaining))
            except queue.Empty:
                continue
            if isinstance(value, BaseException):
                raise value
            check()
            with self._mutex:
                self._check_owner()
                if not self._live(ticket) or value.released.is_set():
                    raise AgentTaskError('presence caller lost its grant before acceptance')
                ticket.accepted.set()
                return dict(value.binding)

    def release_reference(self, owner: _Reference, binding: dict) -> None:
        """Mark only a recorded owned grant; the I/O owner performs its negative release."""
        binding = presence_body('release', binding)
        with self._mutex:
            grant = owner.tokens.get(binding['lease_id'])
            if grant is None or grant.binding != binding:
                raise AgentTaskError('presence token does not belong to this reference')
            grant.released.set()

    def close_reference(self, owner: _Reference) -> None:
        """Last-reference stop is observed by the shared RPC checkpoint, without waiting on its mutex."""
        with self._mutex:
            if not self._last_reference(owner):
                return
            thread = self._retirement_thread()
        if thread is not None:
            thread.join(timeout=3)
            if thread.is_alive():
                raise AgentTaskError('shared presence I/O owner has not retired')
        if not self.retired:
            raise AgentTaskError('shared presence process retirement is unproven')

    def _last_reference(self, owner: _Reference) -> bool:
        owner.closed.set()
        if not owner.tokens:
            self._references.discard(owner)
        if any(not ref.closed.is_set() for ref in self._references):
            return False
        self._owner.stop.set()
        return True

    def _retirement_thread(self) -> threading.Thread | None:
        thread = self._owner.thread
        if (thread is not None and not thread.is_alive() and not self.retired
                and self._owner.channel is not None):
            self._start_thread(self._retire, 'PresenceRetire')
        return self._owner.thread

    def _ensure(self) -> None:
        self._check_owner()
        if self._owner.channel is None:
            self._owner.constructing = True
            self._owner.channel = self._factory(
                [sys.executable, '-u', '-m', 'je_auto_control.utils.agent_runtime.presence_broker'])
            self._owner.constructing = False
        self._check_owner()
        if self._owner.generation is None:
            value = self._owner.channel.request('bootstrap', {}, timeout=15, check=self._check_owner)
            if value == {'ready': False, 'status': 'busy'} and value['ready'] is False:
                raise AgentControlBusy('shared presence source is not ready')
            if not isinstance(value, dict) or set(value) != {'ready', 'generation'} or value['ready'] is not True:
                raise AgentTaskError('shared presence bootstrap is invalid')
            self._owner.generation = identifier(value['generation'])

    def _rpc(self, operation: str, body: dict) -> dict:
        self._check_owner()
        generation = self._owner.generation
        if generation is None:
            raise AgentTaskError('shared presence source generation is unavailable')
        value = self._owner.channel.request(operation, body, timeout=3, check=self._check_owner)
        if not isinstance(value, dict):
            raise AgentTaskError('shared presence reply is invalid')
        sequence = unsigned(value.get('request_id'), (1 << 63) - 1, 1)
        return validate_response(value, operation, sequence, generation)

    def _execute(self, ticket: _Ticket) -> None:
        if not self._live(ticket):
            return
        self._ensure()
        if not self._live(ticket):
            return
        reply = self._rpc('acquire', {})
        if reply['status'] in {'busy', 'lease_lost'}:
            error = AgentControlBusy('presence requires fresh idle') if reply['status'] == 'busy' else (
                AgentTaskError('presence lease is unavailable'))
            ticket.reply.put_nowait(error)
            return
        if reply['status'] != 'ok':
            raise AgentTaskError('shared presence source was lost')
        grant = _Grant(ticket, dict(reply['result']))
        with self._mutex:
            ticket.owner.tokens[grant.binding['lease_id']] = grant
        if self._live(ticket):
            ticket.reply.put_nowait(grant)
        else:
            self._release(grant)

    def _release(self, grant: _Grant) -> None:
        grant.released.set()
        reply = self._rpc('release', grant.binding)
        if reply['status'] != 'ok':
            raise AgentTaskError('shared presence release is unconfirmed')
        with self._mutex:
            grant.ticket.owner.tokens.pop(grant.binding['lease_id'], None)

    def _reap(self) -> None:
        with self._mutex:
            grants = [grant for owner in self._references for grant in owner.tokens.values()]
            pending = [grant for grant in grants if self._needs_release(grant)]
            for grant in pending:
                grant.released.set()
        for grant in pending:
            self._release(grant)
        with self._mutex:
            self._references.difference_update(ref for ref in tuple(self._references)
                                              if ref.closed.is_set() and not ref.tokens)

    def _needs_release(self, grant: _Grant) -> bool:
        return (grant.released.is_set() or grant.ticket.owner.closed.is_set()
                or not grant.ticket.accepted.is_set() and not self._live(grant.ticket))

    def _run(self) -> None:
        try:
            self._loop()
        except (OSError, EOFError, ValueError, TypeError, RuntimeError, AgentTaskError, CancelledError) as error:
            self._owner.failure = error
            self._owner.stop.set()
        finally:
            if self._owner.failure is None:
                self._owner.failure = sys.exc_info()[1]
            self._retire()

    def _loop(self) -> None:
        while not self._owner.stop.is_set():
            self._reap()
            try:
                ticket = self._tickets.get(timeout=0.01)
            except queue.Empty:
                continue
            try:
                self._execute(ticket)
            except AgentControlBusy as error:
                ticket.reply.put_nowait(error)

    def _retire(self) -> None:
        self._owner.stop.set()
        try:
            if self._owner.channel is not None:
                self._owner.channel.close()
                if not self._owner.channel.retired:
                    raise AgentTaskError('shared presence helper has not retired')
                self._owner.channel = None
            if not self._owner.constructing:
                with self._mutex:
                    for reference in self._references:
                        reference.tokens.clear()
                    self._references.difference_update(ref for ref in tuple(self._references) if ref.closed.is_set())
                self._owner.retired.set()
        except (OSError, RuntimeError, ValueError, TypeError, AgentTaskError) as error:
            self._owner.failure = error


@dataclass
class _Registry:
    pool: PresencePool | None = None
    mutex: Any = field(default_factory=threading.RLock)


_SHARED = _Registry()


def shared_reference() -> PresenceReference:
    """Bind an explicit new runtime lifetime; never replace an owner whose retirement is unproven."""
    with _SHARED.mutex:
        current = _SHARED.pool
        if current is not None and current.status()['state'] in {'unavailable', 'closed'}:
            if not current.retired:
                raise AgentTaskError('previous shared presence owner has not retired')
            _SHARED.pool = None
        if _SHARED.pool is None:
            _SHARED.pool = PresencePool()
        return _SHARED.pool.reference()


def shared_status() -> dict:
    """Inspect the default host pool without creating a reference, broker or native observer."""
    with _SHARED.mutex:
        if _SHARED.pool is None:
            return {'state': 'not_started', 'references': 0, 'native_evidence': 'not_recorded'}
        return _SHARED.pool.status()
