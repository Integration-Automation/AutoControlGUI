"""Cross-process ownership for one runtime database; imports never acquire locks."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

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


def _lock(stream: Any) -> None:
    if sys.platform == "win32":
        import msvcrt
        msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
    else:
        import fcntl  # pylint: disable=import-error  # reason: POSIX-only dependency guarded by target platform
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
