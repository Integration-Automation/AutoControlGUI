"""Bounded Android app launch/state/stop through the explicitly owned ADB client."""
from __future__ import annotations

from typing import TYPE_CHECKING

from je_auto_control.wrapper._mobile_app_models import AppState
from je_auto_control.wrapper._mobile_models import DeviceSessionError

if TYPE_CHECKING:
    from je_auto_control.wrapper.device_context import DeviceSession


def launch(session: DeviceSession, app_id: str, timeout_s: float) -> None:
    """Launch the package's launcher intent without random desktop input."""
    result = session.adapter('adb').run(['shell', 'monkey', '-p', app_id, '-c',
                                       'android.intent.category.LAUNCHER', '1'], timeout=timeout_s)
    output = result.stdout.decode('utf-8', errors='replace')
    if 'Events injected: 1' not in output:
        raise DeviceSessionError('Android launcher did not confirm an injected launch event; inspect the device')


def state(session: DeviceSession, app_id: str, timeout_s: float) -> AppState:
    """Observe process presence; pidof exit one means absent, not a transport failure."""
    result = session.adapter('adb').run(['shell', 'pidof', app_id], check=False, timeout=timeout_s)
    if result.returncode not in (0, 1) or result.stderr.strip():
        raise DeviceSessionError('Android app state could not be observed; check authorization/connectivity')
    text = result.stdout.decode('ascii', errors='replace').strip()
    if bool(text) != (result.returncode == 0):
        raise DeviceSessionError('Android returned inconsistent process state; device state is unknown')
    if text and not all(pid.isdigit() and int(pid) > 0 for pid in text.split()):
        raise DeviceSessionError('Android returned invalid app process metadata')
    return AppState(app_id, session.context.device_id, 'running' if text else 'not_running')


def stop(session: DeviceSession, app_id: str, timeout_s: float) -> None:
    """Force-stop only the named package, without affecting the ADB server."""
    session.adapter('adb').run(['shell', 'am', 'force-stop', app_id], timeout=timeout_s)
