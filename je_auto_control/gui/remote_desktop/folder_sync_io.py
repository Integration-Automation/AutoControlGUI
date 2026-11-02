"""Bind confirmed folder sends, cancellation and frozen receipts to one captured GUI owner."""
from __future__ import annotations
from concurrent.futures import CancelledError
from pathlib import Path
from typing import Callable, Optional, Protocol

from je_auto_control.utils.exception.control_signals import raise_caused_run_interruption
from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils.rbac.deferred import DeferredAuthorization
from je_auto_control.utils.remote_desktop.file_sync import FolderSyncCheckpoint, FolderSyncEngine
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
                  cancelled: Optional[Callable[[], bool]] = None, require_commit: bool = False) -> None:
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
                       current_engine: Callable[[], Optional[FolderSyncEngine]],
                       checkpoint: Optional[FolderSyncCheckpoint] = None) -> FolderSyncEngine:
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
            viewer.send_file(path, remote_name=name, cancelled=cancelled, require_commit=True)

    engine = FolderSyncEngine(watch_dir=Path(directory), sender=send, cancelled=cancelled, checkpoint=checkpoint)
    return engine


_OwnerKey = tuple[Path, tuple[object, ...], Optional[tuple[str, Optional[Path], Optional[str]]]]


def _owner_key(viewer: _Viewer, directory: str) -> _OwnerKey:
    """Use authenticated host metadata or this concrete connection; never retain a credential in the key."""
    fingerprint = getattr(viewer, 'host_fingerprint', None)
    peer: tuple[object, ...] = ('connection', id(viewer), id(viewer.connection_identity))
    if isinstance(fingerprint, str) and len(fingerprint) == 64 and all(c in '0123456789abcdef' for c in fingerprint):
        peer = ('host', fingerprint)
    context = DeferredAuthorization.capture().context
    principal: Optional[tuple[str, Optional[Path], Optional[str]]] = None
    if context is not None:
        store = Path(context.store_path).absolute() if context.store_path is not None else None
        principal = (context.user_id, store, context.role if store is None else None)
    return Path(directory).absolute(), peer, principal


class FolderSyncHistory:
    """Retain one stopped GUI baseline; explicit resume rebinds work to the same peer, root and local principal."""

    def __init__(self) -> None:
        self._engine: Optional[FolderSyncEngine] = None
        self._owner: Optional[_OwnerKey] = None

    def checkpoint(self, viewer: _Viewer, directory: str) -> Optional[FolderSyncCheckpoint]:
        """Reject a live old worker before considering a handoff; mismatched owners establish a fresh baseline."""
        if self._engine is None:
            return None
        checkpoint = self._engine.checkpoint()
        return checkpoint if viewer.authenticated and self._owner == _owner_key(viewer, directory) else None

    def remember(self, viewer: _Viewer, directory: str, engine: FolderSyncEngine) -> None:
        """Retain only successfully started work, without changing its captured sender or cancellation owner."""
        self._engine, self._owner = engine, _owner_key(viewer, directory)

    def forget(self) -> None:
        """Explicitly disabling sync resets its baseline but retains ownership of any retiring worker."""
        self._owner = None
