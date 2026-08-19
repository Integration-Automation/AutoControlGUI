"""Wayland screen capture, tried against each compositor's own tool.

No Wayland compositor exposes a readable root window the way X11 does, and
which helper *can* read the screen differs by desktop: wlroots compositors
(sway, Hyprland, river) implement ``wlr-screencopy``, which ``grim`` speaks;
GNOME answers through ``gnome-screenshot``; KDE through ``spectacle``. None of
them is guaranteed to be present, so ``xdg-desktop-portal`` backs them all up
(see :mod:`portal`), and an operator whose setup none of that fits can name
their own command. The tiers, in order:

1. ``JE_AUTOCONTROL_WAYLAND_CAPTURE_COMMAND`` — an explicit operator override.
2. ``grim`` · 3. ``gnome-screenshot`` · 4. ``spectacle``.
5. ``xdg-desktop-portal``, over the session bus.

Only ``grim`` accepts a region itself. Every other tier returns the whole
screen, so :class:`Capture` reports which of the two happened and the caller
crops when it has to.
"""
from __future__ import annotations

import contextlib
import os
import shlex
import subprocess  # nosec B404  # reason: argv-list from a private allow-list, no shell
import tempfile
from dataclasses import dataclass
from typing import Callable, List, Optional, Sequence, Tuple

from je_auto_control.linux_wayland import portal
from je_auto_control.linux_wayland._detect import (
    WAYLAND_GNOME_SCREENSHOT, WAYLAND_GRIM, WAYLAND_SPECTACLE, binary_path,
)
from je_auto_control.utils.exception.exceptions import AutoControlScreenException


CAPTURE_TIMEOUT = 15.0

#: Operator override: a full command line whose ``{output}`` placeholder is
#: replaced with a temporary PNG path. Split with ``shlex``, run without a
#: shell. Always a whole-screen capture — regions are cropped afterwards, so
#: the command never has to understand geometry.
CAPTURE_COMMAND_ENV = "JE_AUTOCONTROL_WAYLAND_CAPTURE_COMMAND"

_OVERRIDE_LABEL = f"${CAPTURE_COMMAND_ENV}"
_PORTAL_LABEL = "xdg-desktop-portal"

_MISSING_TOOL_HINT = (
    "No Wayland screen-capture tool found. Install the one your compositor "
    "supports: grim (sway / Hyprland / river, or any wlr-screencopy "
    "compositor), gnome-screenshot (GNOME), or spectacle (KDE). Installing "
    "none of them, the xdg-desktop-portal fallback needs only a session bus "
    "and is tried automatically. Or name "
    "your own capture command in " + CAPTURE_COMMAND_ENV + ", using {output} "
    "for the file to write. To capture through XWayland set "
    "JE_AUTOCONTROL_LINUX_DISPLAY_SERVER=x11 — note XWayland cannot see "
    "native Wayland windows, so that capture is blank for most of the desktop."
)


@dataclass(frozen=True)
class Capture:
    """One capture's PNG bytes, plus whether the tool applied the region.

    ``region_applied`` is False whenever the helper could only grab the
    whole screen, which tells the caller it still has to crop.
    """

    data: bytes
    region_applied: bool


def run_tool(argv: List[str], *, timeout: float = CAPTURE_TIMEOUT) -> bytes:
    """Run one capture helper and return its stdout.

    :param argv: absolute binary path plus arguments, never a shell string.
    :param timeout: seconds before the helper is considered hung.
    :return: the helper's stdout (empty bytes when it writes to a file).
    """
    # argv comes from a private allow-list (grim / gnome-screenshot /
    # spectacle / wlr-randr resolved through shutil.which), never user
    # input; no shell=True.
    try:
        completed = subprocess.run(argv, check=True,  # nosec B603  # nosemgrep
                                   timeout=timeout,
                                   stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE)
    except subprocess.CalledProcessError as error:
        message = (error.stderr or b"").decode("utf-8", errors="replace")
        raise AutoControlScreenException(
            f"{argv[0]} exited {error.returncode}: {message.strip()}",
        ) from error
    except subprocess.TimeoutExpired as error:
        raise AutoControlScreenException(
            f"{argv[0]} timed out after {timeout}s",
        ) from error
    return completed.stdout or b""


def geometry(screen_region: Sequence[int]) -> str:
    """Format ``[x1, y1, x2, y2]`` as grim's ``-g`` argument (``"x,y WxH"``)."""
    x1, y1, x2, y2 = (int(value) for value in screen_region)
    if x2 <= x1 or y2 <= y1:
        raise AutoControlScreenException(
            f"screen_region must have positive width and height; got "
            f"[{x1}, {y1}, {x2}, {y2}]",
        )
    return f"{x1},{y1} {x2 - x1}x{y2 - y1}"


def _gnome_argv(executable: str, output_path: str) -> List[str]:
    return [executable, "-f", output_path]


def _spectacle_argv(executable: str, output_path: str) -> List[str]:
    # -b background (no GUI), -n no notification, -f full screen, -o output.
    return [executable, "-b", "-n", "-f", "-o", output_path]


# Helpers that can only write a full-screen PNG to a file, in the order they
# are tried once grim is absent.
_FILE_TOOLS: Tuple[Tuple[str, Callable[[str, str], List[str]]], ...] = (
    (WAYLAND_GNOME_SCREENSHOT, _gnome_argv),
    (WAYLAND_SPECTACLE, _spectacle_argv),
)


def _override_template() -> str:
    """The operator's capture command line, or "" when unset."""
    return (os.environ.get(CAPTURE_COMMAND_ENV) or "").strip()


def _override_argv(output_path: str) -> List[str]:
    """Build the operator's capture command for one output path.

    ``shlex.split`` then per-token substitution — never a shell, and never
    string-concatenating the path into a command line, so a path containing
    spaces or quotes stays one argument.
    """
    template = _override_template()
    argv = shlex.split(template)
    if not argv:
        raise AutoControlScreenException(
            f"{CAPTURE_COMMAND_ENV} is set but empty",
        )
    if not any("{output}" in token for token in argv):
        raise AutoControlScreenException(
            f"{CAPTURE_COMMAND_ENV} must contain {{output}}, the path the "
            f"command should write the capture to; got {template!r}",
        )
    return [token.replace("{output}", output_path) for token in argv]


def available_tool() -> Optional[str]:
    """Return the capture tier that would be used, or None if there is none.

    Reported by the diagnostics bundle so an operator can see *why* a capture
    failed without reproducing it.
    """
    if _override_template():
        return _OVERRIDE_LABEL
    for name in (WAYLAND_GRIM, *(tool for tool, _ in _FILE_TOOLS)):
        if binary_path(name) is not None:
            return name
    return _PORTAL_LABEL if portal.is_available() else None


def _grim_capture(executable: str,
                  screen_region: Optional[Sequence[int]]) -> Capture:
    argv = [executable]
    if screen_region is not None:
        argv.extend(["-g", geometry(screen_region)])
    argv.append("-")
    data = run_tool(argv)
    if not data:
        raise AutoControlScreenException("grim produced no output")
    return Capture(data, screen_region is not None)


def _write_to_temp_png(write: Callable[[str], None], label: str) -> Capture:
    """Let ``write`` fill a temporary PNG, then read and delete it."""
    handle, output_path = tempfile.mkstemp(prefix="je_autocontrol_",
                                           suffix=".png")
    os.close(handle)
    try:
        write(output_path)
        with open(output_path, "rb") as captured:
            data = captured.read()
    finally:
        with contextlib.suppress(OSError):
            os.unlink(output_path)
    if not data:
        raise AutoControlScreenException(f"{label} produced no output")
    return Capture(data, False)


def _file_capture(executable: str,
                  build_argv: Callable[[str, str], List[str]]) -> Capture:
    """Run a helper that writes a PNG to a path we choose."""
    return _write_to_temp_png(
        lambda output_path: run_tool(build_argv(executable, output_path)),
        executable,
    )


def _override_capture() -> Capture:
    """Run the operator's own capture command."""
    return _write_to_temp_png(
        lambda output_path: run_tool(_override_argv(output_path)),
        _OVERRIDE_LABEL,
    )


def grab_png(screen_region: Optional[Sequence[int]] = None) -> Capture:
    """Capture the screen as PNG bytes using the first tier that can.

    :param screen_region: ``[x1, y1, x2, y2]`` to capture, or None for all.
    :return: the PNG bytes and whether the region was applied by the tier.
    """
    if _override_template():
        return _override_capture()
    grim = binary_path(WAYLAND_GRIM)
    if grim is not None:
        return _grim_capture(grim, screen_region)
    for name, build_argv in _FILE_TOOLS:
        executable = binary_path(name)
        if executable is not None:
            return _file_capture(executable, build_argv)
    if portal.is_available():
        return Capture(portal.capture_png(), False)
    raise AutoControlScreenException(_MISSING_TOOL_HINT)


__all__ = [
    "CAPTURE_COMMAND_ENV", "CAPTURE_TIMEOUT", "Capture", "available_tool",
    "geometry", "grab_png", "run_tool",
]
