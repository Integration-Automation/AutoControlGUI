"""Explicit device contexts for Android and iOS automation.

The mobile backends grew up around process-wide defaults: one cached
``AdbClient`` per serial, one default ``UIAutomatorDevice``, one default
``IOSDevice``. That is fine for one phone on a desk and wrong for a device
matrix, where two workers must never be able to reach each other's device by
leaving an argument out.

A :class:`DeviceContext` is the frozen identity and configuration of one
device; :func:`open_device` turns it into a :class:`DeviceSession` that owns
its own transport, its own timeout and its own cancellation signal. Nothing in
a session reads or writes a module-level default, and a session bound with
:func:`use_device` is visible only to the thread (and context) that bound it.

Every error a session raises derives from :class:`DeviceError`, itself an
``AutoControlException``, so the executor's containment boundaries see one
family whichever backend failed.
"""
from __future__ import annotations

import threading
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from enum import Enum
from time import monotonic
from typing import Any, Callable, Dict, Iterator, Mapping, Optional, Tuple, TypeVar, Union

from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils.thread_bound import ThreadBoundVar

PLATFORM_ANDROID = "android"
PLATFORM_IOS = "ios"
MOBILE_PLATFORMS = (PLATFORM_ANDROID, PLATFORM_IOS)

STATE_AVAILABLE = "available"
STATE_NEEDS_PERMISSION = "needs_permission"
STATE_NEEDS_DEPENDENCY = "needs_dependency"
STATE_UNSUPPORTED = "unsupported"

#: Every capability a session reports, in report order.
CAPABILITY_NAMES = (
    "input", "unicode_text", "multi_touch", "screenshot", "ui_tree",
    "app_lifecycle", "alerts", "install", "files", "clipboard", "recording",
)

DEFAULT_TIMEOUT_S = 30.0
_POLL_S = 0.02

_Result = TypeVar("_Result")


class DeviceError(AutoControlException, RuntimeError):
    """Base of every error a mobile device session raises."""


class DeviceUnavailableError(DeviceError):
    """The backend SDK, the transport or the device itself cannot be reached."""


class DevicePermissionError(DeviceError):
    """The device refused the host (USB debugging not authorised, no udev access)."""


class DeviceTimeoutError(DeviceError, TimeoutError):
    """A device call outlived the session's timeout; its outcome is unknown."""


class DeviceCancelledError(DeviceError):
    """The session was cancelled; nothing more is sent to the device."""


class DeviceClosedError(DeviceError):
    """The session was closed (or broken by a timeout) and must be reopened."""


class AlertNotPresentError(DeviceError, LookupError):
    """No alert or system dialog is showing to accept or dismiss."""


class AppState(str, Enum):
    """Where an app is in its lifecycle. Compares equal to its string value."""

    NOT_INSTALLED = "not_installed"
    NOT_RUNNING = "not_running"
    BACKGROUND = "background"
    FOREGROUND = "foreground"


class DeviceUnsupportedError(DeviceError):
    """The backend cannot do what was asked; says why and what to use instead."""

    def __init__(self, message: str, *, reason: str = "",
                 alternative: str = "") -> None:
        super().__init__(message)
        self.reason = reason or message
        self.alternative = alternative


@dataclass(frozen=True)
class DeviceCapability:
    """Whether one feature can be used on one device, and if not, why."""

    name: str
    state: str
    reason: str = ""
    alternative: str = ""

    @property
    def available(self) -> bool:
        """Whether the feature can be used right now."""
        return self.state == STATE_AVAILABLE

    def to_dict(self) -> Dict[str, Any]:
        """JSON-safe form for executor, MCP and GUI consumers."""
        return asdict(self)


@dataclass(frozen=True)
class DeviceSetupReport:
    """What a device's backend is, which version answered, and what it can do.

    ``state`` and ``reason`` are those of the ``input`` capability: whether
    the device can be driven at all, and if not, what to fix first.
    """

    platform: str
    device_id: str
    backend: str
    backend_version: str = ""
    os_version: str = ""
    state: str = STATE_AVAILABLE
    reason: str = ""
    capabilities: Mapping[str, DeviceCapability] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """JSON-safe form for executor, MCP and GUI consumers."""
        return {
            "platform": self.platform, "device_id": self.device_id,
            "backend": self.backend, "backend_version": self.backend_version,
            "os_version": self.os_version, "state": self.state, "reason": self.reason,
            "capabilities": {name: capability.to_dict()
                             for name, capability in self.capabilities.items()},
        }


@dataclass(frozen=True)
class DeviceContext:
    """The identity and configuration of one device.

    ``device_id`` is the adb serial on Android and the WebDriverAgent URL on
    iOS; empty means "whatever the backend picks when only one is attached".
    """

    platform: str
    device_id: str = ""
    adb_path: Optional[str] = None
    timeout_s: float = DEFAULT_TIMEOUT_S
    label: str = ""

    def __post_init__(self) -> None:
        if self.platform not in MOBILE_PLATFORMS:
            raise DeviceError(
                f"unknown device platform {self.platform!r}; expected one of {MOBILE_PLATFORMS}")
        if not isinstance(self.timeout_s, (int, float)) or self.timeout_s <= 0:
            raise DeviceError(f"timeout_s must be a positive number, got {self.timeout_s!r}")

    @property
    def name(self) -> str:
        """A label for reports: the explicit label, else the id, else the platform."""
        return self.label or self.device_id or f"{self.platform}-default"

    @classmethod
    def from_spec(cls, spec: Mapping[str, Any]) -> Optional["DeviceContext"]:
        """Build a context from a device-matrix spec; ``None`` if it is not a mobile one.

        A spec is ``{"platform": "android", "serial": ...}`` or
        ``{"platform": "ios", "url": ...}``, optionally with ``adb_path``,
        ``timeout_s`` and ``label``.
        """
        platform = str(spec.get("platform", "")).lower()
        if platform not in MOBILE_PLATFORMS:
            return None
        key = "serial" if platform == PLATFORM_ANDROID else "url"
        adb_path = spec.get("adb_path")
        return cls(
            platform=platform,
            device_id=str(spec.get(key) or spec.get("device_id") or ""),
            adb_path=str(adb_path) if adb_path else None,
            timeout_s=float(spec.get("timeout_s") or DEFAULT_TIMEOUT_S),
            label=str(spec.get("label") or ""),
        )


def _non_negative(name: str, value: float) -> None:
    if not isinstance(value, (int, float)) or value < 0:
        raise DeviceError(f"{name} must be a non-negative number, got {value!r}")


@dataclass(frozen=True)
class Tap:
    """A single tap at ``(x, y)`` in device input coordinates."""

    x: int
    y: int


@dataclass(frozen=True)
class LongPress:
    """Press and hold at ``(x, y)`` for ``duration_s`` seconds."""

    x: int
    y: int
    duration_s: float = 1.0

    def __post_init__(self) -> None:
        _non_negative("duration_s", self.duration_s)


@dataclass(frozen=True)
class Swipe:
    """A quick stroke from ``(x1, y1)`` to ``(x2, y2)`` (a scroll or a flick)."""

    x1: int
    y1: int
    x2: int
    y2: int
    duration_s: float = 0.25

    def __post_init__(self) -> None:
        _non_negative("duration_s", self.duration_s)


@dataclass(frozen=True)
class Drag:
    """Press at ``(x1, y1)``, hold ``hold_s`` so the item lifts, move to ``(x2, y2)``."""

    x1: int
    y1: int
    x2: int
    y2: int
    hold_s: float = 0.5
    duration_s: float = 0.5

    def __post_init__(self) -> None:
        _non_negative("hold_s", self.hold_s)
        _non_negative("duration_s", self.duration_s)


@dataclass(frozen=True)
class Pinch:
    """A two-finger pinch about ``(x, y)``: ``scale`` above 1 zooms in, below 1 zooms out.

    ``span`` is the distance between the fingers at the wide end of the motion.
    """

    x: int
    y: int
    scale: float
    duration_s: float = 0.5
    span: int = 400

    def __post_init__(self) -> None:
        _non_negative("duration_s", self.duration_s)
        if not isinstance(self.scale, (int, float)) or self.scale <= 0 or self.scale == 1:
            raise DeviceError(f"pinch scale must be positive and not 1, got {self.scale!r}")
        if self.span <= 0:
            raise DeviceError(f"pinch span must be positive, got {self.span!r}")


Gesture = Union[Tap, LongPress, Swipe, Drag, Pinch]


class _Call:
    """One device call running on its own thread, so the caller can stop waiting."""

    def __init__(self, function: Callable[[], Any]) -> None:
        self._function = function
        self.done = threading.Event()
        self.result: Any = None
        self.error: Optional[BaseException] = None

    def run(self) -> None:
        """Run the call and keep whatever it returned or raised."""
        try:
            self.result = self._function()
        except BaseException as error:  # NOSONAR python:S5754  # noqa: BLE001  # reason: re-raised by invoke
            self.error = error
        finally:
            self.done.set()


class DeviceSession:
    """One open device: its transport, its timeout and its cancellation signal.

    Subclasses add the platform's operations and route every device call
    through :meth:`invoke`, which is what makes timeout, cancellation and the
    closed state behave the same on ADB, uiautomator2 and WebDriverAgent.
    """

    def __init__(self, context: DeviceContext) -> None:
        self._context = context
        self._cancel = threading.Event()
        self._closed = threading.Event()
        self._state_lock = threading.Lock()
        self._broken_reason = ""

    @property
    def context(self) -> DeviceContext:
        """The context this session was opened from."""
        return self._context

    @property
    def platform(self) -> str:
        """``"android"`` or ``"ios"``."""
        return self._context.platform

    @property
    def device_id(self) -> str:
        """The adb serial or WebDriverAgent URL (may be empty)."""
        return self._context.device_id

    @property
    def cancelled(self) -> bool:
        """Whether :meth:`cancel` was called."""
        return self._cancel.is_set()

    @property
    def connected(self) -> bool:
        """Whether the session still accepts operations."""
        return not self._closed.is_set() and not self._cancel.is_set()

    def cancel(self) -> None:
        """Stop this session: waiting callers return at once and nothing more is sent.

        Only this session is affected. A call already on its way to the device
        cannot be recalled; the session stops waiting for it and refuses every
        later one, so a cancelled run cannot keep typing into the device.
        """
        self._cancel.set()

    def close(self) -> None:
        """Release what the session owns. Safe to call more than once."""
        with self._state_lock:
            if self._closed.is_set():
                return
            self._closed.set()
        self._release()

    def __enter__(self) -> "DeviceSession":
        return self

    def __exit__(self, *_exc: Any) -> None:
        self.close()

    def capabilities(self) -> Dict[str, DeviceCapability]:
        """What this device can do right now. Sends no input to the device."""
        raise NotImplementedError

    def setup_report(self) -> DeviceSetupReport:
        """Backend, versions and capabilities, for checking a setup. Sends no input."""
        capabilities = self.capabilities()
        ready = capabilities["input"]
        backend, backend_version, os_version = self.invoke(
            "setup_report", lambda: self._versions(ready.available))
        return DeviceSetupReport(
            platform=self.platform, device_id=self.device_id, backend=backend,
            backend_version=backend_version, os_version=os_version,
            state=ready.state, reason=ready.reason, capabilities=capabilities)

    def _versions(self, ready: bool) -> Tuple[str, str, str]:
        """``(backend, backend version, OS version)``; empty where it cannot be read."""
        raise NotImplementedError

    def capture(self) -> Any:
        """The current screen as a :class:`~je_auto_control.wrapper.device_frame.DeviceFrame`."""
        raise NotImplementedError

    def type_text(self, text: str) -> None:
        """Type ``text`` into the focused field, or raise if the device cannot receive it."""
        raise NotImplementedError

    def press_key(self, key: str) -> None:
        """Press one hardware or system key."""
        raise NotImplementedError

    def perform(self, gesture: Gesture) -> None:
        """Perform one touch gesture, in device input coordinates."""
        handler = self._gesture_handlers().get(type(gesture))
        if handler is None:
            raise DeviceUnsupportedError(
                f"{type(gesture).__name__} is not a gesture this session can perform",
                alternative="use Tap, LongPress, Swipe, Drag or Pinch")
        self.invoke(type(gesture).__name__, lambda: handler(gesture))

    def _gesture_handlers(self) -> Dict[type, Callable[[Any], None]]:
        """Gesture type to the backend call that performs it; overridden per platform."""
        return {}

    def launch_app(self, app_id: str) -> None:
        """Launch an app (Android package, iOS bundle id)."""
        raise NotImplementedError

    def stop_app(self, app_id: str) -> None:
        """Stop an app."""
        raise NotImplementedError

    def app_state(self, app_id: str) -> AppState:
        """Where an app is in its lifecycle."""
        raise NotImplementedError

    def answer_alert(self, accept: bool) -> str:
        """Accept or dismiss the alert that is showing; returns what was pressed or read."""
        raise NotImplementedError

    def builtin_extension(self) -> Any:
        """The backend's own install / files / clipboard / recording implementation."""
        raise NotImplementedError

    def wait_cancelled(self, timeout_s: float) -> bool:
        """Sleep up to ``timeout_s``; ``True`` as soon as the session is cancelled."""
        return self._cancel.wait(timeout_s)

    def invoke(self, operation: str, function: Callable[[], _Result],
               *, timeout_s: Optional[float] = None) -> _Result:
        """Run one device call under the session's timeout and cancel signal.

        A call that outlives the timeout leaves the device in a state nobody
        observed, so the session is closed rather than left to send the next
        step on top of it.
        """
        self.check_usable()
        budget = float(timeout_s) if timeout_s is not None else float(self._context.timeout_s)
        call = _Call(function)
        threading.Thread(target=call.run, name=f"device-{self._context.name}",
                         daemon=True).start()
        deadline = monotonic() + budget
        while not call.done.wait(_POLL_S):
            if self._cancel.is_set():
                raise DeviceCancelledError(
                    f"{operation} on {self._context.name}: session cancelled")
            if monotonic() >= deadline:
                self._break(f"{operation} did not finish within {budget:g}s")
                raise DeviceTimeoutError(
                    f"{operation} on {self._context.name} timed out after {budget:g}s; "
                    "the session is closed because the device state is unknown")
        if call.error is not None:
            raise call.error
        return call.result

    def check_usable(self) -> None:
        """Raise unless the session can still send operations."""
        if self._cancel.is_set():
            raise DeviceCancelledError(f"session for {self._context.name} was cancelled")
        if self._closed.is_set():
            detail = f" ({self._broken_reason})" if self._broken_reason else ""
            raise DeviceClosedError(f"session for {self._context.name} is closed{detail}")

    def _break(self, reason: str) -> None:
        self._broken_reason = reason
        self.close()

    def _release(self) -> None:
        """Drop the transports this session owns; overridden per platform."""


def open_device(context: DeviceContext, **transports: Any) -> DeviceSession:
    """Open a session for ``context``.

    Nothing is sent to the device here: the transport is built on first use,
    so opening a session needs neither ``adb`` nor a reachable WebDriverAgent.
    ``transports`` lets a caller (or a test) hand in an already-built client —
    ``adb=`` / ``ui_device=`` on Android, ``device=`` on iOS — which the
    session then uses but does not own.
    """
    if not isinstance(context, DeviceContext):
        raise DeviceError(f"open_device needs a DeviceContext, got {type(context).__name__}")
    if context.platform == PLATFORM_ANDROID:
        from je_auto_control.android.session import AndroidSession
        return AndroidSession(context, **transports)
    from je_auto_control.ios.session import IOSSession
    return IOSSession(context, **transports)


_BOUND: "ThreadBoundVar[Optional[DeviceSession]]" = ThreadBoundVar(
    "je_auto_control_device_session", None)


@contextmanager
def use_device(session: DeviceSession) -> Iterator[DeviceSession]:
    """Make ``session`` the device that mobile commands without an address target.

    The binding is visible only to the thread that made it: two device-matrix
    workers each see their own device, and a thread started inside the block
    does not reach the device by leaving an address out -- also on a
    free-threaded build, where a new thread inherits its creator's context
    variables.
    """
    token = _BOUND.set(session)
    try:
        yield session
    finally:
        _BOUND.reset(token)


def bound_session(platform: str, device_id: Optional[str] = None) -> Optional[DeviceSession]:
    """The session bound by :func:`use_device` when it is the one being addressed.

    ``None`` when nothing is bound, the platform differs, or ``device_id``
    names another device — the caller then opens its own.
    """
    session = _BOUND.get()
    if session is None or session.platform != platform:
        return None
    if device_id and device_id != session.device_id:
        return None
    return session


__all__ = [
    "AlertNotPresentError", "AppState", "CAPABILITY_NAMES", "DEFAULT_TIMEOUT_S",
    "DeviceCancelledError", "DeviceCapability",
    "DeviceClosedError", "DeviceContext", "DeviceError", "DevicePermissionError",
    "DeviceSetupReport",
    "DeviceSession", "DeviceTimeoutError", "DeviceUnavailableError",
    "DeviceUnsupportedError", "Drag", "Gesture", "LongPress", "MOBILE_PLATFORMS",
    "PLATFORM_ANDROID", "PLATFORM_IOS", "Pinch", "STATE_AVAILABLE",
    "STATE_NEEDS_DEPENDENCY", "STATE_NEEDS_PERMISSION", "STATE_UNSUPPORTED",
    "Swipe", "Tap", "bound_session", "open_device", "use_device",
]
