"""The D-Bus client this package uses, re-exported from its new home.

The implementation moved to :mod:`je_auto_control.utils.dbus_client` when the
Linux accessibility backend became its second caller: ``utils/`` sits above
the per-OS packages in this project's layering, so an accessibility backend
reaching down into ``linux_wayland/`` to borrow its D-Bus code would invert
that.

This module stays because the portal code and its tests import it by this
name, and moving a working protocol implementation is not a reason to churn
either.
"""
from je_auto_control.utils.dbus_client.session_bus import (  # noqa: F401  # reason: re-export
    BUS_INTERFACE, BUS_NAME, BUS_PATH, DBusError, ERROR, FIELD_ERROR_NAME,
    FIELD_INTERFACE, FIELD_MEMBER, FIELD_PATH, FIELD_REPLY_SERIAL,
    FIELD_SENDER, FIELD_SIGNATURE, METHOD_CALL, METHOD_RETURN, Message,
    SIGNAL, SessionBus, Variant, body_pairs, is_available, session_address,
)

__all__ = [
    "BUS_INTERFACE", "BUS_NAME", "BUS_PATH", "DBusError", "ERROR",
    "METHOD_CALL", "METHOD_RETURN", "Message", "SIGNAL", "SessionBus",
    "Variant", "body_pairs", "is_available", "session_address",
]
