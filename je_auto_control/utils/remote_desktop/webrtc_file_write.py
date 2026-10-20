"""Bounded observable DataChannel writes preserve caller cancellation and serialize file producers."""
from __future__ import annotations
from concurrent.futures import CancelledError, Future, TimeoutError as FutureTimeoutError
from contextlib import contextmanager
from dataclasses import dataclass
from functools import partial
from threading import Event, Lock, current_thread
from time import monotonic
from typing import Callable, Iterator, Optional, Protocol

from je_auto_control.utils.exception.control_signals import is_run_interruption, raise_caused_run_interruption

_CANCELLED = Optional[Callable[[], bool]]
_BUFFER_LIMIT = 1024 * 1024
_WRITE_TIMEOUT_S = 5.0


@dataclass
class _Lease:
    channel: object
    released: bool = False
    pending_abort: Optional[Future[bool]] = None
    error: Optional[BaseException] = None


_active_lock = Lock()
_active_channels: dict[int, _Lease] = {}


# pylint: disable-next=too-few-public-methods  # reason: a channel needs only one structural write operation
class _Channel(Protocol):
    def send(self, message: str | bytes) -> None:
        """Accept one message on the channel's owning thread."""


# pylint: disable-next=too-few-public-methods  # reason: this adapter needs only thread-safe callback scheduling
class _Bridge(Protocol):
    def call_soon(self, callback: Callable[..., None], *args: object) -> None:
        """Schedule one callback on the owned event loop."""


class _PinnedBridge:
    def __init__(self, bridge: _Bridge) -> None:
        self._bridge = bridge
        start = getattr(bridge, 'start', None)
        if callable(start):
            start()
        self._epoch: object = getattr(bridge, '_loop', None)

    @property
    def identity(self) -> object:
        """Return the opaque captured loop epoch for native protocol ownership checks."""
        return self._epoch

    @property
    def _thread(self) -> object:
        if self._epoch is not None and getattr(self._bridge, '_loop', None) is not self._epoch:
            return None
        thread: object = getattr(self._bridge, '_thread', None)
        return thread

    def validate(self) -> None:
        """Refuse a stopped or replaced loop rather than starting a new epoch for an old transfer."""
        if self._epoch is not None and getattr(self._bridge, '_loop', None) is not self._epoch:
            raise RuntimeError('files bridge stopped or was replaced')

    def call_soon(self, callback: Callable[..., None], *args: object) -> None:
        """Schedule work only while the captured event-loop epoch remains current."""
        self.validate()
        self._bridge.call_soon(callback, *args)
        if self._epoch is None:
            self._epoch = getattr(self._bridge, '_loop', None)


def _checkpoint(cancelled: _CANCELLED) -> None:
    if cancelled is not None and cancelled():
        raise CancelledError()


@contextmanager
def _channel_transfer(channel: _Channel) -> Iterator[None]:
    identifier = id(channel)
    lease = _Lease(channel)
    with _active_lock:
        if identifier in _active_channels:
            raise RuntimeError('file transfer already in progress on this channel')
        _active_channels[identifier] = lease
    try:
        yield
    except BaseException as error:
        lease.error = error
        raise
    finally:
        with _active_lock:
            lease.released = True
        if _release_if_done(identifier, lease) and lease.pending_abort is not None:
            _check_cleanup(lease, lease.pending_abort)


def _release_if_done(identifier: int, lease: _Lease) -> bool:
    with _active_lock:
        ready = lease.pending_abort is None or lease.pending_abort.done()
        if _active_channels.get(identifier) is lease and lease.released and ready:
            _active_channels.pop(identifier)
            return True
    return False


def _check_cleanup(lease: _Lease, future: Future[bool]) -> None:
    if future.cancelled() or (lease.error is not None and is_run_interruption(lease.error)):
        return  # The original caller's interruption has priority over a cleanup interruption.
    error = future.exception()
    if error is not None:
        raise_caused_run_interruption(error)


def _pending_finished(identifier: int, lease: _Lease, future: Future[bool]) -> None:
    if _release_if_done(identifier, lease):
        _check_cleanup(lease, future)


def _retain_abort(channel: _Channel, future: Future[bool]) -> None:
    identifier = id(channel)
    with _active_lock:
        lease = _active_channels[identifier]
        lease.pending_abort = future
    future.add_done_callback(partial(_pending_finished, identifier, lease))


def _invoke(future: Future[bool], callback: Callable[[], bool], cancelled: _CANCELLED) -> None:
    if not future.set_running_or_notify_cancel():
        return
    try:
        _checkpoint(cancelled)
        result = callback()
    # pylint: disable-next=broad-exception-caught  # reason: Future.result forwards every callback failure
    except BaseException as error:  # reason: preserve callback signals on the result future
        future.set_exception(error)
    else:
        future.set_result(result)


def _on_bridge_thread(bridge: _Bridge) -> bool:
    return getattr(bridge, '_thread', None) is current_thread()


def _queued_result(bridge: _Bridge, callback: Callable[[], bool], cancelled: _CANCELLED,
                   deadline: float, retained: Optional[Callable[[Future[bool]], None]] = None) -> bool:
    _checkpoint(cancelled)
    if isinstance(bridge, _PinnedBridge):
        bridge.validate()
    if _on_bridge_thread(bridge):
        return callback()
    future: Future[bool] = Future()
    scheduled = False
    if retained is not None:
        retained(future)
    try:
        bridge.call_soon(_invoke, future, callback, cancelled)
        scheduled = True
        return _wait_result(future, cancelled, deadline)
    finally:
        # Cancel queued data writes; retain aborts until they execute before any replacement transfer.
        if retained is None or not scheduled:
            future.cancel()


def _wait_result(future: Future[bool], cancelled: _CANCELLED, deadline: float) -> bool:
    while not future.done():
        _checkpoint(cancelled)
        remaining = deadline - monotonic()
        if remaining <= 0:
            raise FutureTimeoutError('files channel write timed out')
        try:
            return future.result(timeout=min(.05, remaining))
        except FutureTimeoutError:
            if future.done():
                return future.result()
    return future.result()


def _try_send(channel: _Channel, message: str | bytes, control: bool = False) -> bool:
    state = getattr(channel, 'readyState', None)
    if state is not None and state != 'open':
        raise RuntimeError('files channel is not open')
    buffered = getattr(channel, 'bufferedAmount', 0)
    if isinstance(buffered, bool) or not isinstance(buffered, int) or buffered < 0:
        raise RuntimeError('files channel has an invalid buffered amount')
    size = len(message.encode('utf-8')) if isinstance(message, str) else len(message)
    if not control and buffered + size > _BUFFER_LIMIT:
        return False
    channel.send(message)
    return True


def _send_confirmed(channel: _Channel, bridge: _Bridge, message: str | bytes, *,
                    cancelled: _CANCELLED = None, timeout: Optional[float] = None, retain_abort: bool = False) -> None:
    deadline = monotonic() + (_WRITE_TIMEOUT_S if timeout is None else timeout)
    callback = partial(_try_send, channel, message, retain_abort)
    retained = partial(_retain_abort, channel) if retain_abort else None
    while True:
        if _queued_result(bridge, callback, cancelled, deadline, retained):
            return
        if _on_bridge_thread(bridge):
            raise RuntimeError('files channel is busy; retry this file outside the bridge thread')
        remaining = deadline - monotonic()
        if remaining <= 0:
            raise FutureTimeoutError('files channel buffer did not drain')
        Event().wait(min(.01, remaining))
