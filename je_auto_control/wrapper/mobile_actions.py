"""JSON-safe owned mobile operations shared by actions, MCP and the matrix GUI."""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict
from typing import Any, Iterator, Mapping, Optional, cast

from je_auto_control.utils.path_guard.policy import scoped_path
from je_auto_control.wrapper._mobile_binding import _BoundDevice, active_device
from je_auto_control.wrapper._mobile_models import DeviceContext, DeviceSessionError
from je_auto_control.wrapper.device_context import open_device, DeviceSession
from je_auto_control.wrapper.mobile_gesture import Gesture


@contextmanager
def _owner(device: Optional[Mapping[str, Any]]) -> Iterator[_BoundDevice]:
    current = active_device()
    context = DeviceContext.from_spec(device) if device is not None else None
    if current is not None:
        if context is not None and context != current.context:
            raise DeviceSessionError('mobile action device does not match the active owner')
        yield current
    elif context is not None:
        with open_device(context) as session:
            yield session
    else:
        raise DeviceSessionError('mobile action requires an explicit device spec or active matrix owner')


def mobile_capture(file_path: str, device: Optional[Mapping[str, Any]] = None) -> dict[str, Any]:
    """Save one root-checked PNG and return native geometry without desktop fallback."""
    path = scoped_path(file_path, operation='write')
    with _owner(device) as session:
        frame = session.capture()
        session.ensure_open()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(frame.png)
    return {'file_path': str(path), 'device_id': frame.context.device_id,
            'pixel_size': list(frame.pixel_size), 'point_size': list(frame.point_size),
            'orientation': frame.orientation, 'rotation': frame.rotation}


def mobile_gesture(gesture: Mapping[str, Any], device: Optional[Mapping[str, Any]] = None) -> None:
    """Perform a validated JSON native-point gesture with explicit device ownership."""
    operation = Gesture.from_spec(gesture)
    with _owner(device) as session:
        session.perform(operation)


def mobile_type_text(text: str, device: Optional[Mapping[str, Any]] = None) -> None:
    """Send exact Unicode via SDK input; response never echoes the supplied text."""
    # pylint: disable-next=import-outside-toplevel  # reason: text dispatch is optional until requested
    from je_auto_control.wrapper._mobile_operations import type_text
    with _owner(device) as session:
        type_text(session, text)


__all__ = ['mobile_capture', 'mobile_gesture', 'mobile_type_text']


def mobile_app(action: str, app_id: str, timeout_s: Optional[float] = None,
               device: Optional[Mapping[str, Any]] = None) -> dict[str, Any]:
    """Launch/wait/state/stop an app through JSON actions and observe native state."""
    # pylint: disable-next=import-outside-toplevel  # reason: native app routes remain optional until requested
    from je_auto_control.wrapper import mobile_apps
    if action not in ('launch', 'wait', 'state', 'stop'):
        raise DeviceSessionError('mobile app action must be launch, wait, state or stop')
    with _owner(device) as bound:
        session = cast(DeviceSession, bound)
        if action == 'wait':
            result = mobile_apps.wait_for_app(session, app_id,
                timeout_s=session.context.timeout_s if timeout_s is None else timeout_s)
        else:
            if timeout_s is not None:
                raise DeviceSessionError('timeout_s is accepted only for wait; other operations use context timeout')
            result = {'launch': mobile_apps.launch_app, 'state': mobile_apps.app_state,
                      'stop': mobile_apps.stop_app}[action](session, app_id)
    return asdict(result)


def mobile_alert(action: str, device: Optional[Mapping[str, Any]] = None) -> None:
    """Accept/dismiss an iOS alert on the explicit owner; Android reports an alternative."""
    # pylint: disable-next=import-outside-toplevel  # reason: native alert route loads only when requested
    from je_auto_control.wrapper.mobile_apps import handle_mobile_alert
    with _owner(device) as session:
        handle_mobile_alert(cast(DeviceSession, session), action)


def mobile_extension_action(operation: str, options: Mapping[str, Any],
                            device: Optional[Mapping[str, Any]] = None) -> Any:
    """Run owned install/files/clipboard/recording through actions, MCP and matrix GUI."""
    # pylint: disable-next=import-outside-toplevel  # reason: optional adapters stay lazy in headless imports
    from je_auto_control.wrapper.mobile_extensions import run_mobile_extension
    with _owner(device) as session:
        return run_mobile_extension(cast(DeviceSession, session), operation, options)


__all__ += ['mobile_app', 'mobile_alert', 'mobile_extension_action']
