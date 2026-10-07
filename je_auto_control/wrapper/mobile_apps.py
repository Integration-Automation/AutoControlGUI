"""Owned app lifecycle, observed state and cancellable deadline polling."""
from __future__ import annotations

from importlib import import_module
from time import monotonic
from typing import Any, TYPE_CHECKING

from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.wrapper._mobile_app_models import AppState, validate_app_id
from je_auto_control.wrapper._mobile_models import DeviceSessionError, bounded_timeout

if TYPE_CHECKING:
    from je_auto_control.wrapper.device_context import DeviceSession


def _call(session: DeviceSession, operation: str, app_id: str, timeout_s: float) -> Any:
    session.ensure_open()
    backend = import_module(f'je_auto_control.{session.context.platform}.apps')
    try:
        result = getattr(backend, operation)(session, app_id, timeout_s)
    except AutoControlException:
        raise
    except Exception as failure:  # reason: contain optional native failures and unknown device state
        raise DeviceSessionError('mobile app request failed; device state is unknown') from failure
    session.ensure_open()
    return result


def app_state(session: DeviceSession, app_id: str) -> AppState:
    """Observe one package/bundle; never convert connection failure into not_running."""
    validate_app_id(app_id)
    return _call(session, 'state', app_id, session.context.timeout_s)


def launch_app(session: DeviceSession, app_id: str) -> AppState:
    """Launch explicitly, then return observed running state within the owner timeout."""
    validate_app_id(app_id)
    deadline = monotonic() + session.context.timeout_s
    _call(session, 'launch', app_id, session.context.timeout_s)
    remaining = deadline - monotonic()
    if remaining <= 0:
        raise DeviceSessionError('launch deadline exceeded; inspect device state before retry')
    return wait_for_app(session, app_id, timeout_s=remaining)


def wait_for_app(session: DeviceSession, app_id: str, *, timeout_s: float) -> AppState:
    """Poll running state with a finite deadline and cancellation-aware waits."""
    validate_app_id(app_id)
    session.ensure_open()
    deadline = monotonic() + bounded_timeout(session.context.timeout_s, timeout_s)
    while True:
        session.ensure_open()
        remaining = deadline - monotonic()
        if remaining <= 0:
            raise DeviceSessionError('waiting for mobile app timed out; inspect observed device state before retry')
        result = _call(session, 'state', app_id, remaining)
        if monotonic() >= deadline:
            raise DeviceSessionError('waiting for mobile app timed out; late state cannot confirm timely launch')
        if result.state == 'running':
            return result
        if result.state == 'not_installed':
            raise DeviceSessionError('mobile app is not installed; configure an installation adapter')
        session.wait_cancelled(min(.05, max(0, deadline - monotonic())))


def stop_app(session: DeviceSession, app_id: str) -> AppState:
    """Stop only the named app and verify its state rather than returning fake success."""
    validate_app_id(app_id)
    deadline = monotonic() + session.context.timeout_s
    _call(session, 'stop', app_id, session.context.timeout_s)
    remaining = deadline - monotonic()
    if remaining <= 0:
        raise DeviceSessionError('stop deadline exceeded; inspect device state before retry')
    result = _call(session, 'state', app_id, remaining)
    if monotonic() >= deadline:
        raise DeviceSessionError('stop verification exceeded deadline; device state is unknown')
    if result.state == 'running':
        raise DeviceSessionError('app remains running after stop; inspect the device before retry')
    return result


def handle_mobile_alert(session: DeviceSession, action: str) -> None:
    """Accept/dismiss iOS alerts; Android uses an explicit UI-tree selector instead."""
    if action not in ('accept', 'dismiss'):
        raise DeviceSessionError('alert action must be accept or dismiss')
    if session.context.platform != 'ios':
        raise DeviceSessionError('Android has no universal alert endpoint; use find_element/click_element')
    _call(session, 'alert', action, session.context.timeout_s)


__all__ = ['AppState', 'app_state', 'launch_app', 'wait_for_app', 'stop_app', 'handle_mobile_alert']
