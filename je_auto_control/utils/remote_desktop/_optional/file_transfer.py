"""Resolve the file transfer optional group as one outcome."""
from __future__ import annotations

from typing import TYPE_CHECKING as _TYPE_CHECKING


if _TYPE_CHECKING:
    from je_auto_control.utils.remote_desktop.webrtc_files import (
        FileTransferError as _FileTransferError,
        FileTransferReceiver as _FileTransferReceiver,
        FileTransferSender as _FileTransferSender,
    )


def _load() -> tuple[
    type[_FileTransferSender] | None,
    type[_FileTransferReceiver] | None,
    type[_FileTransferError] | None,
]:
    try:
        from je_auto_control.utils.remote_desktop.webrtc_files import (
            FileTransferError, FileTransferReceiver, FileTransferSender,
        )
    except ImportError:
        return (None, None, None)
    return (FileTransferSender, FileTransferReceiver, FileTransferError)


FileTransferSender, FileTransferReceiver, FileTransferWebRTCError = _load()
