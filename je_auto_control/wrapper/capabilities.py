"""Passive backend capability snapshots; never request consent or emit input."""
from __future__ import annotations

import os
import shutil
import sys
from ctypes.util import find_library
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Literal, Mapping

CapabilityState = Literal["available", "needs_permission", "needs_dependency", "unsupported"]


@dataclass(frozen=True)
class CapabilityStatus:
    """One capability's evidence, scope and recovery action.

    Available means the backend or cached grant exists, not that native
    platform acceptance has been independently verified. Probes do not
    dispatch pending revocation events; emissions check their grant again.
    """

    state: CapabilityState
    backend: str
    reason: str
    recovery: str = ""
    desktop_wide: bool = True


@dataclass(frozen=True)
class CapabilitySnapshot:
    """Independent input/capture status plus native permission limitations."""

    input: CapabilityStatus
    capture: CapabilityStatus
    restore_token: CapabilityStatus

    def to_dict(self) -> dict[str, object]:
        """Return JSON-compatible capability evidence for GUI/AC/MCP callers."""
        return asdict(self)


@dataclass(frozen=True)
class BackendContext:
    """Probe settings; injecting environment permits isolated headless tests."""

    platform: str = field(default_factory=lambda: sys.platform)
    display_server: str = "auto"
    environ: Mapping[str, str] = field(default_factory=lambda: dict(os.environ))


def _wayland_input(context: BackendContext) -> CapabilityStatus:
    from je_auto_control.linux_wayland.libei import input_permission_status

    override = context.environ.get("JE_AUTOCONTROL_WAYLAND_INPUT_BACKEND", "auto").strip().lower()
    if override == "cli":
        found = shutil.which("ydotool")
        return CapabilityStatus(
            "needs_permission" if found else "needs_dependency", "ydotool",
            "explicit CLI input; daemon and /dev/uinput access are not probed" if found else "ydotool not found",
            "Start ydotoold with explicitly granted /dev/uinput access; install ydotool >=1.0.",
        )
    cached = input_permission_status()
    if cached is not None:
        state, reason = cached
        return CapabilityStatus(
            "available" if state == "available" else "needs_permission", "libei", reason,
            "Explicitly retry authorization or configure the CLI backend." if state != "available" else "",
        )
    if not find_library("ei"):
        return CapabilityStatus(
            "needs_dependency", "libei", "libei was not discovered (not loaded by this probe)",
            "Install libei; or explicitly select the CLI backend.",
        )
    runtime = context.environ.get("XDG_RUNTIME_DIR", "/run/user/1000")
    if not find_library("oeffis") and not Path(runtime, "eis-0").exists():
        return CapabilityStatus(
            "needs_dependency", "libei", "no liboeffis or compositor EIS socket discovered",
            "Install liboeffis for portal authorization, or use the compositor's EIS socket.",
        )
    return CapabilityStatus(
        "needs_permission", "libei", "portal authorization has not been requested",
        "Explicitly retry authorization via reset_default_backend(), then request input; or select cli.",
    )


def _wayland_capture(context: BackendContext) -> CapabilityStatus:
    override = context.environ.get("JE_AUTOCONTROL_WAYLAND_CAPTURE_COMMAND", "").strip()
    if override:
        return CapabilityStatus(
            "available", "custom_command", "operator capture override configured; command not executed",
            "Ensure the command contains {output} and writes a PNG.",
        )
    for tool in ("grim", "gnome-screenshot", "spectacle"):
        if shutil.which(tool):
            return CapabilityStatus(
                "available", tool, "capture helper found; compositor support/permission not exercised",
            )
    if context.environ.get("DBUS_SESSION_BUS_ADDRESS"):
        return CapabilityStatus(
            "needs_permission", "xdg-desktop-portal", "session bus configured; screenshot consent not requested",
            "Explicitly request a screenshot and respond to the portal dialog.",
        )
    return CapabilityStatus(
        "needs_dependency", "wayland", "no capture helper or session bus configured",
        "Install your compositor's capture helper or configure the session bus/desktop portal.",
    )


def probe_capabilities(context: BackendContext | None = None) -> CapabilitySnapshot:
    """Describe input and capture without loading native libraries or opening a bus."""
    current = context if context is not None else BackendContext()
    from je_auto_control.linux_wayland._detect import is_wayland_session, select_display_server

    display = current.display_server
    if display == "auto":
        display = select_display_server(current.environ)
    restore = CapabilityStatus(
        "unsupported", "liboeffis", "the current liboeffis binding does not expose restore tokens",
        "Authorize a new session explicitly; no restore token is persisted.",
    )
    if current.platform.startswith("linux") and display == "wayland":
        return CapabilitySnapshot(_wayland_input(current), _wayland_capture(current), restore)
    xwayland = current.platform.startswith("linux") and is_wayland_session(current.environ)
    backend = "XWayland" if xwayland else current.platform
    reason = "XWayland covers X11 clients only; native Wayland windows are inaccessible" if xwayland else (
        "platform backend selected; this passive probe does not verify native permissions"
    )
    state: CapabilityState = "needs_permission" if current.platform == "darwin" else "available"
    status = CapabilityStatus(state, backend, reason, desktop_wide=not xwayland)
    return CapabilitySnapshot(status, status, restore)


__all__ = ["BackendContext", "CapabilitySnapshot", "CapabilityStatus", "probe_capabilities"]
