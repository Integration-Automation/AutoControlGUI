"""Passive key/pointer-input and screen-capture capabilities, without native probing or permission requests."""
from __future__ import annotations

from dataclasses import dataclass, field, replace
import os
import shlex
import shutil
import sys
from types import MappingProxyType
from typing import Callable, Mapping, Optional, cast

from je_auto_control.utils.exception.exceptions import AutoControlException

_STATES = frozenset({'available', 'needs_permission', 'needs_dependency', 'unsupported',
                     'unverified', 'paused', 'revoked', 'failed'})
_ENV_KEYS = ('DISPLAY', 'WAYLAND_DISPLAY', 'XDG_SESSION_TYPE', 'DBUS_SESSION_BUS_ADDRESS',
             'JE_AUTOCONTROL_LINUX_DISPLAY_SERVER', 'JE_AUTOCONTROL_WAYLAND_INPUT_BACKEND',
             'JE_AUTOCONTROL_WAYLAND_CAPTURE_COMMAND')
_CAPTURE_TOOLS = ('grim', 'gnome-screenshot', 'spectacle')
_TOOLS = ('ydotool', 'wtype', *_CAPTURE_TOOLS)
_CAPTURE_OVERRIDE = 'JE_AUTOCONTROL_WAYLAND_CAPTURE_COMMAND'


@dataclass(frozen=True)
class CapabilityStatus:
    """One informational capability; availability is a last local observation, never an authority grant.

    ``input`` describes key/pointer events, not the independent wtype text path.
    ``desktop_wide`` describes scope, independently of readiness. Reasons and
    recovery instructions contain no native objects or traceback ownership.
    """

    name: str
    state: str
    backend: str
    reason: str
    recovery: str
    desktop_wide: bool

    def __post_init__(self) -> None:
        if (not isinstance(self.name, str) or not isinstance(self.state, str)
                or self.name not in ('input', 'capture') or self.state not in _STATES):
            raise AutoControlException('invalid capability name or state')
        if not all(isinstance(value, str) and value for value in (self.backend, self.reason, self.recovery)):
            raise AutoControlException('capability descriptions must be non-empty strings')
        if not isinstance(self.desktop_wide, bool):
            raise AutoControlException('capability scope must be boolean')

    def to_dict(self) -> dict[str, object]:
        """Return JSON-compatible metadata without devices, permission tokens or environment values."""
        return {'name': self.name, 'state': self.state, 'backend': self.backend, 'reason': self.reason,
                'recovery': self.recovery, 'desktop_wide': self.desktop_wide}


@dataclass(frozen=True)
class CapabilitySnapshot:
    """Independent capability results for one supplied backend context; no active verification is performed."""

    platform: str
    display_server: str
    input: CapabilityStatus
    capture: CapabilityStatus

    def __post_init__(self) -> None:
        _validate_observations(self.input, self.capture)
        if not isinstance(self.input, CapabilityStatus) or not isinstance(self.capture, CapabilityStatus):
            raise AutoControlException('snapshot requires input and capture statuses')
        if not all(isinstance(value, str) and value for value in (self.platform, self.display_server)):
            raise AutoControlException('snapshot platform/display must be non-empty strings')

    def to_dict(self) -> dict[str, object]:
        """Serialize the passive result; this payload cannot be used as a permission grant."""
        return {'platform': self.platform, 'display_server': self.display_server, 'passive': True,
                'input': self.input.to_dict(), 'capture': self.capture.to_dict()}


@dataclass(frozen=True)
class BackendContext:
    """Detached diagnostic facts, owned by the caller rather than a new mutable global session.

    Construct explicit contexts for adapters/tests or use ``current()`` for
    bounded PATH lookups and cached local native state. Observations are inert
    metadata and never change an operator's real backend or authorization.
    """

    platform: str
    environ: Mapping[str, str] = field(repr=False)
    executables: frozenset[str] = field(default_factory=frozenset, repr=False)
    input_state: Optional[CapabilityStatus] = None
    capture_state: Optional[CapabilityStatus] = None
    native_optional_absent: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.platform, str) or not self.platform:
            raise AutoControlException('capability platform must be a non-empty string')
        _validate_observations(self.input_state, self.capture_state)
        if not isinstance(self.native_optional_absent, bool):
            raise AutoControlException('optional native absence must be boolean')
        object.__setattr__(self, 'environ', _freeze_environment(self.environ))
        object.__setattr__(self, 'executables', _freeze_executables(self.executables))

    @classmethod
    def current(cls) -> BackendContext:
        """Read environment/PATH and an already-loaded sender's nonblocking state; never load or connect it."""
        env = {key: value for key in _ENV_KEYS if (value := os.environ.get(key)) is not None}
        names = set(_TOOLS)
        command = _command_parts(env.get(_CAPTURE_OVERRIDE, ''))
        if command:
            names.add(command[0])
        found = frozenset(name for name in names if shutil.which(name))
        observed, optional = _current_input_state()
        return cls(sys.platform, env, found, input_state=observed, native_optional_absent=optional)


def _freeze_environment(env: Mapping[str, str]) -> Mapping[str, str]:
    if not isinstance(env, Mapping) or not all(
            isinstance(key, str) and isinstance(value, str) for key, value in env.items()):
        raise AutoControlException('capability environment must map strings to strings')
    return MappingProxyType(dict(env))


def _freeze_executables(tools: frozenset[str]) -> frozenset[str]:
    if not isinstance(tools, (set, frozenset)) or not all(isinstance(name, str) and name for name in tools):
        raise AutoControlException('capability executables must be a set of names')
    return frozenset(tools)


def _validate_observations(input_state: Optional[CapabilityStatus],
                           capture_state: Optional[CapabilityStatus]) -> None:
    for name, status in (('input', input_state), ('capture', capture_state)):
        if status is not None and (not isinstance(status, CapabilityStatus) or status.name != name):
            raise AutoControlException('capability observation belongs to a different operation')


def _current_input_state() -> tuple[Optional[CapabilityStatus], bool]:
    native = sys.modules.get('je_auto_control.linux_wayland.libei')
    peek = getattr(native, '_observed_input_state', None)
    if not callable(peek):
        return None, False
    state, fallback = cast(Callable[[], tuple[Optional[str], bool]], peek)()
    if state is None:
        return None, False
    optional = state == 'unavailable' and fallback
    state = 'needs_dependency' if state == 'unavailable' else state
    if state not in _STATES:
        state = 'unverified'
    recovery = _INPUT_RECOVERY.get(state, 'Explicitly invoke the intended input operation to verify readiness.')
    return CapabilityStatus('input', state, 'libei',
                            'Last locally observed native sender state; no events or permissions were polled.',
                            recovery, True), optional


_INPUT_RECOVERY = {
    'needs_permission': 'Review the portal refusal, then explicitly reset/retry the native session to request consent.',
    'needs_dependency': 'Install compatible libei/liboeffis, or explicitly select the configured CLI alternative.',
    'paused': 'Wait for the compositor to resume its devices; no CLI fallback is implied.',
    'revoked': 'Explicitly establish a new authorized native session before sending input.',
    'failed': 'Inspect the native session failure and explicitly reconnect; no CLI fallback is implied.',
}


def _command_parts(template: str) -> list[str]:
    try:
        return shlex.split(template)
    except ValueError:
        return []


def probe_capabilities(context: BackendContext) -> CapabilitySnapshot:
    """Describe input/capture independently without operating devices, loading libraries or requesting permission.

    ``unverified`` distinguishes prerequisites from an established capability.
    Existing local native observations are not refreshed and may become stale;
    every real operation must still enforce its current authority and state.
    """
    if not isinstance(context, BackendContext):
        raise AutoControlException('probe_capabilities requires a BackendContext')
    if context.platform in ('win32', 'darwin'):
        backend = 'win32' if context.platform == 'win32' else 'quartz'
        return _native_desktop(context, backend)
    if not context.platform.startswith(('linux', 'freebsd', 'openbsd', 'netbsd')):
        return _unsupported(context)
    wayland = _is_wayland(context.environ)
    override = context.environ.get('JE_AUTOCONTROL_LINUX_DISPLAY_SERVER', '').strip().lower()
    selected = override if override in ('x11', 'wayland') else ('wayland' if wayland else 'x11')
    if not context.platform.startswith('linux') or selected == 'x11':
        return _x11(context, wayland)
    return CapabilitySnapshot(context.platform, 'wayland', _wayland_input(context), _wayland_capture(context))


def _is_wayland(env: Mapping[str, str]) -> bool:
    return env.get('XDG_SESSION_TYPE', '').strip().lower() == 'wayland' or bool(env.get('WAYLAND_DISPLAY', '').strip())


def _native_desktop(context: BackendContext, backend: str) -> CapabilitySnapshot:
    statuses = [_observation(context, name, backend) or CapabilityStatus(
        name, 'unverified', backend, 'Backend selected; OS permission and desktop access have not been tested.',
        'Explicitly run the intended operation; review OS permissions if it is denied.', True)
        for name in ('input', 'capture')]
    return CapabilitySnapshot(context.platform, backend, *statuses)


def _unsupported(context: BackendContext) -> CapabilitySnapshot:
    statuses = [CapabilityStatus(name, 'unsupported', 'none', 'No supported desktop backend for this platform.',
                                 'Use a supported Windows, macOS, Linux or BSD desktop.', False)
                for name in ('input', 'capture')]
    return CapabilitySnapshot(context.platform, 'none', *statuses)


def _x11(context: BackendContext, wayland: bool) -> CapabilitySnapshot:
    present = bool(context.environ.get('DISPLAY', '').strip())
    state = 'unverified' if present else 'needs_dependency'
    reason = 'XWayland covers X11 clients only; native Wayland windows are outside its scope.' if wayland else (
        'DISPLAY is configured; no X11 connection was attempted.' if present else 'DISPLAY is not configured.')
    statuses = [_observation(context, name, 'x11') or CapabilityStatus(
        name, state, 'x11', reason, 'Provide a reachable X11 display and explicitly verify the intended operation.',
        not wayland) for name in ('input', 'capture')]
    scoped = [replace(status, desktop_wide=status.desktop_wide and not wayland) for status in statuses]
    return CapabilitySnapshot(context.platform, 'x11', *scoped)


def _observation(context: BackendContext, name: str, backend: str) -> Optional[CapabilityStatus]:
    observed = context.input_state if name == 'input' else context.capture_state
    return observed if observed is not None and observed.backend == backend else None


def _wayland_input(context: BackendContext) -> CapabilityStatus:
    choice = context.environ.get('JE_AUTOCONTROL_WAYLAND_INPUT_BACKEND', '').strip().lower()
    if choice == 'cli':
        return _cli_input(context)
    observed = _observation(context, 'input', 'libei')
    fallback = _optional_cli(context, choice, observed)
    if observed is not None and not fallback:
        return observed
    if fallback:
        return _cli_input(context)
    return CapabilityStatus('input', 'unverified', 'libei' if choice == 'libei' else 'auto',
                            'Native loadability, authorization and protocol readiness were not probed.',
                            'Explicitly invoke key/pointer input to verify the native session.', True)


def _optional_cli(context: BackendContext, choice: str, observed: Optional[CapabilityStatus]) -> bool:
    return (choice != 'libei' and context.native_optional_absent
            and (observed is None or observed.state == 'needs_dependency'))


def _cli_input(context: BackendContext) -> CapabilityStatus:
    installed = 'ydotool' in context.executables
    return CapabilityStatus('input', 'unverified' if installed else 'needs_dependency', 'ydotool',
                            'CLI client found; daemon/access not tested.' if installed else 'ydotool is not found.',
                            'Configure ydotoold and verify key/pointer input; wtype text is separate.', True)


def _wayland_capture(context: BackendContext) -> CapabilityStatus:
    template = context.environ.get(_CAPTURE_OVERRIDE, '').strip()
    if template:
        return _custom_capture(context, template)
    for tool in _CAPTURE_TOOLS:
        if tool in context.executables:
            return _observation(context, 'capture', tool) or CapabilityStatus(
                'capture', 'unverified', tool, 'Executable found; compositor compatibility/permission not tested.',
                'Use the helper matching the compositor and explicitly verify capture.', True)
    if context.environ.get('DBUS_SESSION_BUS_ADDRESS', '').strip():
        return _observation(context, 'capture', 'portal') or CapabilityStatus(
            'capture', 'unverified', 'portal', 'Session bus configured; portal service and consent were not checked.',
            'Explicitly request a screenshot and respond to the portal dialog if shown.', True)
    return CapabilityStatus('capture', 'needs_dependency', 'none', 'No capture helper or session bus is configured.',
                            'Install a compositor-compatible helper or configure the desktop session bus.', True)


def _custom_capture(context: BackendContext, template: str) -> CapabilityStatus:
    parts = _command_parts(template)
    if not parts or not any('{output}' in part for part in parts):
        return CapabilityStatus('capture', 'failed', 'custom-command', 'The explicit capture command is malformed.',
                                'Supply a correctly quoted argv template containing the {output} placeholder.', True)
    installed = parts[0] in context.executables
    return _observation(context, 'capture', 'custom-command') or CapabilityStatus(
        'capture', 'unverified' if installed else 'needs_dependency', 'custom-command',
        'Command found; it was not executed.' if installed else 'The explicit capture executable was not found.',
        'Check the explicit executable and deliberately verify its output; no alternate provider is selected.', True)


__all__ = ['BackendContext', 'CapabilityStatus', 'CapabilitySnapshot', 'probe_capabilities']
