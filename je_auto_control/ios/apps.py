"""WDA app and alert routes through a frozen session owned by one device context."""
from __future__ import annotations

from time import monotonic
from typing import Literal, TYPE_CHECKING

from je_auto_control.wrapper._mobile_app_models import AppState
from je_auto_control.wrapper._mobile_models import DeviceSessionError

if TYPE_CHECKING:
    from je_auto_control.wrapper.device_context import DeviceSession


def _request(session: DeviceSession, path: str, data: dict, timeout_s: float):
    deadline = monotonic() + timeout_s
    handle = session.adapter('wda_app').handle_for(timeout_s)
    remaining = deadline - monotonic()
    if remaining <= 0:
        raise DeviceSessionError('WDA session construction exceeded the request deadline; state is unknown')
    # pylint: disable-next=protected-access  # reason: explicit owned routes avoid SDK unlock/retry/default-session effects
    return handle._fetch('POST', path, data, with_session=True, timeout=remaining)


def launch(session: DeviceSession, app_id: str, timeout_s: float) -> None:
    """Launch on the owned WDA session; do not auto-unlock or switch a global client."""
    _request(session, '/wda/apps/launch', {'bundleId': app_id, 'shouldWaitForQuiescence': False}, timeout_s)


def state(session: DeviceSession, app_id: str, timeout_s: float) -> AppState:
    """Map XCTest's observed state, rejecting malformed/unknown server data."""
    native = _request(session, '/wda/apps/state', {'bundleId': app_id}, timeout_s).value
    if isinstance(native, bool) or not isinstance(native, int) or native not in (0, 1, 2, 3, 4):
        raise DeviceSessionError('WDA returned an unknown application state')
    mapped: Literal['running', 'not_running', 'not_installed']
    mapped = 'not_installed' if native == 0 else 'not_running' if native == 1 else 'running'
    return AppState(app_id, session.context.device_id, mapped, native)


def stop(session: DeviceSession, app_id: str, timeout_s: float) -> None:
    """Terminate only the requested bundle through the owned session."""
    _request(session, '/wda/apps/terminate', {'bundleId': app_id}, timeout_s)


def alert(session: DeviceSession, action: str, timeout_s: float) -> None:
    """Accept/dismiss the owned session's current system alert."""
    _request(session, f'/alert/{action}', {}, timeout_s)
