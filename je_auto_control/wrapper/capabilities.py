"""What this session can do right now, and what stands in the way if it cannot.

``platform_wrapper`` picks a backend at import and says nothing more. That is
enough on Windows; on Wayland it leaves every interesting question open. Is
input going through the portal or through ``/dev/uinput``? Did the user refuse
the consent dialog, or is there no portal to ask? Is this the Wayland backend
at all, or the X11 one talking to XWayland and reaching only half the windows?

:func:`probe_capabilities` answers those as data. Four capabilities, each
diagnosed on its own because they fail independently — a host with working
capture and no input is ordinary, and one verdict for both hides which:

``input``          synthesising keyboard and pointer events
``capture``        reading pixels off the screen
``recording``      reading what the *user* types and clicks
``stop_shortcut``  a global key that stops a running script

**Probing has no side effect.** It reads the environment, looks names up on
``PATH``, asks the loader whether a library exists, and reads the
authorisation ledger. It never opens a portal request, never shows a consent
dialog, never connects a libei sender and never sends an event — so it is safe
to call from a diagnostics screen, a health check, or an MCP client that has
no business moving the pointer.

On Windows and macOS the same rule holds, with different questions: the
process's integrity level and session, whether the workstation is locked,
whether one pixel can be copied off the screen; Accessibility, Screen
Recording and Input Monitoring through the calls that *check* a permission,
never the ones that ask for it (:mod:`capability_probes`). What could not be
read is ``unknown``, not ``available``.

Everything it consults comes in through :class:`BackendContext`, which is what
makes a GNOME session describable from a Windows test run.
"""
from __future__ import annotations

import ctypes.util
import os
import shutil
import sys
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, Mapping, Optional, Tuple

from je_auto_control.linux_wayland._detect import (
    WAYLAND_GNOME_SCREENSHOT, WAYLAND_GRIM, WAYLAND_SPECTACLE,
    WAYLAND_YDOTOOL, is_wayland_session, select_display_server,
)
from je_auto_control.linux_wayland.authorisation import (
    CAPTURE, CAPTURE_RECOVERY, INPUT, INPUT_RECOVERY, AuthorisationLedger,
    AuthorisationRecord, AuthorisationState, compositor_identity, ledger,
)
from je_auto_control.linux_wayland.input_events import (
    RECORD_DEVICES_ENV, configured_record_devices,
)
from je_auto_control.wrapper.capability_probes import (
    MacFacts, WindowsFacts, cheap_backend_version, read_mac_facts,
    read_windows_facts,
)

RECORDING = "recording"
STOP_SHORTCUT = "stop_shortcut"

_INPUT_BACKEND_ENV = "JE_AUTOCONTROL_WAYLAND_INPUT_BACKEND"
_CAPTURE_COMMAND_ENV = "JE_AUTOCONTROL_WAYLAND_CAPTURE_COMMAND"


class CapabilityStatus(str, Enum):
    """Where one capability stands. Compares equal to its string value."""

    AVAILABLE = "available"
    #: Usable, but the desktop has not been asked yet — it will be on first use.
    NOT_REQUESTED = "not_requested"
    #: A consent request is on screen right now.
    REQUESTING = "requesting"
    #: Someone has to say yes: a refused or unanswered consent, a device node
    #: this user may not read.
    NEEDS_PERMISSION = "needs_permission"
    #: Something has to be installed or configured.
    NEEDS_SETUP = "needs_setup"
    #: This process closed its session; the next use asks again.
    SESSION_CLOSED = "session_closed"
    #: The compositor took a granted session away.
    REVOKED = "revoked"
    #: The grant came from a compositor that is no longer the one running.
    COMPOSITOR_RESTARTED = "compositor_restarted"
    UNSUPPORTED = "unsupported"
    #: Not something this probe can determine without side effects.
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class Capability:
    """One capability's diagnosis."""

    name: str
    state: CapabilityStatus
    #: The backend that serves it, or would once the obstacle is cleared.
    backend: str
    #: False when only part of the desktop is reachable — XWayland.
    desktop_wide: bool = True
    detail: str = ""
    #: What the operator can do about it, in English; empty when nothing is
    #: wrong. ``recovery_key`` is the same advice as a GUI catalogue key.
    recovery: str = ""
    recovery_key: str = ""
    #: The raw authorisation state behind ``state``, where there is one.
    authorisation: str = ""
    #: Whether consent survives a restart: ``unsupported`` on the libei path,
    #: because liboeffis is never asked for a restore token by this binding.
    restore_token: str = "not_applicable"

    @property
    def usable(self) -> bool:
        """Whether an action using this capability can be attempted now."""
        return self.state in (CapabilityStatus.AVAILABLE,
                              CapabilityStatus.NOT_REQUESTED,
                              CapabilityStatus.SESSION_CLOSED)

    def to_dict(self) -> Dict[str, Any]:
        """JSON-ready form; the state becomes its plain string."""
        data = asdict(self)
        data["state"] = self.state.value
        data["usable"] = self.usable
        return data


@dataclass(frozen=True)
class CapabilitySnapshot:
    """Every capability of one session, at one moment."""

    platform: str
    #: ``wayland``, ``x11``, or the platform name where the question is moot.
    display_server: str
    #: True when the X11 backend is serving a Wayland session.
    xwayland: bool
    capabilities: Tuple[Capability, ...]
    #: What the serving backend could say about its version without running
    #: anything (``Windows 10.0.26200``, ``python-xlib 0.33``); ``""`` when it
    #: cannot be known that cheaply -- the Wayland tools, or a described
    #: desktop that is not this machine.
    backend_version: str = ""

    def get(self, name: str) -> Capability:
        """The capability called ``name``."""
        for capability in self.capabilities:
            if capability.name == name:
                return capability
        raise KeyError(name)

    @property
    def input(self) -> Capability:
        """Keyboard and pointer synthesis."""
        return self.get(INPUT)

    @property
    def capture(self) -> Capability:
        """Screen capture."""
        return self.get(CAPTURE)

    def to_dict(self) -> Dict[str, Any]:
        """JSON-ready form, shared by the executor, MCP and the GUI."""
        return {
            "platform": self.platform,
            "display_server": self.display_server,
            "xwayland": self.xwayland,
            "backend_version": self.backend_version,
            "capabilities": [item.to_dict() for item in self.capabilities],
        }


def _library_present(name: str) -> bool:
    """Whether the loader can find ``lib<name>``; loads nothing."""
    try:
        return ctypes.util.find_library(name) is not None
    except (OSError, ValueError):
        return False


def _session_bus_present() -> bool:
    """Whether a D-Bus session bus address is known; connects to nothing."""
    from je_auto_control.linux_wayland import _dbus_client
    return _dbus_client.is_available()


def _readable(path: str) -> bool:
    return os.access(path, os.R_OK)


def _loaded_backend() -> Optional[str]:
    """Which Linux backend ``platform_wrapper`` actually imported, if it has.

    Read out of ``sys.modules`` rather than imported: importing the wrapper
    is what *selects* a backend, and a probe must not be the thing that does.
    """
    wrapper = sys.modules.get("je_auto_control.wrapper.platform_wrapper")
    screen = getattr(wrapper, "screen", None)
    module = getattr(screen, "__name__", "")
    if "linux_wayland" in module:
        return "wayland"
    return "x11" if module else None


@dataclass(frozen=True)
class BackendContext:
    """Everything a probe is allowed to look at.

    The defaults read the live process. A test — or a support engineer
    reproducing someone else's desktop — replaces any of them.
    """

    platform: str = sys.platform
    environ: Mapping[str, str] = field(default_factory=lambda: os.environ)
    which: Callable[[str], Optional[str]] = shutil.which
    library_present: Callable[[str], bool] = _library_present
    session_bus_present: Callable[[], bool] = _session_bus_present
    readable: Callable[[str], bool] = _readable
    compositor: Callable[[Mapping[str, str]], Optional[str]] = (
        compositor_identity)
    authorisations: AuthorisationLedger = ledger
    #: ``wayland`` / ``x11`` once the wrapper has chosen, else None.
    loaded_backend: Optional[str] = None
    #: Read-only facts about a Windows / macOS session. The defaults query the
    #: live process and answer "unknown" on any other platform.
    windows_facts: Callable[[], WindowsFacts] = read_windows_facts
    mac_facts: Callable[[], MacFacts] = read_mac_facts
    #: ``backend name -> version text`` (``""`` when not cheaply known).
    backend_version: Callable[[str], str] = cheap_backend_version

    @classmethod
    def current(cls) -> "BackendContext":
        """The context of the running process."""
        return cls(loaded_backend=_loaded_backend())


def probe_capabilities(context: Optional[BackendContext] = None
                       ) -> CapabilitySnapshot:
    """Diagnose input, capture, recording and the stop shortcut.

    :param context: what to inspect; the live process when omitted.
    :return: one :class:`Capability` per capability. Never raises for a
        capability that is merely unavailable — that is a state, not an error.
    """
    ctx = context if context is not None else BackendContext.current()
    if not ctx.platform.startswith("linux"):
        return _other_platform(ctx)
    wanted = select_display_server(ctx.environ)
    serving = ctx.loaded_backend or wanted
    if serving == "wayland":
        return CapabilitySnapshot(ctx.platform, "wayland", False, (
            _wayland_input(ctx), _wayland_capture(ctx),
            _wayland_recording(ctx), _wayland_stop_shortcut(ctx)),
            backend_version=ctx.backend_version("wayland"))
    return _x11(ctx, is_wayland_session(ctx.environ))


# --- Windows, macOS and anything else --------------------------------------

def _other_platform(ctx: BackendContext) -> CapabilitySnapshot:
    from je_auto_control.wrapper import capability_states
    if ctx.platform == "win32":
        backend = "win32"
        found = capability_states.windows_capabilities(ctx.windows_facts())
    elif ctx.platform == "darwin":
        backend = "quartz"
        found = capability_states.mac_capabilities(ctx.mac_facts())
    else:
        backend = "x11"
        found = capability_states.unprobed_capabilities(backend)
    return CapabilitySnapshot(
        ctx.platform, ctx.platform, False,
        tuple(Capability(**fields) for fields in found),
        backend_version=ctx.backend_version(backend))


# --- X11, including X11 serving a Wayland session --------------------------

_XWAYLAND_SCOPE = (
    "the X11 backend is running against XWayland: it reaches X11 "
    "applications only, and native Wayland windows neither receive its "
    "input nor appear in its captures")
_XWAYLAND_RECOVERY = (
    "Install the Wayland tools (ydotool 1.0+ or libei, and grim, "
    "gnome-screenshot or spectacle) so the Wayland backend loads, or keep "
    "JE_AUTOCONTROL_LINUX_DISPLAY_SERVER=x11 only for X11 applications.")


def _x11(ctx: BackendContext, xwayland: bool) -> CapabilitySnapshot:
    has_display = bool((ctx.environ.get("DISPLAY") or "").strip())
    state = (CapabilityStatus.AVAILABLE if has_display
             else CapabilityStatus.NEEDS_SETUP)
    detail = _XWAYLAND_SCOPE if xwayland else ""
    recovery = _XWAYLAND_RECOVERY if xwayland else (
        "" if has_display else "Set DISPLAY to a running X server.")
    key = "cap_fix_xwayland" if xwayland else (
        "" if has_display else "cap_fix_display")
    return CapabilitySnapshot(ctx.platform, "x11", xwayland, tuple(
        Capability(name, state, "xwayland" if xwayland else "x11",
                   desktop_wide=not xwayland, detail=detail,
                   recovery=recovery, recovery_key=key)
        for name in (INPUT, CAPTURE, RECORDING, STOP_SHORTCUT)),
        backend_version=ctx.backend_version("x11"))


# --- Wayland: input ---------------------------------------------------------

#: liboeffis is never asked for a restore token by this binding, so consent
#: is per process. A name, not a literal at the call site: it is a state,
#: and a literal there reads to a secret scanner as a hardcoded credential.
_RESTORE_UNSUPPORTED = "unsupported"

_YDOTOOL_RECOVERY = (
    "Install ydotool 1.0 or newer and run ydotoold with access to "
    "/dev/uinput, or install libei and liboeffis to use the desktop portal.")

#: authorisation state -> (capability state, catalogue key of the advice)
_INPUT_STATES = {
    AuthorisationState.NOT_REQUESTED: (CapabilityStatus.NOT_REQUESTED, ""),
    AuthorisationState.REQUESTING: (CapabilityStatus.REQUESTING,
                                    "cap_fix_answer_dialog"),
    AuthorisationState.GRANTED: (CapabilityStatus.AVAILABLE, ""),
    AuthorisationState.DECLINED: (CapabilityStatus.NEEDS_PERMISSION,
                                  "cap_fix_input_consent"),
    AuthorisationState.TIMED_OUT: (CapabilityStatus.NEEDS_PERMISSION,
                                   "cap_fix_input_consent"),
    AuthorisationState.CLOSED: (CapabilityStatus.SESSION_CLOSED, ""),
    AuthorisationState.REVOKED: (CapabilityStatus.REVOKED,
                                 "cap_fix_input_consent"),
}


def _wayland_input(ctx: BackendContext) -> Capability:
    forced = (ctx.environ.get(_INPUT_BACKEND_ENV) or "auto").strip().lower()
    if forced == "cli" or not ctx.library_present("ei"):
        return _ydotool_input(ctx, "")
    record = ctx.authorisations.get(INPUT)
    if record.state is AuthorisationState.FAILED:
        # Not a refusal, so the CLI really is what serves input now.
        return _ydotool_input(ctx, f"libei could not start: {record.detail}")
    if _compositor_changed(ctx, record):
        return Capability(
            INPUT, CapabilityStatus.COMPOSITOR_RESTARTED, "libei",
            detail="the session was granted by a compositor that has since "
                   "been restarted", recovery=INPUT_RECOVERY,
            recovery_key="cap_fix_input_consent",
            authorisation=record.state.value, restore_token=_RESTORE_UNSUPPORTED)
    state, key = _INPUT_STATES[record.state]
    return Capability(
        INPUT, state, "libei", detail=record.detail,
        recovery=INPUT_RECOVERY if key == "cap_fix_input_consent" else (
            "Answer the consent dialog on the desktop." if key else ""),
        recovery_key=key, authorisation=record.state.value,
        restore_token=_RESTORE_UNSUPPORTED)


def _ydotool_input(ctx: BackendContext, detail: str) -> Capability:
    """Input through the ``ydotool`` CLI: no consent, but a daemon to run."""
    if ctx.which(WAYLAND_YDOTOOL):
        return Capability(INPUT, CapabilityStatus.AVAILABLE, "ydotool",
                          detail=detail)
    return Capability(INPUT, CapabilityStatus.NEEDS_SETUP, "ydotool",
                      detail=detail or "ydotool is not on PATH",
                      recovery=_YDOTOOL_RECOVERY,
                      recovery_key="cap_fix_ydotool")


def _compositor_changed(ctx: BackendContext,
                        record: AuthorisationRecord) -> bool:
    """Whether a granted session has outlived the compositor that granted it."""
    if record.state is not AuthorisationState.GRANTED or not record.compositor:
        return False
    now = ctx.compositor(ctx.environ)
    return now is not None and now != record.compositor


# --- Wayland: capture -------------------------------------------------------

_CAPTURE_TOOLS = (WAYLAND_GRIM, WAYLAND_GNOME_SCREENSHOT, WAYLAND_SPECTACLE)

_CAPTURE_STATES = {
    AuthorisationState.NOT_REQUESTED: CapabilityStatus.NOT_REQUESTED,
    AuthorisationState.REQUESTING: CapabilityStatus.REQUESTING,
    AuthorisationState.GRANTED: CapabilityStatus.AVAILABLE,
    AuthorisationState.DECLINED: CapabilityStatus.NEEDS_PERMISSION,
    AuthorisationState.TIMED_OUT: CapabilityStatus.NEEDS_PERMISSION,
    AuthorisationState.FAILED: CapabilityStatus.NEEDS_SETUP,
    AuthorisationState.CLOSED: CapabilityStatus.NOT_REQUESTED,
    AuthorisationState.REVOKED: CapabilityStatus.NEEDS_PERMISSION,
}


def _wayland_capture(ctx: BackendContext) -> Capability:
    if (ctx.environ.get(_CAPTURE_COMMAND_ENV) or "").strip():
        return Capability(CAPTURE, CapabilityStatus.AVAILABLE,
                          f"${_CAPTURE_COMMAND_ENV}")
    for tool in _CAPTURE_TOOLS:
        if ctx.which(tool):
            return Capability(CAPTURE, CapabilityStatus.AVAILABLE, tool)
    if not ctx.session_bus_present():
        return Capability(
            CAPTURE, CapabilityStatus.NEEDS_SETUP, "none",
            detail="no capture tool on PATH and no session bus for the portal",
            recovery=CAPTURE_RECOVERY, recovery_key="cap_fix_capture")
    record = ctx.authorisations.get(CAPTURE)
    state = _CAPTURE_STATES[record.state]
    blocked = state in (CapabilityStatus.NEEDS_PERMISSION,
                        CapabilityStatus.NEEDS_SETUP)
    return Capability(
        CAPTURE, state, "xdg-desktop-portal", detail=record.detail,
        recovery=CAPTURE_RECOVERY if blocked else "",
        recovery_key="cap_fix_capture" if blocked else "",
        authorisation=record.state.value)


# --- Wayland: recording and the stop shortcut -------------------------------

_RECORDING_SCOPE = (
    "Wayland has no global input hook. Actions this program executes are "
    "journalled without one; reading the user's own keyboard and mouse "
    "needs the evdev reader, which is opt-in")
_RECORDING_SETUP = (
    f"Name the devices to read in {RECORD_DEVICES_ENV} (comma-separated "
    "/dev/input/event* paths); list candidates with list_input_devices().")
_RECORDING_PERMISSION = (
    "Give this user read access to the named devices: add it to the "
    "`input` group (then log in again) or install a udev rule. Do not run "
    "the whole program as root for this.")


def _wayland_recording(ctx: BackendContext) -> Capability:
    devices = configured_record_devices(ctx.environ)
    if not devices:
        return Capability(RECORDING, CapabilityStatus.NEEDS_SETUP, "evdev",
                          detail=_RECORDING_SCOPE, recovery=_RECORDING_SETUP,
                          recovery_key="cap_fix_record_setup")
    denied = [path for path in devices if not ctx.readable(path)]
    if denied:
        return Capability(
            RECORDING, CapabilityStatus.NEEDS_PERMISSION, "evdev",
            detail="not readable: " + ", ".join(denied),
            recovery=_RECORDING_PERMISSION,
            recovery_key="cap_fix_record_permission")
    return Capability(RECORDING, CapabilityStatus.AVAILABLE, "evdev",
                      detail=", ".join(devices))


def _wayland_stop_shortcut(ctx: BackendContext) -> Capability:
    if not ctx.session_bus_present():
        return Capability(
            STOP_SHORTCUT, CapabilityStatus.NEEDS_SETUP, "none",
            detail="no session bus, so the GlobalShortcuts portal cannot be "
                   "reached",
            recovery="Stop a running script from the GUI's stop control or "
                     "by ending the process.",
            recovery_key="cap_fix_stop_manual")
    return Capability(
        STOP_SHORTCUT, CapabilityStatus.NOT_REQUESTED,
        "xdg-desktop-portal GlobalShortcuts",
        detail="whether this desktop's portal implements GlobalShortcuts is "
               "only known once a stop-shortcut session is opened; the GUI's "
               "stop control works regardless")


__all__ = [
    "BackendContext", "Capability", "CapabilitySnapshot", "CapabilityStatus",
    "MacFacts", "RECORDING", "STOP_SHORTCUT", "WindowsFacts", "probe_capabilities",
]
