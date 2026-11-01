"""Errors the viewer-side USB passthrough client raises.

Kept apart from ``viewer_client`` so the handle, the request bookkeeping
and the client can all raise them without importing each other. Every
name is re-exported from ``viewer_client``, which is where callers have
always imported them from.
"""
from __future__ import annotations

from je_auto_control.utils.exception.exceptions import AutoControlException


class UsbClientError(AutoControlException):
    """The host reported a transfer or open failure."""


class UsbClientTimeout(UsbClientError):
    """A reply did not arrive within the configured timeout."""


class UsbClientClosed(UsbClientError):
    """The client / handle was shut down before a reply arrived."""


class UsbClientDesynchronized(UsbClientError):
    """A timed-out request left replies impossible to pair; reconnect.

    Raised instead of sending when an earlier request of the same kind
    timed out and the host does not echo request ids: its late reply and
    the answer to a new request would be indistinguishable. A claim is
    recovered by closing its handle and opening the device again; OPEN /
    RESUME and LIST by reconnecting the channel with a new client.
    """


__all__ = [
    "UsbClientClosed", "UsbClientDesynchronized",
    "UsbClientError", "UsbClientTimeout",
]
