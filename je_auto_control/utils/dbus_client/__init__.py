"""A minimal D-Bus session-bus client, in the standard library alone.

Written for the XDG portal handshake — see :mod:`.session_bus` for why that
could not be a shell-out to ``gdbus`` — and kept general enough for anything
else that has to speak D-Bus without pulling in a binding. AT-SPI2, the Linux
accessibility bus, is the second caller.

It lives here rather than under ``linux_wayland/`` because ``utils/`` sits
above the per-OS packages in this project's layering: an accessibility backend
in ``utils/`` reaching down into a platform backend to borrow its D-Bus code
would invert that. ``je_auto_control.linux_wayland._dbus_client`` re-exports
this module, so the Wayland code and its tests are unchanged.
"""
from je_auto_control.utils.dbus_client.session_bus import (
    BUS_INTERFACE, BUS_NAME, BUS_PATH, DBusError, ERROR, METHOD_CALL,
    METHOD_RETURN, Message, SIGNAL, SessionBus, Variant, body_pairs,
    is_available, session_address,
)

__all__ = [
    "BUS_INTERFACE", "BUS_NAME", "BUS_PATH", "DBusError", "ERROR",
    "METHOD_CALL", "METHOD_RETURN", "Message", "SIGNAL", "SessionBus",
    "Variant", "body_pairs", "is_available", "session_address",
]
