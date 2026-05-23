"""Phase 8.2: USB/IP wire protocol — host side.

The USB/IP project (https://github.com/torvalds/linux/tree/master/drivers/usb/usbip)
defines a TCP wire protocol that lets a virtual USB host controller
on one machine see devices physically attached to another. The Linux
kernel ships ``vhci-hcd`` as the client driver; Windows is served by
the open-source `usbip-win <https://github.com/cezanne/usbip-win>`_
KMDF driver. macOS does *not* have a viable client today —
post-Big Sur kernel extensions require a paid Apple Developer
entitlement Apple no longer grants for new third-party USB drivers,
so macOS clients are documented as unsupported.

This module ships the **server side**: AutoControl's host machine
publishes its locally-plugged USB devices over TCP/3240, and a remote
Linux / Windows machine ``usbip attach``-es one of them. From the
client's perspective the device shows up as locally plugged.

What's in the box:

* :mod:`usbip.protocol` — RFC-style packers / unpackers for every
  OP_* and USBIP_* message. Wire format is deterministic and stable
  across kernel versions (it was frozen as ``protocol_version=0x0111``
  in 2010).
* :mod:`usbip.server` — single-threaded ``socketserver``-based server.
  Handles OP_REQ_DEVLIST and OP_REQ_IMPORT in-process; URB submission
  is routed to a pluggable :class:`UrbBackend`.
* :mod:`usbip.backend` — abstract URB execution. The bundled
  :class:`FakeUrbBackend` is what the test suite uses; production
  deployments plug in libusb / WinUSB via subclassing.

The wire protocol is the focus here. Driving a *real* device requires
libusb plus root privileges (or an INF + WinUSB driver match on
Windows) and lives in the platform-specific backends shipped in
:mod:`je_auto_control.utils.usb.passthrough`.
"""
from je_auto_control.utils.usbip.backend import (
    FakeUrbBackend, UrbBackend, UrbRequest, UrbResponse,
)
from je_auto_control.utils.usbip.protocol import (
    OP_REP_DEVLIST, OP_REP_IMPORT, OP_REQ_DEVLIST, OP_REQ_IMPORT,
    PROTOCOL_VERSION, USBIP_CMD_SUBMIT, USBIP_CMD_UNLINK,
    USBIP_RET_SUBMIT, USBIP_RET_UNLINK, UsbIpDevice, UsbIpError,
    decode_cmd_submit, decode_op_request, encode_op_rep_devlist,
    encode_op_rep_import, encode_ret_submit,
)
from je_auto_control.utils.usbip.server import (
    UsbIpServer, default_port,
)

__all__ = [
    "FakeUrbBackend", "UrbBackend", "UrbRequest", "UrbResponse",
    "OP_REP_DEVLIST", "OP_REP_IMPORT", "OP_REQ_DEVLIST", "OP_REQ_IMPORT",
    "PROTOCOL_VERSION", "USBIP_CMD_SUBMIT", "USBIP_CMD_UNLINK",
    "USBIP_RET_SUBMIT", "USBIP_RET_UNLINK", "UsbIpDevice", "UsbIpError",
    "decode_cmd_submit", "decode_op_request", "encode_op_rep_devlist",
    "encode_op_rep_import", "encode_ret_submit",
    "UsbIpServer", "default_port",
]
