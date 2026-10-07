"""Create and reclaim only explicit WDA session IDs, without SDK global retry/locks."""
from __future__ import annotations

import re
import threading
from collections.abc import Mapping
from time import monotonic
from typing import Any, Callable, cast

from je_auto_control.ios.client import IOSDevice, IOSUnavailableError
from je_auto_control.wrapper._mobile_client_owner import LazyMobileHandle
from je_auto_control.wrapper._mobile_models import DeviceContext, DeviceSessionError
from je_auto_control.wrapper._mobile_sdk import ios_handle
from je_auto_control.wrapper._mobile_sdk_protocols import IOSSDK
from je_auto_control.wrapper._mobile_wda_lease import EndpointLease


class IOSAppDevice(IOSDevice):
    """Freeze a newly created session ID; a late constructor disposes only that ID."""

    def __init__(self, context: DeviceContext, guard: Callable[[], None]) -> None:
        super().__init__(context.target, timeout_s=context.timeout_s, _guard=guard)
        self._context = context
        self._app_guard = guard
        self._ids: dict[str, Any] = {}
        self._ids_lock = threading.Lock()
        self._delete_lock = threading.Lock()
        self._lease = EndpointLease(context.target)
        self._owner = LazyMobileHandle(None, guard, self._dispose_handle)

    def handle_for(self, timeout_s: float) -> IOSSDK:
        """Include first session construction in the caller's request budget."""
        return cast(IOSSDK, self._owner.get(lambda: self._connect_handle(timeout_s)))

    def _connect_handle(self, timeout_s: float | None = None) -> Any:
        self._app_guard()
        self._lease.acquire()
        try:
            return self._create_owned(timeout_s)
        except BaseException:  # reason: release only reservations that have no confirmed native resources
            with self._ids_lock:
                has_resources = bool(self._ids)
            if not has_resources:
                self._lease.release()
            raise

    def _create_owned(self, timeout_s: float | None) -> Any:
        try:
            # pylint: disable-next=import-outside-toplevel  # reason: optional SDK is loaded on first native app use
            import wda
        except ImportError as failure:
            raise IOSUnavailableError('facebook-wda is required for owned iOS app operations') from failure
        deadline = monotonic() + (self._context.timeout_s if timeout_s is None else timeout_s)
        _require_idle(wda, self._context, deadline)
        self._app_guard()
        sid = None
        try:
            # SDK's low-level transport has an explicit timeout, no global named lock or automatic input replay.
            response = wda._unsafe_httpdo(  # pylint: disable=protected-access  # reason: bounded no-retry transport
                self._context.target.rstrip('/') + '/session', 'POST', {'capabilities': {}},
                _remaining(deadline))
            sid = _session_id(response)
            with self._ids_lock:
                self._ids[sid] = wda
            handle = ios_handle(wda, self._context.target, self._context.timeout_s, self._app_guard, session_id=sid)
            object.__setattr__(handle, '_owned_app_sid', sid)
            object.__setattr__(handle, '_owned_app_sdk', wda)
            return handle
        except BaseException:  # reason: reclaim a confirmed owned session if construction fails
            if sid is not None:
                self._delete_owned(sid)
            raise

    def _dispose_handle(self, handle: Any) -> None:
        sid = object.__getattribute__(handle, '_owned_app_sid')
        self._delete_owned(sid)

    def _delete_owned(self, sid: str) -> None:
        with self._delete_lock:
            with self._ids_lock:
                sdk = self._ids.get(sid)
            if sdk is not None:
                _delete(sdk, self._context, sid)
                with self._ids_lock:
                    self._ids.pop(sid, None)
                    if not self._ids:
                        self._lease.release()

    def close(self) -> None:
        """Retry confirmed owned IDs, including construction finishing after revocation."""
        self._owner.close()
        with self._ids_lock:
            identifiers = tuple(self._ids)
        for sid in identifiers:
            self._delete_owned(sid)


def _session_id(response: Any) -> str:
    sid = getattr(response, 'sessionId', None)
    if not sid:
        value = getattr(response, 'value', {})
        sid = value.get('sessionId') if isinstance(value, dict) else None
    if not isinstance(sid, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,200}', sid, re.ASCII):
        raise DeviceSessionError('WDA returned no valid session ID; server state is unknown, do not auto-retry')
    return sid


def _delete(sdk: Any, context: DeviceContext, sid: str) -> None:
    # pylint: disable-next=protected-access  # reason: cleanup targets only the explicitly owned ID after owner revocation
    sdk._unsafe_httpdo(context.target.rstrip('/') + f'/session/{sid}', 'DELETE', None, context.timeout_s)


def _remaining(deadline: float) -> float:
    remaining = deadline - monotonic()
    if remaining <= 0:
        raise DeviceSessionError('WDA ownership check exceeded the request deadline; no automatic retry')
    return remaining


def _require_idle(sdk: Any, context: DeviceContext, deadline: float) -> None:
    # Creating a WDA session kills its active session. Never replace a detected foreign owner.
    # pylint: disable-next=protected-access  # reason: passive bounded preflight without SDK status retry
    response = sdk._unsafe_httpdo(context.target.rstrip('/') + '/status', 'GET', None, _remaining(deadline))
    if isinstance(response, Mapping):
        known, sid = 'sessionId' in response, response.get('sessionId')
    else:
        known, sid = hasattr(response, 'sessionId'), getattr(response, 'sessionId', None)
    if not known:
        raise DeviceSessionError('WDA status lacks ownership metadata; configure a dedicated idle endpoint')
    if sid is not None:
        raise DeviceSessionError('WDA app operations require a dedicated idle endpoint; existing session is preserved')
