"""Session-scoped mobile capture and input without desktop fallback."""
from __future__ import annotations

import io
from typing import TYPE_CHECKING, Any

from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.wrapper._mobile_models import DeviceSessionError
from je_auto_control.wrapper.device_frame import DeviceFrame
from je_auto_control.wrapper.mobile_gesture import Gesture

if TYPE_CHECKING:
    from je_auto_control.wrapper._mobile_binding import _BoundDevice

_IOS_ORIENTATIONS = {'PORTRAIT': 0, 'LANDSCAPE': 90, 'UIA_DEVICE_ORIENTATION_LANDSCAPERIGHT': 270,
                     'UIA_DEVICE_ORIENTATION_PORTRAIT_UPSIDEDOWN': 180}


def _geometry(handle: Any, platform: str) -> tuple[tuple[float, float], int]:
    if platform == 'android':
        info = handle.info
        rotation = info['displayRotation']
        if isinstance(rotation, bool) or rotation not in (0, 1, 2, 3):
            raise DeviceSessionError('Android returned an unknown orientation')
        return (info['displayWidth'], info['displayHeight']), int(rotation) * 90
    orientation = handle.orientation
    if orientation not in _IOS_ORIENTATIONS:
        raise DeviceSessionError('WDA returned an unknown orientation')
    # The SDK public window_size fallback can dismiss alerts or launch Settings.
    # Read the raw viewport instead; zero/malformed geometry must fail visibly.
    size = handle._unsafe_window_size()  # pylint: disable=protected-access  # reason: avoid SDK alert/Settings side effects
    return (size['width'], size['height']) if isinstance(size, dict) else tuple(size), _IOS_ORIENTATIONS[orientation]


def capture(session: _BoundDevice) -> DeviceFrame:
    """Snapshot native orientation/viewport around one screenshot; never touch desktop."""
    session.ensure_open()
    platform = session.context.platform
    handle = session.adapter('wda' if platform == 'ios' else 'uiautomator2').handle
    try:
        geometry = _geometry(handle, platform)
        image = handle.screenshot()
        try:
            output = io.BytesIO()
            image.save(output, format='PNG')
        finally:
            image.close()
        if _geometry(handle, platform) != geometry:
            raise DeviceSessionError('device geometry changed during capture; recapture before input')
        frame = DeviceFrame(output.getvalue(), session.context, *geometry)
    except AutoControlException:
        raise
    except Exception as failure:  # reason: optional SDK geometry methods can raise outside the framework family
        raise DeviceSessionError('device capture/geometry is invalid; check SDK and recapture') from failure
    session.ensure_open()
    return frame


def perform(session: _BoundDevice, gesture: Gesture) -> None:
    """Keep gesture dispatch inside one owner and its configured request budget."""
    session.ensure_open()
    if not isinstance(gesture, Gesture) or gesture.duration_s > session.context.timeout_s:
        raise DeviceSessionError('gesture must be validated and fit the device request timeout')
    if gesture.frame is not None:
        _validate_frame(session, gesture.frame)
    if session.context.platform == 'android':
        # pylint: disable-next=import-outside-toplevel  # reason: load only the selected platform operation
        from je_auto_control.android.input import perform_gesture
        kind = 'uiautomator2'
    else:
        # pylint: disable-next=import-outside-toplevel  # reason: load only the selected platform operation
        from je_auto_control.ios.input import perform_gesture
        kind = 'wda'
    perform_gesture(gesture, device=session.adapter(kind))
    session.ensure_open()


def _validate_frame(session: _BoundDevice, frame: DeviceFrame) -> None:
    if frame.context != session.context:
        raise DeviceSessionError('gesture frame belongs to a different device context')
    platform = session.context.platform
    handle = session.adapter('wda' if platform == 'ios' else 'uiautomator2').handle
    try:
        geometry = _geometry(handle, platform)
    except AutoControlException:
        raise
    except Exception as failure:  # reason: optional SDK metadata errors must retain the framework boundary
        raise DeviceSessionError('cannot verify device geometry before touch') from failure
    if geometry != (frame.point_size, frame.orientation):
        raise DeviceSessionError('device geometry changed since the frame; recapture before input')
    session.ensure_open()


def type_text(session: _BoundDevice, text: str) -> None:
    """Use an exact-Unicode SDK route on the selected device, with no ADB fallback."""
    session.ensure_open()
    if not isinstance(text, str) or '\x00' in text:
        raise DeviceSessionError('mobile text must be a string without NUL')
    if session.context.platform == 'android':
        # pylint: disable-next=import-outside-toplevel  # reason: load only the selected platform operation
        from je_auto_control.android.input import type_text as send
        kind = 'uiautomator2'
    else:
        # pylint: disable-next=import-outside-toplevel  # reason: load only the selected platform operation
        from je_auto_control.ios.input import type_text as send
        kind = 'wda'
    send(text, device=session.adapter(kind))
    session.ensure_open()
