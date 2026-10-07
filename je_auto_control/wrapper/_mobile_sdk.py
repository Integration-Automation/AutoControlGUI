"""Per-owner SDK transport guards; no SDK import or global timeout changes."""
from __future__ import annotations

import atexit
import functools
import inspect
from typing import Any, Callable, Optional

from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.wrapper._mobile_models import DeviceSessionError, bounded_timeout


class _GuardedSDK:  # pylint: disable=too-few-public-methods  # reason: mixin guards inherited SDK operations
    """Revoke retained public methods/properties, including direct SDK ADB helpers."""

    def __getattribute__(self, name: str) -> Any:
        if name.startswith('_'):
            return super().__getattribute__(name)
        guard = super().__getattribute__('_owned_guard')
        guard()
        value = super().__getattribute__(name)
        guard()
        if not inspect.isroutine(value):
            return value
        methods = super().__getattribute__('_owned_methods')
        if name not in methods:
            @functools.wraps(value)
            def guarded(*args: Any, **kwargs: Any) -> Any:
                guard()
                try:
                    result = value(*args, **kwargs)
                except AutoControlException:
                    raise
                except Exception as failure:  # reason: optional SDK families must not escape the framework boundary
                    raise DeviceSessionError('mobile SDK request failed') from failure
                guard()
                return result
            methods[name] = guarded
        return methods[name]


def _initialize_owner(handle: Any, guard: Callable[[], None]) -> None:
    object.__setattr__(handle, '_owned_guard', guard)
    object.__setattr__(handle, '_owned_methods', {})


def android_handle(sdk: Any, serial: str, timeout_s: float, guard: Callable[[], None]) -> Any:
    """Bind uiautomator2 RPC/shell/device-wait requests to one owner and deadline."""
    class OwnedDevice(_GuardedSDK, sdk.Device):
        """Guard the SDK's request boundaries instead of changing module globals."""

        def _wait_for_device(self, timeout: float = 10) -> Any:
            guard()
            result = super()._wait_for_device(timeout=bounded_timeout(timeout_s, timeout))
            guard()
            return result

        def jsonrpc_call(self, method: str, params: Any = None, timeout: float = 10) -> Any:
            """Bound one RPC request and reject its reply after revocation."""
            guard()
            result = super().jsonrpc_call(method, params, bounded_timeout(timeout_s, timeout))
            guard()
            return result

        def shell(self, cmdargs: Any, timeout: float = 60) -> Any:
            """Bound one SDK shell request without changing SDK global state."""
            guard()
            result = super().shell(cmdargs, timeout=bounded_timeout(timeout_s, timeout))
            guard()
            return result

    guard()
    handle = OwnedDevice.__new__(OwnedDevice)
    _initialize_owner(handle, guard)
    try:
        sdk.Device.__init__(handle, serial)  # pylint: disable=unnecessary-dunder-call  # reason: retain partial handle for cleanup
    except BaseException:  # reason: even a failed SDK bootstrap may have launched an owned helper
        dispose_android(handle)
        raise
    return handle


def ios_handle(sdk: Any, url: str, timeout_s: float, guard: Callable[[], None]) -> Any:
    """Bound WDA HTTP requests independently of the SDK's global HTTP_TIMEOUT."""
    class OwnedClient(_GuardedSDK, sdk.Client):  # pylint: disable=too-few-public-methods  # reason: inherits optional SDK API
        """Keep root-client requests and retry paths inside this owner's lifetime."""

        def _fetch(self, method: str, urlpath: str, data: Any = None,
                   with_session: bool = False, timeout: Optional[float] = None) -> Any:
            guard()
            result = super()._fetch(method, urlpath, data, with_session,
                                    bounded_timeout(timeout_s, timeout))
            guard()
            return result

    guard()
    handle = OwnedClient.__new__(OwnedClient)
    _initialize_owner(handle, guard)
    sdk.Client.__init__(handle, url)  # pylint: disable=unnecessary-dunder-call  # reason: initialize owner before SDK bootstrap
    return handle


def dispose_android(handle: Any) -> None:
    """Remove the SDK's atexit retention and close only this client's started helper."""
    # Bypass the revoked public-call guard for this one owned-resource cleanup.
    try:
        stop = object.__getattribute__(handle, 'stop_uiautomator')
    except AttributeError:
        return
    if stop is not None:
        atexit.unregister(stop)
        methods = object.__getattribute__(handle, '_owned_methods')
        callback = methods.get('stop_uiautomator')
        if callback is not None:
            atexit.unregister(callback)
        if getattr(handle, '_process', None) is not None:
            stop(wait=False)
