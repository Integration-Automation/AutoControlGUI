"""Confirm native file publication with bounded authenticated probes and transfer/hash/size receipt matching."""
from __future__ import annotations

import asyncio
from _thread import LockType
import json
import secrets
import weakref
from concurrent.futures import Future, InvalidStateError, TimeoutError as FutureTimeoutError
from contextlib import contextmanager
from dataclasses import dataclass, field
from functools import partial
from threading import Lock, RLock
from time import monotonic
from typing import Any, Callable, Iterator, Optional, TypeGuard

from je_auto_control.utils.exception.control_signals import raise_caused_run_interruption
from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils.logging.logging_instance import autocontrol_logger
from je_auto_control.utils.remote_desktop.file_receipts import FileReceiveReceipt
from je_auto_control.utils.remote_desktop.webrtc_file_write import (
    _CANCELLED, _Channel, _PinnedBridge, _checkpoint, _on_bridge_thread, _send_confirmed, _try_send, _wait_result,
)

_PROBE_TIMEOUT_S = 2.0
_COMMIT_TIMEOUT_S = 5.0
_MAX_ENVELOPE = 4096


class FileCommitError(AutoControlException, RuntimeError):
    """A native peer cannot confirm the requested file publication."""


@dataclass
class _Probe:
    """One bounded outstanding capability request."""
    nonce: str = field(default_factory=lambda: secrets.token_hex(16))
    future: Future[bool] = field(default_factory=Future)


@dataclass
class _Commit:
    """Expected byte metadata and an unpredictable nonce for one publication wait."""
    transfer_id: str
    size: int
    nonce: str = field(default_factory=lambda: secrets.token_hex(16))
    digest: str = ''
    future: Future[bool] = field(default_factory=Future)


@dataclass
class _Inbound:
    """Capture one incoming end envelope independently from a later transfer."""
    transfer_id: str
    nonce: Optional[str] = None
    generation: int = 0


@dataclass
class _State:
    """Lock the ephemeral requests and generation of one channel."""
    lock: LockType = field(default_factory=Lock)
    closed: bool = False
    probe: Optional[_Probe] = None
    commit: Optional[_Commit] = None
    inbound: Optional[_Inbound] = None
    generation: int = 0


def _settle(future: Future[bool], error: Optional[BaseException] = None) -> None:
    try:
        if error is None:
            future.set_result(True)
        else:
            future.set_exception(error)
    except InvalidStateError:
        pass  # A timed-out/cancelled waiter already withdrew this claimed response.


def valid_hex(value: object, length: int) -> TypeGuard[str]:
    """Validate bounded lowercase protocol tokens without coercing booleans or arbitrary objects."""
    return isinstance(value, str) and len(value) == length and all(c in '0123456789abcdef' for c in value)


def valid_int(value: object) -> TypeGuard[int]:
    """Accept integer protocol fields while refusing bool and numeric coercion."""
    return isinstance(value, int) and not isinstance(value, bool)


def parse_envelope(message: object) -> Optional[dict[str, Any]]:
    """Bound native control envelopes before decoding; binary file chunks bypass this parser."""
    if not isinstance(message, str):
        return None
    try:
        if len(message) > _MAX_ENVELOPE or len(message.encode('utf-8')) > _MAX_ENVELOPE:
            raise FileCommitError('file envelope exceeds the protocol limit')
        envelope = json.loads(message)
    except ValueError as error:
        raise_caused_run_interruption(error)
        raise FileCommitError('invalid file envelope') from error
    if not isinstance(envelope, dict):
        raise FileCommitError('file envelope must be an object')
    if not isinstance(envelope.get('type'), str):
        raise FileCommitError('file message type must be a string')
    return envelope


def current_epoch() -> object:
    """Return the current native loop or the explicit synchronous-adapter epoch."""
    try:
        return asyncio.get_running_loop()
    except RuntimeError:
        return None


class FileCommitBinding:
    """Own bounded protocol state for one concrete channel, authentication predicate and event-loop epoch."""

    def __init__(self, channel: _Channel, active: Callable[[], bool]) -> None:
        self.channel = channel
        self._active = active
        self.state = _State()
        self.epoch = current_epoch()

    def usable(self, epoch: object, generation: Optional[int] = None) -> bool:
        """Refuse detached channels, revoked authentication and another loop before producing side effects."""
        with self.state.lock:
            valid = not self.state.closed and (generation is None or generation == self.state.generation)
        return valid and self.epoch is epoch and self._active()

    def invalidate(self, *, terminal: bool = False) -> None:
        """Withdraw pending requests without completing another channel's or transfer's receipt."""
        with self.state.lock:
            self.state.closed = self.state.closed or terminal
            self.state.generation += 1
            pending = [item.future for item in (self.state.probe, self.state.commit) if item is not None]
            self.state.probe = self.state.commit = self.state.inbound = None
        for future in pending:
            _settle(future, FileCommitError('file connection ownership ended before confirmation'))

    def control(self, envelope: dict[str, Any]) -> bool:
        """Consume only supported confirmation messages on the originally bound event loop."""
        handlers = {'file_probe': self._probe_request, 'file_support': self._probe_response,
                    'file_commit': self._commit_response}
        kind = envelope.get('type')
        if not isinstance(kind, str):
            raise FileCommitError('file message type must be a string')
        handler = handlers.get(kind)
        if handler is None:
            return False
        if self.usable(current_epoch()):
            handler(envelope)
        return True

    def observe(self, envelope: Optional[dict[str, Any]]) -> Optional[_Inbound]:
        """Capture only the strict incoming transfer's nonce; legacy transfers retain their original wire behavior."""
        if envelope is None:
            return None
        kind = envelope.get('type')
        with self.state.lock:
            if kind == 'file_begin':
                token = envelope.get('transfer_id')
                self.state.inbound = _Inbound(token, generation=self.state.generation) if (
                    envelope.get('commit') == 2 and valid_hex(token, 16)) else None
            elif kind == 'file_end':
                return self._end_inbound(envelope)
            elif kind == 'file_abort':
                self.state.inbound = None
        return None

    def _end_inbound(self, envelope: dict[str, Any]) -> Optional[_Inbound]:
        """Capture an incoming end while the caller holds the channel state lock."""
        incoming = self.state.inbound
        nonce = envelope.get('commit_nonce')
        if incoming is None or envelope.get('transfer_id') != incoming.transfer_id or not valid_hex(nonce, 32):
            return None
        self.state.inbound = None
        return _Inbound(incoming.transfer_id, nonce, incoming.generation)

    def published(self, receipt: FileReceiveReceipt, incoming: Optional[_Inbound]) -> None:
        """Acknowledge the exact received bytes only after the receiver has atomically published them."""
        if incoming is not None and incoming.nonce is not None and self.usable(current_epoch(), incoming.generation):
            self._send({'type': 'file_commit', 'transfer_id': incoming.transfer_id, 'nonce': incoming.nonce,
                        'sha256': receipt.sha256, 'size': receipt.size})

    def _send(self, envelope: dict[str, Any]) -> None:
        try:
            _try_send(self.channel, json.dumps(envelope), control=True)
        except (OSError, RuntimeError, ValueError) as error:
            raise_caused_run_interruption(error)
            autocontrol_logger.debug('file confirmation response unavailable: %r', error)

    def _probe_request(self, envelope: dict[str, Any]) -> None:
        nonce = envelope.get('nonce')
        version = envelope.get('version')
        if not valid_int(version) or version < 1 or not valid_hex(nonce, 32):
            raise FileCommitError('invalid file confirmation probe')
        self._send({'type': 'file_support', 'version': 2, 'nonce': nonce})

    def _probe_response(self, envelope: dict[str, Any]) -> None:
        with self.state.lock:
            probe = self.state.probe
            if self.state.closed or probe is None or envelope.get('nonce') != probe.nonce:
                return
            self.state.probe = None
        error = None if valid_int(envelope.get('version')) and envelope['version'] == 2 else FileCommitError(
            'peer does not support publication confirmation')
        _settle(probe.future, error)

    def _commit_response(self, envelope: dict[str, Any]) -> None:
        with self.state.lock:
            commit = self.state.commit
            if (self.state.closed or commit is None or envelope.get('transfer_id') != commit.transfer_id
                    or envelope.get('nonce') != commit.nonce):
                return
            self.state.commit = None
        valid = (bool(commit.digest) and envelope.get('sha256') == commit.digest
                 and valid_int(envelope.get('size')) and envelope['size'] == commit.size)
        _settle(commit.future, None if valid else FileCommitError('publication receipt does not match sent content'))


# Registry allocation can run cyclic GC and synchronously reenter weak-reference cleanup.
_bindings_lock = RLock()
_bindings: dict[int, weakref.ReferenceType[FileCommitBinding]] = {}


def _remove_binding(identifier: int, reference: weakref.ReferenceType[FileCommitBinding]) -> None:
    with _bindings_lock:
        if _bindings.get(identifier) is reference:
            _bindings.pop(identifier)


def bind_commit_channel(channel: _Channel, active: Callable[[], bool]) -> FileCommitBinding:
    """Register a weak binding; native event handlers, not a global registry, own the channel lifetime."""
    binding = FileCommitBinding(channel, active)
    with _bindings_lock:
        _bindings[id(channel)] = weakref.ref(binding, partial(_remove_binding, id(channel)))
    return binding


def _find_binding(channel: object) -> Optional[FileCommitBinding]:
    with _bindings_lock:
        reference = _bindings.get(id(channel))
        binding = reference() if reference is not None else None
    return binding if binding is not None and binding.channel is channel else None


def retire_commit_channel(channel: object, *, terminal: bool = False) -> None:
    """Invalidate only this channel's pending confirmations, safely from teardown/permission threads."""
    binding = _find_binding(channel)
    if binding is not None:
        binding.invalidate(terminal=terminal)


class ConfirmedPeer:
    """Probe an authenticated peer before reading source content and await a matching publication receipt."""

    def __init__(self, binding: FileCommitBinding, bridge: _PinnedBridge, cancelled: _CANCELLED) -> None:
        self.binding, self.bridge, self.cancelled = binding, bridge, cancelled
        with binding.state.lock:
            self._generation = binding.state.generation

    def guard(self) -> bool:
        """Validate the captured connection/epoch and preserve the caller's original cancellation."""
        _checkpoint(self.cancelled)
        self.bridge.validate()
        if not self.binding.usable(self.bridge.identity, self._generation):
            raise FileCommitError('file connection ownership ended')
        return False

    def probe(self) -> None:
        """Require a fresh bounded capability exchange before each confirmed file, including permission rechecks."""
        self.guard()
        if _on_bridge_thread(self.bridge):
            raise FileCommitError('confirmed file sends must run outside the bridge thread')
        probe = _Probe()
        with self.binding.state.lock:
            if self.binding.state.closed or self.binding.state.generation != self._generation:
                raise FileCommitError('file connection ownership ended')
            if self.binding.state.probe is not None:
                raise FileCommitError('file capability probe already pending')
            self.binding.state.probe = probe
        try:
            _send_confirmed(self.binding.channel, self.bridge,
                            json.dumps({'type': 'file_probe', 'version': 2, 'nonce': probe.nonce}),
                            cancelled=self.guard, timeout=_PROBE_TIMEOUT_S)
            _wait_result(probe.future, self.guard, monotonic() + _PROBE_TIMEOUT_S)
            self.guard()
        except FutureTimeoutError as error:
            raise FileCommitError('peer did not confirm publication receipt support') from error
        finally:
            with self.binding.state.lock:
                if self.binding.state.probe is probe:
                    self.binding.state.probe = None
            probe.future.cancel()

    @contextmanager
    def request(self, transfer_id: str, size: int) -> Iterator[CommitWait]:
        """Own one bounded outstanding publication receipt until completion, cancellation or timeout."""
        self.guard()
        pending = _Commit(transfer_id, size)
        with self.binding.state.lock:
            if self.binding.state.closed or self.binding.state.generation != self._generation:
                raise FileCommitError('file connection ownership ended')
            if self.binding.state.commit is not None:
                raise FileCommitError('file publication confirmation already pending')
            self.binding.state.commit = pending
        try:
            yield CommitWait(self, pending)
        finally:
            with self.binding.state.lock:
                if self.binding.state.commit is pending:
                    self.binding.state.commit = None
            pending.future.cancel()


class CommitWait:
    """Freeze expected content before sending the end nonce and wait for its exact acknowledged publication."""

    def __init__(self, peer: ConfirmedPeer, pending: _Commit) -> None:
        self._peer, self._pending = peer, pending

    def end_fields(self, digest: str) -> dict[str, str]:
        """Bind receipt validation to the exact bytes sent before exposing the unpredictable end nonce."""
        with self._peer.binding.state.lock:
            self._pending.digest = digest
        return {'sha256': digest, 'commit_nonce': self._pending.nonce}

    def wait(self) -> None:
        """A completed receipt wins late cancellation; an uncertain publication never becomes success."""
        try:
            _wait_result(self._pending.future, self._peer.guard, monotonic() + _COMMIT_TIMEOUT_S)
        except FutureTimeoutError as error:
            raise FileCommitError('peer publication confirmation timed out') from error


def confirmed_peer(channel: _Channel, bridge: _PinnedBridge, cancelled: _CANCELLED) -> ConfirmedPeer:
    """Require a native receipt listener before probing; never infer delivery support from queued writes."""
    binding = _find_binding(channel)
    if binding is None:
        raise FileCommitError('files channel has no native publication receipt listener')
    peer = ConfirmedPeer(binding, bridge, cancelled)
    peer.probe()
    return peer


@contextmanager
def commit_request(peer: Optional[ConfirmedPeer], transfer_id: str, size: int) -> Iterator[Optional[CommitWait]]:
    """Keep legacy manual sends available while confirmed sends own their matching receipt wait."""
    if peer is None:
        yield None
    else:
        with peer.request(transfer_id, size) as request:
            yield request
