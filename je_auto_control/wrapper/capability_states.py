"""Turn Windows / macOS session facts into capability states.

:mod:`capability_probes` reads the facts; this module judges them. Kept apart
so the judgement is a pure function of a ``WindowsFacts`` / ``MacFacts`` value
and can be tested on any machine. Each function returns the keyword arguments
of one :class:`~je_auto_control.wrapper.capabilities.Capability` per
capability, in the order input, capture, recording, stop shortcut.

The rule throughout: a fact that could not be read gives ``unknown``, never
``available``; an obstacle names what to do about it.

Imports no ``PySide6``.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from je_auto_control.wrapper.capability_probes import MacFacts, WindowsFacts

_INPUT, _CAPTURE, _RECORDING, _STOP = "input", "capture", "recording", "stop_shortcut"
_NAMES = (_INPUT, _CAPTURE, _RECORDING, _STOP)
_AVAILABLE, _UNKNOWN = "available", "unknown"
_NEEDS_PERMISSION, _NEEDS_SETUP, _UNSUPPORTED = (
    "needs_permission", "needs_setup", "unsupported")

Fields = Dict[str, Any]

_UNPROBED = ("permission for this platform is granted outside the process "
             "and is not probed here")

_SESSION_ZERO = ("this process runs in session 0 (a service), which has no "
                 "interactive desktop to send input to or read pixels from")
_SESSION_ZERO_FIX = ("Run it in the signed-in user's session -- a scheduled "
                     "task set to 'run only when user is logged on', not a "
                     "service.")
_LOCKED = ("the workstation is locked or a secure desktop (UAC, Ctrl+Alt+Del) "
           "is showing: input desktop {name!r}")
_LOCKED_FIX = "Unlock the session, or answer the prompt that is on screen."
_LOW_INTEGRITY = ("the process runs at {level} integrity; Windows drops input "
                  "it sends to normal windows (UIPI)")
_LOW_INTEGRITY_FIX = "Start it from a normal (medium-integrity) process."
_UIPI_HINT = ("{level} integrity: input sent to a window of an elevated "
              "(administrator) process is dropped by UIPI -- run elevated to "
              "reach those windows")
_CAPTURE_FIX = ("A disconnected remote-desktop session has no screen: keep "
                "the session connected, or move it to the console.")
_HOOK_DENIED = ("the input desktop cannot be opened with hook access, which a "
                "low-level keyboard / mouse hook needs")
_NOT_READ = "could not be read from this process"


def _state(name: str, state: str, backend: str, detail: str = "", recovery: str = "",
           key: str = "") -> Fields:
    from je_auto_control.wrapper.capabilities import CapabilityStatus
    return {"name": name, "state": CapabilityStatus(state), "backend": backend,
            "detail": detail, "recovery": recovery, "recovery_key": key}


def unprobed_capabilities(backend: str) -> List[Fields]:
    """Four ``unknown`` capabilities for a platform with nothing to probe."""
    return [_state(name, _UNKNOWN, backend, _UNPROBED) for name in _NAMES]


def _windows_blocker(name: str, facts: WindowsFacts) -> Optional[Fields]:
    """What stops every capability alike: session 0, or a locked workstation."""
    if facts.session_id == 0:
        return _state(name, _UNSUPPORTED, "win32", _SESSION_ZERO, _SESSION_ZERO_FIX,
                      "cap_fix_win_session0")
    if facts.secure_desktop:
        return _state(name, _NEEDS_PERMISSION, "win32",
                      _LOCKED.format(name=facts.input_desktop), _LOCKED_FIX,
                      "cap_fix_win_locked")
    return None


def _windows_input(facts: WindowsFacts) -> Fields:
    if facts.integrity in ("untrusted", "low"):
        return _state(_INPUT, _NEEDS_PERMISSION, "win32",
                      _LOW_INTEGRITY.format(level=facts.integrity), _LOW_INTEGRITY_FIX,
                      "cap_fix_win_integrity")
    if facts.integrity is None or facts.session_id is None or facts.input_desktop is None:
        return _state(_INPUT, _UNKNOWN, "win32",
                      f"integrity level, session or input desktop {_NOT_READ}")
    hint = _UIPI_HINT.format(level=facts.integrity) if facts.integrity == "medium" else ""
    return _state(_INPUT, _AVAILABLE, "win32", hint)


def _windows_capture(facts: WindowsFacts) -> Fields:
    if facts.capture_ok is None:
        return _state(_CAPTURE, _UNKNOWN, "win32", f"a screen copy {_NOT_READ}")
    if facts.capture_ok:
        return _state(_CAPTURE, _AVAILABLE, "win32")
    return _state(_CAPTURE, _NEEDS_SETUP, "win32",
                  f"a 1x1 screen copy failed: {facts.capture_error or 'no reason given'}",
                  _CAPTURE_FIX, "cap_fix_win_capture")


def _windows_hooks(name: str, facts: WindowsFacts, note: str) -> Fields:
    if facts.hook_access is None or facts.input_desktop is None:
        return _state(name, _UNKNOWN, "win32", f"hook access to the input desktop {_NOT_READ}")
    if not facts.hook_access:
        return _state(name, _NEEDS_PERMISSION, "win32", _HOOK_DENIED, _LOCKED_FIX,
                      "cap_fix_win_locked")
    return _state(name, _AVAILABLE, "win32", note)


def windows_capabilities(facts: WindowsFacts) -> List[Fields]:
    """Input, capture, recording and the stop shortcut for a Windows session."""
    own = {
        _INPUT: lambda: _windows_input(facts),
        _CAPTURE: lambda: _windows_capture(facts),
        _RECORDING: lambda: _windows_hooks(
            _RECORDING, facts, "hook access checked; no hook was installed"),
        _STOP: lambda: _windows_hooks(
            _STOP, facts, "hook access checked; no hotkey was registered"),
    }
    return [_windows_blocker(name, facts) or own[name]() for name in _NAMES]


_MAC_PANES = {
    _INPUT: ("Accessibility", "cap_fix_mac_accessibility"),
    _CAPTURE: ("Screen Recording", "cap_fix_mac_screen_recording"),
    _RECORDING: ("Input Monitoring", "cap_fix_mac_input_monitoring"),
    _STOP: ("Input Monitoring", "cap_fix_mac_input_monitoring"),
}
_MAC_FIX = ("System Settings > Privacy & Security > {pane}: enable the "
            "application that runs Python (Terminal, the IDE), then restart it.")


def _mac_state(name: str, granted: Optional[bool], call: str) -> Fields:
    pane, key = _MAC_PANES[name]
    if granted is None:
        return _state(name, _UNKNOWN, "quartz",
                      f"{call} is not available here, so {pane} was not checked")
    if granted:
        return _state(name, _AVAILABLE, "quartz", f"{pane} is granted ({call})")
    return _state(name, _NEEDS_PERMISSION, "quartz", f"{pane} is not granted ({call})",
                  _MAC_FIX.format(pane=pane), key)


def mac_capabilities(facts: MacFacts) -> List[Fields]:
    """Input, capture, recording and the stop shortcut for a macOS session."""
    return [
        _mac_state(_INPUT, facts.accessibility, "AXIsProcessTrusted"),
        _mac_state(_CAPTURE, facts.screen_recording, "CGPreflightScreenCaptureAccess"),
        _mac_state(_RECORDING, facts.input_monitoring, "CGPreflightListenEventAccess"),
        _mac_state(_STOP, facts.input_monitoring, "CGPreflightListenEventAccess"),
    ]


__all__ = ["mac_capabilities", "unprobed_capabilities", "windows_capabilities"]
