"""Bind folder polling, cancellation and frozen receive receipts to one captured GUI owner."""
from __future__ import annotations
from concurrent.futures import CancelledError
from pathlib import Path
from typing import Callable, Optional, Protocol

from je_auto_control.utils.exception.control_signals import raise_caused_run_interruption
from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils.rbac.deferred import DeferredAuthorization
from je_auto_control.utils.remote_desktop.file_sync import FolderSyncEngine
from je_auto_control.utils.remote_desktop.file_receipts import FileReceiveReceipt


class _Viewer(Protocol):
    @property
    def authenticated(self) -> bool:
        """Whether this same viewer still owns an authenticated connection."""

    @property
    def connection_identity(self) -> object:
        """The opaque concrete peer to which this work was attached."""

    def send_file(self, local_path: str, remote_name: Optional[str] = None,
                  on_progress: Optional[Callable[[int, int], None]] = None, *,
                  cancelled: Optional[Callable[[], bool]] = None) -> None:
        """Send a file cooperatively under its owner's cancellation predicate."""

    def set_file_received_callback(self, callback: Callable[[Path], None]) -> None:
        """Attach the existing inert path/status listener."""

    def set_file_receipt_callback(self, callback: Callable[[FileReceiveReceipt], None]) -> None:
        """Attach the local received-content listener."""


def bind_folder_receipts(viewer: _Viewer, current_viewer: Callable[[], object],
                         current_engine: Callable[[], Optional[FolderSyncEngine]],
                         notify: Optional[Callable[[Path], None]] = None) -> None:
    """Route native receipts to the attached folder owner; delayed callbacks never adopt a replacement viewer."""
    engine = current_engine()

    def received(receipt: FileReceiveReceipt) -> None:
        if current_viewer() is viewer and engine is not None and current_engine() is engine:
            engine.record_receipt(receipt)

    def published(path: Path) -> None:
        if current_viewer() is viewer and notify is not None:
            notify(path)

    if engine is not None:
        viewer.set_file_receipt_callback(received)
    if notify is not None:
        viewer.set_file_received_callback(published)


def make_folder_engine(viewer: _Viewer, directory: str, current_viewer: Callable[[], object],
                       current_engine: Callable[[], Optional[FolderSyncEngine]]) -> FolderSyncEngine:
    """Create inert polling work; the caller attaches the returned engine before starting it."""
    authority = DeferredAuthorization.capture()
    with authority.scope():
        pass
    engine: FolderSyncEngine
    connection = viewer.connection_identity

    def cancelled() -> bool:
        if engine.stop_requested:
            return True
        if (current_viewer() is not viewer or current_engine() is not engine or not viewer.authenticated
                or viewer.connection_identity is not connection):
            engine.request_stop()
            return True
        try:
            with authority.scope():
                pass
        except (AutoControlException, OSError, ValueError) as error:
            raise_caused_run_interruption(error)
            engine.request_stop()
            return True
        return False

    def send(path: str, name: str) -> None:
        if cancelled():
            raise CancelledError()
        with authority.scope():
            viewer.send_file(path, remote_name=name, cancelled=cancelled)

    engine = FolderSyncEngine(watch_dir=Path(directory), sender=send, cancelled=cancelled)
    return engine
