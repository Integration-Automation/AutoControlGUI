"""Bind file receivers to one authenticated peer and channel, retiring partial bytes when ownership ends."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Optional, Protocol

from je_auto_control.utils.remote_desktop.file_receipts import FileReceiveReceipt
from je_auto_control.utils.logging.logging_instance import autocontrol_logger
from je_auto_control.utils.remote_desktop.webrtc_file_commit import (
    FileCommitBinding, FileCommitError, bind_commit_channel, current_epoch, parse_envelope, retire_commit_channel,
)


class _FileChannel(Protocol):
    def on(self, event: str) -> Callable[[Callable[..., None]], Callable[..., None]]:
        """Register a callback for one channel event."""

    def send(self, message: str | bytes) -> None:
        """Send one native frame on the bound event loop."""


class _Receiver(Protocol):
    def handle_message(self, message: object, *, on_done: Callable[[Path], None],
                       on_receipt: Optional[Callable[[FileReceiveReceipt], None]] = None) -> None:
        """Consume a frame and notify only after complete publication."""

    def abort(self) -> None:
        """Discard partial bytes without closing the channel's receiving capability."""

    def close(self) -> None:
        """Permanently retire this receiver and its partial bytes."""


def close_file_receiver(receiver: Optional[_Receiver], channel: object = None) -> None:
    """Permanently close the receiver before connection teardown or replacement."""
    retire_commit_channel(channel, terminal=True)
    if receiver is not None:
        receiver.close()


def abort_file_receiver(receiver: Optional[_Receiver], channel: object = None) -> None:
    """Discard partial bytes after permission loss, allowing a later grant on the same channel."""
    retire_commit_channel(channel)
    if receiver is not None:
        receiver.abort()


def _admit_frame(binding: FileCommitBinding, receiver: _Receiver, message: object,
                 accept_begin: Callable[[], bool]) -> tuple[bool, Any]:
    """Return whether the commit protocol consumed the frame, and the confirmation for a data frame."""
    try:
        envelope = parse_envelope(message)
        if envelope is not None and binding.control(envelope):
            return True, None
        if envelope is not None and envelope.get('type') == 'file_begin' and not accept_begin():
            return True, None
        return False, binding.observe(envelope)
    except FileCommitError as error:
        binding.invalidate(terminal=True)
        receiver.abort()
        autocontrol_logger.debug('file protocol refused frame: %s', error)
        return True, None


def _receipt_callback(binding: FileCommitBinding, active: Callable[[], bool], confirmation: Any,
                      received: Optional[Callable[[FileReceiveReceipt], None]],
                      ) -> Callable[[FileReceiveReceipt], None]:
    def receipt_done(receipt: FileReceiveReceipt) -> None:
        if active():
            binding.published(receipt, confirmation)
            if received is not None:
                received(receipt)
    return receipt_done


def bind_file_receiver(channel: _FileChannel, receiver: _Receiver, active: Callable[[], bool],
                       completed: Callable[[Path], None],
                       accept_begin: Callable[[], bool] = lambda: True, *,
                       received: Optional[Callable[[FileReceiveReceipt], None]] = None) -> None:
    """Wire a fresh receiver; stale frames and close callbacks cannot affect a replacement transfer."""
    binding = bind_commit_channel(channel, active)

    def done(path: Path) -> None:
        if active():
            completed(path)

    @channel.on('message')
    def message_received(message: object) -> None:
        if not binding.usable(current_epoch()):
            binding.invalidate()
            receiver.abort()
            return
        consumed, confirmation = _admit_frame(binding, receiver, message, accept_begin)
        if not consumed:
            receiver.handle_message(message, on_done=done,
                                    on_receipt=_receipt_callback(binding, active, confirmation, received))

    @channel.on('close')
    def channel_closed() -> None:
        binding.invalidate(terminal=True)
        receiver.close()
