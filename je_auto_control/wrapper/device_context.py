"""Frozen mobile identities and independently owned, lazy execution bindings."""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict
import importlib.util
import shutil
import sys
import threading
from typing import Any, Iterator, Mapping, Optional, Sequence

from je_auto_control.wrapper._mobile_models import DeviceContext, DeviceSessionError
from je_auto_control.wrapper import _mobile_operations
from je_auto_control.wrapper.device_frame import DeviceFrame
from je_auto_control.wrapper.mobile_gesture import Gesture
from je_auto_control.wrapper._mobile_binding import bind_device, bound_device
from je_auto_control.wrapper.capabilities import CapabilityStatus
from je_auto_control.android.client import UIAutomatorDevice
from je_auto_control.ios.client import IOSDevice
from je_auto_control.wrapper._mobile_adb import OwnedAdbClient


def _sdk_present(name: str) -> bool:
    if name in sys.modules:
        return True
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def _capabilities(context: DeviceContext) -> dict[str, CapabilityStatus]:
    dependencies = {'wda': _sdk_present('wda')} if context.platform == 'ios' else {
        'adb': bool(shutil.which(context.adb_path or 'adb')), 'uiautomator2': _sdk_present('uiautomator2'),
    }
    return {name: CapabilityStatus(
        'needs_permission' if found else 'needs_dependency', name,
        'dependency discovered; device connectivity/authorization not exercised' if found else 'dependency not found',
        'Authorize and explicitly operate the selected device.' if found else f'Install/configure {name}.',
        desktop_wide=False,
    ) for name, found in dependencies.items()}


class DeviceSession:
    """Own a lazy mobile binding; cancel/close never changes process defaults.

    connected describes the open logical owner, not verified device reachability.
    Cancellation rejects further requests and late completions. A native request
    already sent may drain within its request timeout; physical state is observed
    separately. Only helpers started by this SDK client are reclaimed; global
    ADB servers, existing device services and unrelated WDA app sessions stay owned
    by their original clients.
    """

    def __init__(self, context: DeviceContext) -> None:
        self._context = context
        self._closed = threading.Event()
        self._lock = threading.Lock()
        self._adapters: dict[str, Any] = {}

    @property
    def context(self) -> DeviceContext:
        """Return the frozen identity used by every operation in this session."""
        return self._context

    @property
    def connected(self) -> bool:
        """Whether the logical owner is open; no network probe is performed."""
        return not self._closed.is_set()

    @property
    def capabilities(self) -> dict[str, CapabilityStatus]:
        """Passively discover dependencies without loading SDKs or requesting input."""
        if self.connected:
            return _capabilities(self.context)
        return {'session': CapabilityStatus('unsupported', self.context.platform,
                                           'device session is closed', 'Open a new explicit context.', False)}

    def ensure_open(self) -> None:
        """Reject a cancelled owner rather than falling back to a default device."""
        if not self.connected:
            raise DeviceSessionError('device session is closed or cancelled; open a new explicit context')

    def capture(self) -> DeviceFrame:
        """Capture native device evidence with point/pixel and orientation metadata."""
        return _mobile_operations.capture(self)

    def perform(self, gesture: Gesture) -> None:
        """Send a validated native-point gesture without a desktop fallback."""
        _mobile_operations.perform(self, gesture)

    def type_text(self, text: str) -> None:
        """Send Unicode unchanged through this device's SDK input route."""
        _mobile_operations.type_text(self, text)

    def adapter(self, kind: str) -> Any:
        """Return one owned lazy client; SDK construction happens on first use."""
        with self._lock:
            self.ensure_open()
            if kind not in self._adapters:
                self._adapters[kind] = self._new_adapter(kind)
            return self._adapters[kind]

    def _new_adapter(self, kind: str) -> Any:
        if kind == 'adb' and self.context.platform == 'android':
            return OwnedAdbClient(self.context, self.ensure_open)
        if kind == 'uiautomator2' and self.context.platform == 'android':
            return UIAutomatorDevice(self.context.target, _guard=self.ensure_open, timeout_s=self.context.timeout_s)
        if kind == 'wda' and self.context.platform == 'ios':
            return IOSDevice(self.context.target, _guard=self.ensure_open, timeout_s=self.context.timeout_s)
        raise DeviceSessionError('the requested backend belongs to a different device platform')

    @contextmanager
    def bind(self) -> Iterator[DeviceSession]:
        """Use this owner for implicit mobile helpers in the current execution context."""
        self.ensure_open()
        with bind_device(self):
            yield self

    def cancel(self) -> None:
        """Invalidate before cleanup; do not wait behind an unanswered SDK constructor."""
        self.close()

    def close(self) -> None:
        """Detach clients first, then reclaim only helpers started by this owner."""
        with self._lock:
            self._closed.set()
            clients = tuple(self._adapters.items())
            self._adapters.clear()
        for kind, client in clients:
            if kind != 'adb':
                client.close()

    def __enter__(self) -> DeviceSession:
        self.ensure_open()
        return self

    def __exit__(self, *_exception: object) -> None:
        self.close()


def open_device(context: DeviceContext) -> DeviceSession:
    """Create a fresh lazy owner; never mutate default clients or perform device input."""
    if not isinstance(context, DeviceContext):
        raise DeviceSessionError('open_device requires a frozen DeviceContext')
    return DeviceSession(context)


def probe_device_contexts(devices: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Return passive matrix metadata; never import SDKs, connect or send input."""
    if not isinstance(devices, (list, tuple)):
        raise DeviceSessionError('devices must be a list or tuple of device specs')
    return [{'device_id': context.device_id, 'platform': context.platform,
             'capabilities': {name: asdict(status) for name, status in _capabilities(context).items()}}
            for context in (DeviceContext.from_spec(spec, index=index) for index, spec in enumerate(devices))]


def bound_adapter(platform: str, kind: str, target: Optional[str] = None,
                  adb_path: Optional[str] = None) -> Any:
    """Resolve an explicit helper through its owner, refusing cross-target overrides."""
    session = bound_device(platform)
    if session is None:
        return None
    if ((target is not None and target != session.context.target)
            or (adb_path is not None and adb_path != session.context.adb_path)):
        raise DeviceSessionError('explicit target/config does not match the active device context')
    return session.adapter(kind)
