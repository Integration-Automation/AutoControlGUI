"""Connect a default native grant without holding the stop/cache lock across authorization."""
from __future__ import annotations

from _thread import LockType
from typing import Callable, Optional, Protocol, TYPE_CHECKING

from je_auto_control.linux_wayland.permission import WaylandPermissionRequired
from je_auto_control.utils.exception.exceptions import AutoControlException

if TYPE_CHECKING:
    from je_auto_control.linux_wayland.libei import NativeInputBackend


class CacheOwner(Protocol):  # pylint: disable=too-few-public-methods  # reason: structural module-cache contract
    """Compatibility cache fields retained on the libei module."""

    _DEFAULT_LOCK: LockType
    _CONNECT_LOCK: LockType
    _DEFAULT_BACKEND: Optional[NativeInputBackend]
    _PENDING_BACKEND: Optional[NativeInputBackend]
    _PERMISSION_ERROR: Optional[WaylandPermissionRequired]
    _PROBE_FAILED: bool

    def _new_default_backend(self) -> Optional[NativeInputBackend]:
        """Construct an unconnected native owner, or report missing dependencies."""
        raise NotImplementedError


def connect_default(owner: CacheOwner,
                    cleanup: Callable[[Callable[[], object]], None]) -> Optional[NativeInputBackend]:
    """Serialize connection attempts while leaving stop/reset free to revoke pending work."""
    # pylint: disable=protected-access  # reason: compatibility cache fields stay on the libei module
    with owner._CONNECT_LOCK:
        with owner._DEFAULT_LOCK:
            if owner._PERMISSION_ERROR is not None:
                raise WaylandPermissionRequired('input', owner._PERMISSION_ERROR.reason)
            if owner._DEFAULT_BACKEND is not None:
                return owner._DEFAULT_BACKEND
            if owner._PROBE_FAILED:
                return None
            backend = owner._new_default_backend()
            if backend is None:
                owner._PROBE_FAILED = True
                return None
            owner._PENDING_BACKEND = backend
        return _authorize(owner, backend, cleanup)


def _authorize(owner: CacheOwner, backend: NativeInputBackend,
               cleanup: Callable[[Callable[[], object]], None]) -> NativeInputBackend:
    # pylint: disable=protected-access  # reason: compatibility cache fields stay on the libei module
    published = False
    try:
        backend.connect()
        with owner._DEFAULT_LOCK:
            if owner._PENDING_BACKEND is not backend:
                reason = owner._PERMISSION_ERROR.reason if owner._PERMISSION_ERROR else 'input authorization was reset'
                raise WaylandPermissionRequired('input', reason)
            owner._DEFAULT_BACKEND = backend
            owner._PENDING_BACKEND = None
            published = True
        return backend
    except (AutoControlException, OSError, ValueError, AttributeError) as failure:
        raise _retain_failure(owner, backend, failure) from failure
    finally:
        if not published:
            cleanup(backend.disconnect)


def _retain_failure(owner: CacheOwner, backend: NativeInputBackend,
                    failure: Exception) -> WaylandPermissionRequired:
    # pylint: disable=protected-access  # reason: compatibility cache fields stay on the libei module
    reason = failure.reason if isinstance(failure, WaylandPermissionRequired) else str(failure)
    error = WaylandPermissionRequired('input', reason)
    with owner._DEFAULT_LOCK:
        if owner._PENDING_BACKEND is backend:
            owner._PENDING_BACKEND = None
            owner._PROBE_FAILED = not isinstance(failure, WaylandPermissionRequired)
            owner._PERMISSION_ERROR = error
        return owner._PERMISSION_ERROR if owner._PERMISSION_ERROR is not None else error
