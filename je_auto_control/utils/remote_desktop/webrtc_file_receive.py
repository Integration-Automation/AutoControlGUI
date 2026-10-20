"""Bind file receivers to one authenticated peer and channel, retiring partial bytes when ownership ends."""
from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional, Protocol

from je_auto_control.utils.remote_desktop.file_receipts import FileReceiveReceipt


# pylint: disable-next=too-few-public-methods  # reason: binding only needs the structural event-registration operation
class _FileChannel(Protocol):
    def on(self, event: str) -> Callable[[Callable[..., None]], Callable[..., None]]:
        """Register a callback for one channel event."""


class _Receiver(Protocol):
    def handle_message(self, message: object, *, on_done: Callable[[Path], None],
                       on_receipt: Optional[Callable[[FileReceiveReceipt], None]] = None) -> None:
        """Consume a frame and notify only after complete publication."""

    def abort(self) -> None:
        """Discard partial bytes without closing the channel's receiving capability."""

    def close(self) -> None:
        """Permanently retire this receiver and its partial bytes."""


def close_file_receiver(receiver: Optional[_Receiver]) -> None:
    """Permanently close the receiver before connection teardown or replacement."""
    if receiver is not None:
        receiver.close()


def abort_file_receiver(receiver: Optional[_Receiver]) -> None:
    """Discard partial bytes after permission loss, allowing a later grant on the same channel."""
    if receiver is not None:
        receiver.abort()


def bind_file_receiver(channel: _FileChannel, receiver: _Receiver, active: Callable[[], bool],
                       completed: Callable[[Path], None],
                       accept_begin: Callable[[], bool] = lambda: True, *,
                       received: Optional[Callable[[FileReceiveReceipt], None]] = None) -> None:
    """Wire a fresh receiver; stale frames and close callbacks cannot affect a replacement transfer."""
    def done(path: Path) -> None:
        if active():
            completed(path)

    def receipt_done(receipt: FileReceiveReceipt) -> None:
        if active() and received is not None:
            received(receipt)

    @channel.on('message')
    def message_received(message: object) -> None:
        if not active():
            receiver.abort()
            return
        if isinstance(message, str) and 'file_begin' in message and not accept_begin():
            return
        receiver.handle_message(message, on_done=done, on_receipt=receipt_done)

    @channel.on('close')
    def channel_closed() -> None:
        receiver.close()
