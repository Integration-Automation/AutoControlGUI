"""Bind the existing file-dialog executor to one task-owned window and rooted absolute path."""
from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Any, Iterator

from je_auto_control.utils.agent_runtime.errors import AgentHumanReview, AgentTaskError
from je_auto_control.utils.agent_runtime.models import positive
from je_auto_control.utils.agent_runtime.workflow_files import task_policy
from je_auto_control.utils.file_dialog.file_dialog import FileDialogDriver, _driver_scope


class _ScopedDriver(FileDialogDriver):
    def __init__(self, target: Any, window_id: int, process_id: int) -> None:
        self._target, self._window_id, self._process_id = target, window_id, process_id

    def wait_window(self, title: str, timeout_s: float) -> bool:
        from je_auto_control.wrapper.window_backends import get_backend
        if self._target._action_identity != (self._window_id, self._process_id):
            raise AgentHumanReview("file dialog origin identity changed before dispatch")
        positive(timeout_s, "file dialog wait", 60)
        policy = task_policy()
        backend = get_backend()
        deadline = time.monotonic() + min(timeout_s, policy.spec.budget.action_seconds)
        wanted = title.strip().casefold()
        while True:
            task_policy()
            matches = [window for window, name in backend.list_windows() if name.strip().casefold() == wanted]
            if len(matches) > 1:
                raise AgentHumanReview("file dialog selection is ambiguous")
            if matches:
                if time.monotonic() > deadline:
                    return False
                return self._focus(backend, matches[0])
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return False
            time.sleep(min(0.05, remaining))

    def _focus(self, backend: Any, window_id: int) -> bool:
        if backend.window_process_id(window_id) != self._process_id:
            raise AgentHumanReview("file dialog belongs to another process")
        if not backend.bring_to_front(window_id):
            return False
        hwnd, _title, process_id = self._target._check_foreground()
        if (hwnd, process_id) != (window_id, self._process_id):
            raise AgentHumanReview("file dialog foreground identity could not be confirmed")
        self._target._action_identity = hwnd, process_id
        return True

    def type_path(self, path: str) -> None:
        super().type_path(task_policy().path(path))


@contextmanager
def scoped_file_dialog(target: Any, window_id: int, process_id: int, arguments: dict) -> Iterator[None]:
    """Keep the public executor call/journal intact while replacing only its trusted driver seam."""
    if "driver" in arguments:
        raise AgentTaskError("managed file dialogs cannot override their host driver")
    with _driver_scope(_ScopedDriver(target, window_id, process_id)):
        yield
