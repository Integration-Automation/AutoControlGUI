"""Cross-process ownership for one runtime database; imports never acquire locks."""
from __future__ import annotations

import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Iterator

from je_auto_control.utils.agent_runtime.errors import AgentControlBusy


class RuntimeLock:
    """Hold an OS-released lock before recovering durable tasks and input leases."""

    def __init__(self, path: str | Path) -> None:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        self._stream: Any = target.open("a+b")
        try:
            self._stream.seek(0)
            self._stream.write(b"\0")
            self._stream.flush()
            self._stream.seek(0)
            _lock(self._stream)
        except OSError as error:
            self._stream.close()
            raise AgentControlBusy("another runtime still owns this task store") from error

    def close(self) -> None:
        """Release only this runtime's OS lock; repeated close is harmless."""
        if not self._stream.closed:
            self._stream.close()


@contextmanager
def close_runtime_ownership(mutex: Any, owner: Any, history: Any,
                            snapshot: Callable[[], tuple[bool, Any]]) -> Iterator[bool]:
    """Serialize final owner release with lazy construction after inputs have already retired."""
    if not mutex.acquire(blocking=False):
        raise AgentControlBusy('runtime construction or mutation is still active')
    try:
        closed, controller = snapshot()
        if closed:
            yield False
            return
        if controller is not None:
            controller.close()
        yield True
        history.close()
        owner.close()
    finally:
        mutex.release()


def _lock(stream: Any) -> None:
    if sys.platform == "win32":
        import msvcrt
        msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
    else:
        import fcntl  # pylint: disable=import-error  # reason: POSIX-only dependency guarded by target platform
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
