"""Bind file receivers to one authenticated peer and channel, retiring partial bytes when ownership ends."""
from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional, Protocol

from je_auto_control.utils.remote_desktop.file_receipts import FileReceiveReceipt
from je_auto_control.utils.logging.logging_instance import autocontrol_logger
from je_auto_control.utils.remote_desktop.webrtc_file_commit import (
    FileCommitError, bind_commit_channel, current_epoch, parse_envelope, retire_commit_channel,
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
        try:
            envelope = parse_envelope(message)
            if envelope is not None and binding.control(envelope):
                return
            if envelope is not None and envelope.get('type') == 'file_begin' and not accept_begin():
                return
            confirmation = binding.observe(envelope)
        except FileCommitError as error:
            binding.invalidate(terminal=True)
            receiver.abort()
            autocontrol_logger.debug('file protocol refused frame: %s', error)
            return

        def receipt_done(receipt: FileReceiveReceipt) -> None:
            if active():
                binding.published(receipt, confirmation)
                if received is not None:
                    received(receipt)

        receiver.handle_message(message, on_done=done, on_receipt=receipt_done)

    @channel.on('close')
    def channel_closed() -> None:
        binding.invalidate(terminal=True)
        receiver.close()
