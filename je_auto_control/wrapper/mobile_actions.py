"""JSON-safe owned mobile operations shared by actions, MCP and the matrix GUI."""
from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator, Mapping, Optional

from je_auto_control.utils.path_guard.policy import scoped_path
from je_auto_control.wrapper._mobile_binding import _BoundDevice, active_device
from je_auto_control.wrapper._mobile_models import DeviceContext, DeviceSessionError
from je_auto_control.wrapper.device_context import open_device
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
