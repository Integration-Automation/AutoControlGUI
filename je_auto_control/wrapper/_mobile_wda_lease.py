"""Reserve exact WDA endpoints without holding global locks during native I/O."""
from __future__ import annotations

import threading

from je_auto_control.wrapper._mobile_models import DeviceSessionError

_LOCK = threading.Lock()
_OWNERS: dict[str, object] = {}


class EndpointLease:
    """Protect same-process pending/active owners; external clients need exclusive endpoints."""

    def __init__(self, endpoint: str) -> None:
        self._endpoint = endpoint.rstrip('/')
        self._token = object()

    def acquire(self) -> None:
        """Fail fast if another local owner is constructing or using this endpoint."""
        with _LOCK:
            current = _OWNERS.get(self._endpoint)
            if current is not None and current is not self._token:
                raise DeviceSessionError(
                    'WDA endpoint is owned by another local session; use a dedicated idle endpoint')
            _OWNERS[self._endpoint] = self._token

    def release(self) -> None:
        """Release only this token after failure before creation or confirmed owned cleanup."""
        with _LOCK:
            if _OWNERS.get(self._endpoint) is self._token:
                del _OWNERS[self._endpoint]
