"""Host-reviewed browser Python environments and bounded owned dependency-probe helpers."""
from __future__ import annotations

from contextlib import closing
import os
from pathlib import Path
import threading
from typing import Any, Mapping, Sequence

from je_auto_control.utils.agent_runtime.browser_environment import validate_browser_probe
from je_auto_control.utils.agent_runtime.errors import AgentControlBusy, AgentTaskError
from je_auto_control.utils.agent_runtime.native_channel import OwnedChannel
from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils.exception.control_signals import raise_caused_run_interruption

_PROBES = threading.BoundedSemaphore(2)
_WORKER = "je_auto_control.utils.agent_runtime.native_worker"


def normalize_helper_python(value: Any) -> str:
    """Require an explicit local absolute interpreter path, preserving virtualenv executable symlinks."""
    if not isinstance(value, str) or not value or len(value) > 4096 or any(char in value for char in "\r\n\x00"):
        raise AgentTaskError("browser helper Python must be a bounded local absolute path")
    path = Path(value)
    if not path.is_absolute() or value.startswith(("\\\\", "//")) or ".." in path.parts:
        raise AgentTaskError("browser helper Python must be a local absolute path without parent traversal")
    # Resolving this executable would replace POSIX virtualenv symlinks with the base interpreter.
    return os.path.abspath(value)


def browser_helper_argv(settings: Mapping[str, Any]) -> tuple[str, ...] | None:
    """Use installed isolated packages only for an explicitly configured host interpreter."""
    if "helper_python" not in settings:
        return None
    return (normalize_helper_python(settings["helper_python"]), "-I", "-u", "-m", _WORKER)


def probe_browser_helper(argv: Sequence[str], *, transfer: bool) -> dict[str, Any]:
    """Inspect dependencies in a fresh owned helper without acquiring the target's input resource."""
    # pylint: disable-next=consider-using-with  # reason: probe capacity must fail fast, then release in finally
    if not _PROBES.acquire(blocking=False):
        raise AgentControlBusy("browser helper dependency probe capacity is busy")
    try:
        with closing(OwnedChannel(argv)) as channel:
            hello = channel.request("bootstrap", {}, timeout=15)
            if hello != {"protocol": 1}:
                raise AgentTaskError("incompatible browser helper bootstrap")
            reply = channel.request("probe_browser", {"transfer": transfer}, timeout=10)
            return validate_browser_probe(reply, transfer)
    except (AutoControlException, OSError, RuntimeError, TypeError, ValueError) as error:
        raise_caused_run_interruption(error)
        return {"status": "unknown", "reason": "helper_probe_unavailable", "browser_launch": "not_probed",
                "native_evidence": "not_recorded"}
    finally:
        _PROBES.release()
