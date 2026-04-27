"""Feature flag for USB passthrough.

Default: **disabled**. The design doc explicitly requires an external
security review before this turns on by default. Two ways to opt in:

  * environment: ``JE_AUTOCONTROL_USB_PASSTHROUGH=1``
  * programmatic: ``enable_usb_passthrough(True)`` from your bootstrap

The host's WebRTC layer is expected to call
:func:`is_usb_passthrough_enabled` before honouring an incoming ``usb``
DataChannel. If False, the channel must be rejected with an ERROR
frame and not opened.
"""
from __future__ import annotations

import os
import threading


_ENV_VAR = "JE_AUTOCONTROL_USB_PASSTHROUGH"
_TRUTHY = frozenset({"1", "true", "yes", "on"})

_state_lock = threading.Lock()
_explicit_state: "_ExplicitState | None" = None


class _ExplicitState:
    __slots__ = ("value",)

    def __init__(self, value: bool) -> None:
        self.value = bool(value)


def enable_usb_passthrough(enabled: bool) -> None:
    """Programmatic override of the env var.

    Pass ``True`` to opt in, ``False`` to force off (overriding any env
    setting). Once set, this wins until the process exits.
    """
    global _explicit_state
    with _state_lock:
        _explicit_state = _ExplicitState(enabled)


def is_usb_passthrough_enabled() -> bool:
    """True iff the operator opted in via env or explicit call."""
    with _state_lock:
        explicit = _explicit_state
    if explicit is not None:
        return explicit.value
    return os.environ.get(_ENV_VAR, "").strip().lower() in _TRUTHY


__all__ = ["enable_usb_passthrough", "is_usb_passthrough_enabled"]
