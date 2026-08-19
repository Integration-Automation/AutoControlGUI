"""Which ydotool command line is installed — and refusing the one that lies.

ydotool 1.0 replaced its command line wholesale. Everything this backend
builds arrived in that release: ``mousemove --absolute``, ``mousemove
--wheel``, hex button bitmasks for ``click`` (so a press and a release can be
sent separately, which is what makes a drag possible), and ``key CODE:STATE``
taking numeric evdev codes instead of key names.

The 0.1.x series is still what ``apt install ydotool`` — the hint this
backend used to print — installs on Debian bookworm and on every current
Ubuntu. It does not merely reject the newer argv. Measured against a real
uinput device (``docker/ydotool_verify.py`` runs the same comparison in CI):

===========================  ====  =======================================
AutoControl's call           rc    what reached the kernel
===========================  ====  =======================================
``click 0xc0`` (left)        0     BTN_LEFT down+up — right by coincidence
``click 0x40`` (press only)  0     *nothing*
``click 0xc1`` (right)       0     *nothing*
``mousemove --absolute ...`` 0     *nothing* — "unrecognised option"
``mousemove --wheel ...``    0     *nothing* — "unrecognised option"
``key 30:1``                 0     *nothing*
===========================  ====  =======================================

Every one exits **0**, including the two that print ``unrecognised option``.
The backends run ydotool with ``check=True``, so a non-zero status is the
only thing that would raise — which means on those distributions a script
clicked nothing, typed nothing and moved nothing while every call reported
success. A silent no-op is the one failure mode a GUI automation library
cannot ship, so the legacy CLI is refused up front instead.

Neither series implements ``--version``, and 1.x needs its daemon running
before it will answer ``--help``, so the probe uses the one thing both print
without a daemon and without side effects: the no-argument command list.
"""
from __future__ import annotations

import subprocess  # nosec B404  # reason: argv-list, path from shutil.which, no shell
import threading
from typing import Dict, Optional

from je_auto_control.utils.exception.exceptions import AutoControlException


#: ydotool 0.1.x listed a ``recorder`` command; 1.0 dropped it.
_LEGACY_COMMAND = "recorder"

#: 1.x is daemon-only and advertises the socket override in its usage banner.
#: 0.1.x, which talks to ``/dev/uinput`` directly, has no such line.
_MODERN_MARKER = "ydotool_socket"

MODERN = "modern"
LEGACY = "legacy"
UNKNOWN = "unknown"

#: Probing costs a subprocess, and mouse / key dispatch must not pay that per
#: event, so the answer is cached per resolved binary path.
_cache: Dict[str, str] = {}
_cache_lock = threading.Lock()

_PROBE_TIMEOUT = 5.0

_LEGACY_HINT = (
    "ydotool 0.1.x is installed at {path}, and its command line cannot "
    "express what this backend needs: absolute cursor moves, separate "
    "button press and release edges, wheel events, and numeric evdev key "
    "codes all arrived in ydotool 1.0. Worse, 0.1.x exits 0 while emitting "
    "nothing for those arguments, so every call would report success and do "
    "nothing. Install ydotool 1.0 or newer (Debian: from unstable, which "
    "packages 1.0.4; Arch: `pacman -S ydotool`; Fedora: `dnf install "
    "ydotool`; or build from https://github.com/ReimuNotMoe/ydotool), or "
    "set JE_AUTOCONTROL_LINUX_DISPLAY_SERVER=x11 to drive XWayland instead."
)


def _probe(path: str) -> str:
    """Classify the installed ydotool by its no-argument usage banner."""
    try:
        completed = subprocess.run(  # nosec B603  # nosemgrep
            [path], capture_output=True, timeout=_PROBE_TIMEOUT, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        # An unreadable probe is not evidence of the broken version; let the
        # real call fail with its own message rather than blaming the CLI.
        return UNKNOWN
    banner = (completed.stdout + completed.stderr).decode(
        "utf-8", errors="replace").lower()
    if _MODERN_MARKER in banner:
        return MODERN
    if _LEGACY_COMMAND in banner.split():
        return LEGACY
    return UNKNOWN


def cli_generation(path: str) -> str:
    """Return ``MODERN`` / ``LEGACY`` / ``UNKNOWN`` for the ydotool at ``path``.

    The result is cached per path for the life of the process.
    """
    with _cache_lock:
        cached = _cache.get(path)
    if cached is not None:
        return cached
    generation = _probe(path)
    with _cache_lock:
        _cache[path] = generation
    return generation


def reject_legacy_cli(path: str) -> str:
    """Return ``path``, or raise when it is the 0.1.x CLI that silently no-ops.

    ``UNKNOWN`` is allowed through on purpose: only the version measured to
    fail silently is refused, so a future release that drops the markers this
    probe reads is not blocked by a stale detector.
    """
    if cli_generation(path) == LEGACY:
        raise AutoControlException(_LEGACY_HINT.format(path=path))
    return path


def reset_cache(path: Optional[str] = None) -> None:
    """Forget probe results — for tests, and after installing a new ydotool."""
    with _cache_lock:
        if path is None:
            _cache.clear()
        else:
            _cache.pop(path, None)


__all__ = [
    "LEGACY", "MODERN", "UNKNOWN", "cli_generation", "reject_legacy_cli",
    "reset_cache",
]
