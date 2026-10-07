"""Qt-owned connection presentation with headless, session-bound native work."""
from __future__ import annotations

from functools import partial
from typing import Callable, Protocol
import weakref

from PySide6.QtCore import QObject
from PySide6.QtWidgets import QMessageBox, QWidget

from je_auto_control.gui._panel_tasks import PanelTasks
from je_auto_control.gui._task_state import TaskError, TaskResult
from je_auto_control.gui.remote_desktop._task_work import connect_owned
from je_auto_control.gui.remote_desktop.session_owner import PanelSessions
from je_auto_control.utils.remote_desktop.sessions import RemoteSession


class Connectable(Protocol):  # pylint: disable=too-few-public-methods  # reason: one native connect seam
    """Native connection with an explicitly bounded timeout."""
    def connect(self, timeout: float) -> None:
        """Connect within the worker's bounded request timeout."""


def _start_native(start: Callable[[], object], _timeout: float) -> object:
    return start()


class ConnectionTasks(QObject):
    """Snapshot the owned session before starting; completion never selects a new session."""

    def __init__(self, owner: QWidget, sessions: PanelSessions) -> None:
        super().__init__(owner)
        self._owner = weakref.ref(owner)
        self._sessions = sessions
        self._tasks = {role: PanelTasks(owner, timeout_s=60) for role in ('host', 'viewer')}

    def connect(self, viewer: Connectable, ready: Callable[[], None]) -> None:
        """Start the native attempt with copied inputs, not a widget callback on the worker."""
        self._submit(viewer.connect, 'viewer', ready)

    def start(self, start: Callable[[], object], ready: Callable[[], None]) -> None:
        """Start an already allocated owned host off Qt."""
        self._submit(partial(_start_native, start), 'host', ready)

    def _submit(self, native: Callable[[float], object], role: str, ready: Callable[[], None]) -> None:
        identifier = self._sessions.id(role)
        if identifier is None:
            return
        directory = self._sessions.directory
        session = directory.get_session(identifier, owner=self._sessions.owner)
        tasks = self._tasks[role]
        tasks.submit(partial(connect_owned, directory, session, native), partial(self._ready, session, ready))
        if tasks.handle is not None:
            tasks.handle.failed.connect(self._failed)

    def _ready(self, session: RemoteSession, ready: Callable[[], None], _result: TaskResult) -> None:
        if self._sessions.directory.session_is_current(session.id, session.generation, owner=session.owner):
            ready()

    def _failed(self, error: TaskError) -> None:
        owner = self._owner()
        if owner is not None:
            QMessageBox.warning(owner, 'Remote Desktop', error.message)

    def cancel(self, role: str | None = None) -> None:
        """Cancel delivery before panel/session revocation."""
        for name, tasks in self._tasks.items():
            if role is None or name == role:
                tasks.cancel()
