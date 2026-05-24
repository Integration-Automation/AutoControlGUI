"""Wayland screen backend (grim + wlr-randr CLI bridges).

Screen capture goes through ``grim`` — the wlroots screencopy tool —
because the xdg-desktop-portal ScreenCast path needs a user-consent
dialog every call. Resolution comes from ``wlr-randr`` when present;
otherwise the GNOME ``gnome-screenshot`` fallback is consulted.
"""
from __future__ import annotations

import re
import subprocess  # nosec B404  # reason: argv-list, no shell interpolation
from typing import List, Optional, Tuple

from PIL import Image

from je_auto_control.linux_wayland._detect import WAYLAND_GRIM, binary_path
from je_auto_control.utils.exception.exceptions import AutoControlException


_RESOLUTION_RE = re.compile(  # NOSONAR python:S5852  # reason: anchored short ``\d+`` runs, no nested quantifiers — not vulnerable to ReDoS
    r"(\d+)x(\d+)",
)
_INSTALL_HINT_GRIM = (
    "grim is required for Wayland screenshots. "
    "Install with your package manager (e.g. `apt install grim`)."
)


def _require_grim() -> str:
    path = binary_path(WAYLAND_GRIM)
    if path is None:
        raise AutoControlException(_INSTALL_HINT_GRIM)
    return path


def _run(argv: list, *, timeout: float = 10.0) -> bytes:
    try:
        completed = subprocess.run(  # nosec B603  # reason: argv-list, validated binary
            argv, check=True, timeout=timeout,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
    except subprocess.CalledProcessError as error:
        message = (error.stderr or b"").decode("utf-8", errors="replace")
        raise AutoControlException(
            f"{argv[0]} exited {error.returncode}: {message.strip()}",
        ) from error
    except subprocess.TimeoutExpired as error:
        raise AutoControlException(
            f"{argv[0]} timed out after {timeout}s",
        ) from error
    return completed.stdout or b""


def screen_size() -> Tuple[int, int]:
    """Return the primary monitor's pixel size.

    Tries ``wlr-randr`` first (sway / hyprland) then falls back to
    grim's PNG header so the call still works on GNOME / KDE without
    extra dependencies.
    """
    coords = _size_from_wlr_randr()
    if coords is not None:
        return coords
    return _size_from_grim_capture()


def screenshot(file_path: Optional[str] = None,
               screen_region: Optional[List[int]] = None) -> Optional[str]:
    """Capture the screen with ``grim``.

    ``screen_region`` is ``[x1, y1, x2, y2]`` (matching the X11
    backend's calling convention). When ``file_path`` is omitted the
    capture is returned as PNG bytes via grim's stdout but discarded;
    callers should pass an explicit path to keep the file.
    """
    grim = _require_grim()
    argv = [grim]
    if screen_region is not None:
        x1, y1, x2, y2 = (int(v) for v in screen_region)
        argv.extend(["-g", f"{x1},{y1} {x2 - x1}x{y2 - y1}"])
    argv.append(file_path if file_path else "-")
    _run(argv)
    return file_path


def _size_from_wlr_randr() -> Optional[Tuple[int, int]]:
    if binary_path("wlr-randr") is None:
        return None
    try:
        output = _run(["wlr-randr"], timeout=5.0).decode(
            "utf-8", errors="replace",
        )
    except AutoControlException:
        return None
    for line in output.splitlines():
        match = _RESOLUTION_RE.search(line)
        if match:
            return int(match.group(1)), int(match.group(2))
    return None


def _size_from_grim_capture() -> Tuple[int, int]:
    grim = _require_grim()
    data = _run([grim, "-"], timeout=10.0)
    if not data:
        raise AutoControlException("grim produced no output")
    from io import BytesIO
    with Image.open(BytesIO(data)) as image:
        return int(image.width), int(image.height)


__all__ = ["screen_size", "screenshot"]
