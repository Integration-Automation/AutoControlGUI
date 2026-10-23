"""POSIX helpers retire their own live process group when the owning parent disappears."""
from __future__ import annotations

import os
import signal
import sys
import threading

from je_auto_control.utils.agent_runtime.errors import AgentTaskError


def start_parent_watch() -> None:
    """Watch only the actual parent and signal only this still-live session leader's own group."""
    if sys.platform == "win32":
        return
    parent = os.getppid()
    if os.getpgrp() != os.getpid() or os.getsid(0) != os.getpid():
        raise AgentTaskError("native helper requires its own owned session")

    def watch() -> None:
        while os.getppid() == parent and parent > 1:
            threading.Event().wait(0.1)
        os.killpg(os.getpgrp(), signal.SIGKILL)

    threading.Thread(target=watch, name="NativeParentWatch", daemon=True).start()
