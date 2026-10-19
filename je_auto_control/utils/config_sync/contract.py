"""Shared config commit errors, identifiers and bounded finite JSON wire values."""
import json

from je_auto_control.utils.exception.exceptions import AutoControlException

_MAX_BYTES = 1024 * 1024
_MAX_REVISION = 2**63 - 1


class ConfigSyncError(AutoControlException, RuntimeError):
    """Raised on network errors or schema validation failures."""


class ConfigStoreError(AutoControlException, RuntimeError):
    """Persistent configuration storage could not be opened or committed."""


class ConfigRevisionConflict(AutoControlException, RuntimeError):
    """A stale base revision or reused operation ID cannot replace committed data."""

    def __init__(self, current_revision: int, message: str = "stale config revision") -> None:
        super().__init__(message)
        self.current_revision = current_revision


class ConfigStoreFull(AutoControlException, RuntimeError):
    """A new account would exceed the configured persistent bucket capacity."""


def _identifier(value: str, label: str) -> None:
    if not isinstance(value, str) or not value or len(value) > 128 or not value.isprintable() or "/" in value:
        raise ConfigSyncError(f"invalid {label}")


def _revision(value: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value < _MAX_REVISION:
        raise ConfigSyncError("revision must be a nonnegative SQLite integer")


def _encoded(body: dict[str, object]) -> str:
    try:
        text = json.dumps(body, sort_keys=True, separators=(",", ":"), allow_nan=False, ensure_ascii=True)
    except (TypeError, ValueError, RecursionError):
        raise ConfigSyncError("config bucket must contain finite JSON data") from None
    if len(text.encode("ascii")) > _MAX_BYTES:
        raise ConfigSyncError("config bucket exceeds 1 MiB")
    return text


def _version_two(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value == 2
