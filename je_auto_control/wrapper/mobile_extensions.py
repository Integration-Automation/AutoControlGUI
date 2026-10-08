"""App lifecycle and the optional device extensions, for any mobile session.

Two layers:

* **Lifecycle and alerts** — :func:`launch_app`, :func:`stop_app`,
  :func:`app_state`, :func:`wait_for_app`, :func:`accept_alert`,
  :func:`dismiss_alert` — work on every :class:`DeviceSession`.
* **Extensions** — install, files, clipboard, recording — are the features a
  backend may simply not have. :class:`MobileExtension` is their contract and
  :func:`mobile_extension` returns the implementation for a session. A feature
  the backend lacks reports ``needs_dependency`` with the reason, and calling
  it raises :class:`DeviceUnsupportedError`; nothing is borrowed from another
  platform's tooling to make it look supported.

An adapter for a host-side tool is plugged in with
:func:`register_mobile_extension`. It is asked first, and the built-in
extension covers whatever it does not provide.
"""
from __future__ import annotations

import threading
from time import monotonic
from typing import Any, Callable, Dict, Optional, Protocol, runtime_checkable

from je_auto_control.wrapper.device_context import (
    MOBILE_PLATFORMS, AppState, DeviceCapability, DeviceError, DeviceSession,
    DeviceTimeoutError,
)

#: The features an extension may or may not provide.
EXTENSION_FEATURES = ("install", "files", "clipboard", "recording")
_WAIT_POLL_S = 0.25


@runtime_checkable
class MobileExtension(Protocol):
    """Install, files, clipboard and recording for one device.

    ``capability(feature)`` answers for each of :data:`EXTENSION_FEATURES`
    without touching the device. A method whose feature is not ``available``
    raises :class:`DeviceUnsupportedError` carrying the same reason.
    """

    name: str

    def capability(self, feature: str) -> DeviceCapability:
        """Whether ``feature`` can be used, and if not, what is missing."""

    def install_app(self, source: str) -> str:
        """Install the app package at host path ``source``."""

    def push_file(self, local_path: str, remote_path: str) -> str:
        """Copy a host file to the device."""

    def pull_file(self, remote_path: str, local_path: str) -> str:
        """Copy a device file to the host."""

    def get_clipboard(self) -> str:
        """The device clipboard's text."""

    def set_clipboard(self, text: str) -> None:
        """Put ``text`` on the device clipboard."""

    def start_recording(self, remote_path: str = ..., time_limit_s: int = ...) -> str:
        """Start recording the screen."""

    def stop_recording(self, local_path: str, remote_path: str = ...) -> str:
        """Stop recording and save the result to host path ``local_path``."""


ExtensionFactory = Callable[[DeviceSession], MobileExtension]

_FACTORIES: Dict[str, ExtensionFactory] = {}
_FACTORIES_LOCK = threading.Lock()

#: Which feature each extension method belongs to.
_METHOD_FEATURES = {
    "install_app": "install", "push_file": "files", "pull_file": "files",
    "get_clipboard": "clipboard", "set_clipboard": "clipboard",
    "start_recording": "recording", "stop_recording": "recording",
}


def register_mobile_extension(platform: str, factory: Optional[ExtensionFactory]) -> None:
    """Plug in an adapter for ``platform``; ``None`` removes it.

    ``factory(session)`` returns a :class:`MobileExtension`. It is how iOS
    gets install / files / recording, which WebDriverAgent does not provide.
    """
    if platform not in MOBILE_PLATFORMS:
        raise DeviceError(f"unknown device platform {platform!r}")
    with _FACTORIES_LOCK:
        if factory is None:
            _FACTORIES.pop(platform, None)
        else:
            _FACTORIES[platform] = factory


class _Layered:
    """An adapter first, the built-in extension for what the adapter lacks."""

    def __init__(self, adapter: MobileExtension, builtin: MobileExtension) -> None:
        self._adapter = adapter
        self._builtin = builtin
        self.name = f"{adapter.name}+{builtin.name}"

    def _pick(self, feature: str) -> MobileExtension:
        return self._adapter if self._adapter.capability(feature).available else self._builtin

    def capability(self, feature: str) -> DeviceCapability:
        """The adapter's answer when it provides ``feature``, else the built-in's."""
        return self._pick(feature).capability(feature)

    def __getattr__(self, method: str) -> Any:
        feature = _METHOD_FEATURES.get(method)
        if feature is None:
            raise AttributeError(method)
        return getattr(self._pick(feature), method)


def mobile_extension(session: DeviceSession) -> MobileExtension:
    """The extension for ``session``: a registered adapter layered over the built-in one."""
    builtin: MobileExtension = session.builtin_extension()
    with _FACTORIES_LOCK:
        factory = _FACTORIES.get(session.platform)
    if factory is None:
        return builtin
    layered: MobileExtension = _Layered(factory(session), builtin)
    return layered


def launch_app(session: DeviceSession, app_id: str) -> AppState:
    """Launch ``app_id`` (Android package, iOS bundle id); returns its state afterwards."""
    session.launch_app(app_id)
    return session.app_state(app_id)


def stop_app(session: DeviceSession, app_id: str) -> AppState:
    """Stop ``app_id``; returns its state afterwards."""
    session.stop_app(app_id)
    return session.app_state(app_id)


def app_state(session: DeviceSession, app_id: str) -> AppState:
    """Whether ``app_id`` is installed, running, and in front."""
    return session.app_state(app_id)


def wait_for_app(session: DeviceSession, app_id: str, *, timeout_s: float = 10.0,
                 state: AppState = AppState.FOREGROUND) -> AppState:
    """Wait until ``app_id`` reaches ``state``; raises :class:`DeviceTimeoutError` if it does not.

    Cancelling the session ends the wait at the next poll.
    """
    wanted = AppState(state)
    deadline = monotonic() + float(timeout_s)
    while True:
        current = session.app_state(app_id)
        if current == wanted:
            return current
        if monotonic() >= deadline:
            raise DeviceTimeoutError(
                f"{app_id} is {current.value}, not {wanted.value}, after {float(timeout_s):g}s")
        if session.wait_cancelled(_WAIT_POLL_S):
            session.check_usable()


def accept_alert(session: DeviceSession) -> str:
    """Accept the alert or system dialog that is showing; returns what was pressed or read."""
    return session.answer_alert(True)


def dismiss_alert(session: DeviceSession) -> str:
    """Dismiss the alert or system dialog that is showing."""
    return session.answer_alert(False)


__all__ = [
    "EXTENSION_FEATURES", "ExtensionFactory", "MobileExtension", "accept_alert",
    "app_state", "dismiss_alert", "launch_app", "mobile_extension",
    "register_mobile_extension", "stop_app", "wait_for_app",
]
