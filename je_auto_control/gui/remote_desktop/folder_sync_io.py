"""Bind folder polling and chunk cancellation to one viewer, engine and captured GUI owner."""
from __future__ import annotations
from concurrent.futures import CancelledError
from pathlib import Path
from typing import Callable, Optional, Protocol

from je_auto_control.utils.exception.control_signals import raise_caused_run_interruption
from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils.rbac.deferred import DeferredAuthorization
from je_auto_control.utils.remote_desktop.file_sync import FolderSyncEngine


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
