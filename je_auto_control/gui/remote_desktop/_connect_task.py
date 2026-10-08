"""Connect a remote-desktop viewer without holding the GUI thread.

``viewer.connect(timeout=5.0)`` in a button slot froze the window for the TCP
connect, then the TLS / WebSocket upgrade, then the auth exchange -- each
bounded at five seconds, so ten to fifteen against a host that accepts and
says nothing. The legacy viewer panel and the Quick Connect screen both connect
through here instead: the viewer is built on the GUI thread, connected on a
task-controller worker, and handed back on the GUI thread.
"""
import functools
from typing import Any, Callable

from PySide6.QtCore import QObject

from je_auto_control.gui._weak_call import weak_slot
from je_auto_control.gui.task_controller import CancellationToken, TaskHandle, task_controller
from je_auto_control.utils.logging.logging_instance import autocontrol_logger

#: Seconds the backend gets for each step of the connect.
CONNECT_TIMEOUT_S = 5.0


def _disconnect_quietly(viewer: Any) -> None:
    """Close a viewer nobody will use; safe on one that never connected, and twice."""
    try:
        viewer.disconnect()
    except (OSError, RuntimeError) as error:
        autocontrol_logger.debug("dropping an unused viewer: %r", error)


def _connect(viewer: Any, timeout_s: float, token: CancellationToken) -> Any:
    """Worker thread: connect ``viewer`` and return it."""
    # connect() takes a timeout but no cancel signal: a cancelled attempt
    # runs out its timeout, and the viewer it produced is disconnected by
    # the task's ``discard``.
    token.raise_if_cancelled()
    viewer.connect(timeout=token.remaining(timeout_s))
    return viewer


def connect_viewer(owner: QObject, viewer: Any, *,
                   on_connected: Callable[[Any], None],
                   on_failed: Callable[[Exception], None],
                   timeout_s: float = CONNECT_TIMEOUT_S) -> TaskHandle:
    """Run ``viewer.connect`` off the GUI thread for ``owner``; return the task.

    ``on_connected(viewer)`` or ``on_failed(error)`` runs on the GUI thread,
    and only while ``owner`` exists; both are held weakly, so pass methods of
    the panel (or a ``functools.partial`` of one), never a closure over it.
    Cancelling the task, or destroying ``owner``, disconnects a viewer that
    connects anyway.
    """
    handle = task_controller().submit(functools.partial(_connect, viewer, timeout_s),
                                      owner=owner, discard=_disconnect_quietly)
    handle.result.connect(weak_slot(on_connected))
    handle.error.connect(weak_slot(on_failed))
    return handle


__all__ = ["CONNECT_TIMEOUT_S", "connect_viewer"]
