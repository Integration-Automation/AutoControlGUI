"""Notify native file path and frozen receipt listeners while preserving original interruption objects."""
from pathlib import Path
from typing import Callable, Optional, TypeVar

from je_auto_control.utils.exception.control_signals import raise_caused_run_interruption
from je_auto_control.utils.logging.logging_instance import autocontrol_logger
from je_auto_control.utils.remote_desktop.file_receipts import FileReceiveReceipt

ReceiptCallback = Callable[[FileReceiveReceipt], None]
_T = TypeVar('_T')


class FileReceiveCallbacks:
    """Own dynamic path/receipt listeners and optional host auditing for one native endpoint."""

    def __init__(self, audit: Optional[Callable[[Path], None]] = None) -> None:
        self.on_file: Optional[Callable[[Path], None]] = None
        self.on_receipt: Optional[ReceiptCallback] = None
        self._audit = audit

    def published(self, path: Path) -> None:
        """Audit and notify the current path listener after publication, containing ordinary callback failures."""
        _notify(self._audit, path, 'file audit')
        _notify(self.on_file, path, 'file done')

    def received(self, receipt: FileReceiveReceipt) -> None:
        """Notify the current receipt listener with the original received content fingerprint."""
        _notify(self.on_receipt, receipt, 'file receipt')


def _notify(callback: Optional[Callable[[_T], None]], value: _T, label: str) -> None:
    if callback is None:
        return
    try:
        callback(value)
    except (RuntimeError, OSError) as error:
        raise_caused_run_interruption(error)
        autocontrol_logger.debug('%s cb: %r', label, error)
