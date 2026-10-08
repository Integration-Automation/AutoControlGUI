"""What a tab's ``dispose()`` does, in one place.

``close_tab(key, release=True)`` calls the tab's ``dispose()`` and then
schedules the widget for deletion. Deletion alone is late and partial: it
happens when the event loop next runs, a ``QTimer`` keeps firing until then,
and whatever the tab registered *outside* Qt -- a listener on a registry that
outlives it, a share of the USB watcher, a handler on the global logger, a
background task still waiting on a peer -- is released only by a ``destroyed``
hook, if the tab has one. ``dispose()`` lets go of all of it at once, on the
call, so "release" means released when it returns.

Background work is cancelled the way destroying the tab would cancel it a
moment later: a task of the :mod:`~je_auto_control.gui.task_controller` through
its token (a script run stops, a result that still arrives goes to the task's
``discard``), a bare :func:`~je_auto_control.gui._worker_thread.start_worker`
worker through its ``request_stop()`` when it has one, and in both cases the
outcome is no longer delivered. Work that cannot be interrupted runs to its
end unobserved.

A tab's ``dispose()`` is one call to :func:`release_resources` naming its own
extra releases. It must be safe to call twice, and the ``destroyed`` hooks the
tabs already have stay: a tab deleted without ``dispose()`` (the window
closing) still cleans up.
"""
from typing import Callable

from PySide6.QtCore import QObject, QTimer

from je_auto_control.gui._worker_thread import cancel_workers
from je_auto_control.gui.task_controller import task_controller
from je_auto_control.utils.logging.logging_instance import autocontrol_logger


def stop_timers(owner: QObject) -> int:
    """Stop every ``QTimer`` below ``owner``; return how many were running."""
    stopped = 0
    for timer in owner.findChildren(QTimer):
        if timer.isActive():
            timer.stop()
            stopped += 1
    return stopped


def release_resources(owner: QObject, *releases: Callable[[], object]) -> None:
    """Stop ``owner``'s timers, cancel its background tasks and workers, and run each release.

    A release that raises is logged and does not keep the others from
    running: a half-disposed tab would still be deleted.
    """
    stop_timers(owner)
    task_controller().cancel_all(owner)
    cancel_workers(owner)
    for release in releases:
        try:
            release()
        except Exception as error:  # noqa: BLE001  # reason: logged; the remaining releases must still run
            autocontrol_logger.warning(f"dispose of {type(owner).__name__} failed in {release!r}: {error!r}")


__all__ = ["release_resources", "stop_timers"]
