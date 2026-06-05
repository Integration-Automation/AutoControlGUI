"""Headless USB passthrough commands — one source of truth.

These plain functions implement the feature flag, ACL management, and
local/remote claim+probe operations. They return JSON-able dicts and
contain no transport glue, so the executor (``AC_usb_*``), the REST API
(``/usb/...``), the socket server, and the scheduler all call the same
code. No Qt, no aiortc at import time.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

# Standard USB GET_DESCRIPTOR (device) — a harmless liveness probe.
_DESC_REQUEST_TYPE = 0x80
_DESC_REQUEST = 0x06
_DESC_VALUE = 0x0100
_DESC_LENGTH = 18


def passthrough_enable(enabled: bool = True) -> Dict[str, Any]:
    """Toggle the USB passthrough feature flag (default off)."""
    from je_auto_control.utils.usb.passthrough import (
        enable_usb_passthrough, is_usb_passthrough_enabled,
    )
    enable_usb_passthrough(bool(enabled))
    return {"enabled": is_usb_passthrough_enabled()}


def passthrough_status() -> Dict[str, Any]:
    from je_auto_control.utils.usb.passthrough import is_usb_passthrough_enabled
    return {"enabled": is_usb_passthrough_enabled()}


def acl_list() -> Dict[str, Any]:
    from je_auto_control.utils.usb.passthrough import UsbAcl
    acl = UsbAcl()
    return {
        "default": acl.default_policy,
        "integrity_ok": acl.integrity_ok,
        "rules": [r.to_dict() for r in acl.list_rules()],
    }


def acl_add(vendor_id: str, product_id: str,
            serial: Optional[str] = None, allow: bool = True,
            prompt_on_open: bool = False, label: str = "") -> Dict[str, Any]:
    from je_auto_control.utils.usb.passthrough import AclRule, UsbAcl
    acl = UsbAcl()
    acl.add_rule(AclRule(
        vendor_id=str(vendor_id), product_id=str(product_id),
        serial=(None if serial is None else str(serial)),
        label=str(label), allow=bool(allow),
        prompt_on_open=bool(prompt_on_open),
    ))
    return {"added": True, "rules": len(acl.list_rules())}


def acl_remove(vendor_id: str, product_id: str,
               serial: Optional[str] = None) -> Dict[str, Any]:
    from je_auto_control.utils.usb.passthrough import UsbAcl
    removed = UsbAcl().remove_rule(
        vendor_id=str(vendor_id), product_id=str(product_id),
        serial=(None if serial is None else str(serial)),
    )
    return {"removed": removed}


def acl_set_default(policy: str) -> Dict[str, Any]:
    from je_auto_control.utils.usb.passthrough import UsbAcl
    acl = UsbAcl()
    acl.set_default_policy(str(policy))
    return {"default": acl.default_policy}


def acl_export(path: str) -> Dict[str, Any]:
    from je_auto_control.utils.usb.passthrough import UsbAcl, export_acl_to_file
    export_acl_to_file(UsbAcl(), Path(path))
    return {"exported": True, "path": str(path)}


def acl_import(path: str, replace: bool = False) -> Dict[str, Any]:
    from je_auto_control.utils.usb.passthrough import UsbAcl, import_acl_from_file
    count = import_acl_from_file(UsbAcl(), Path(path), replace=bool(replace))
    return {"imported": count}


def _descriptor_probe(client: Any, vendor_id: str, product_id: str,
                      serial: Optional[str]) -> Dict[str, Any]:
    """Open a claim, read the device descriptor, close — return a summary."""
    from je_auto_control.utils.usb.passthrough import describe_descriptor
    handle = client.open(
        vendor_id=str(vendor_id), product_id=str(product_id),
        serial=(None if serial is None else str(serial)),
    )
    try:
        descriptor = handle.control_transfer(
            bm_request_type=_DESC_REQUEST_TYPE, b_request=_DESC_REQUEST,
            w_value=_DESC_VALUE, length=_DESC_LENGTH,
        )
    finally:
        handle.close()
    return {
        "ok": True, "vendor_id": str(vendor_id), "product_id": str(product_id),
        "descriptor_hex": descriptor.hex(),
        "descriptor": describe_descriptor(descriptor),
    }


def loopback_list() -> Dict[str, Any]:
    """List ACL-visible devices over the in-process loopback channel."""
    from je_auto_control.utils.usb.passthrough import UsbAcl, UsbLoopback
    with UsbLoopback(acl=UsbAcl(), viewer_id="command") as loop:
        return {"devices": loop.list_devices()}


def loopback_open(vendor_id: str, product_id: str,
                  serial: Optional[str] = None) -> Dict[str, Any]:
    """Claim a local device over loopback and read its descriptor."""
    from je_auto_control.utils.usb.passthrough import UsbAcl, UsbLoopback
    with UsbLoopback(acl=UsbAcl(), viewer_id="command") as loop:
        return _descriptor_probe(loop, vendor_id, product_id, serial)


def _remote_client() -> Any:
    """Return the live WebRTC viewer's USB client or raise a clear error."""
    from je_auto_control.utils.remote_desktop.registry import registry
    client = registry.webrtc_usb_client()
    if client is None:
        raise RuntimeError("no live WebRTC viewer with a usb channel")
    return client


def remote_list() -> Dict[str, Any]:
    """List the remote host's devices over the live WebRTC usb channel."""
    return {"devices": _remote_client().list_devices()}


def remote_open(vendor_id: str, product_id: str,
                serial: Optional[str] = None) -> Dict[str, Any]:
    """Claim a remote device over the live WebRTC usb channel + probe."""
    return _descriptor_probe(_remote_client(), vendor_id, product_id, serial)


__all__ = [
    "passthrough_enable", "passthrough_status",
    "acl_list", "acl_add", "acl_remove", "acl_set_default",
    "acl_export", "acl_import",
    "loopback_list", "loopback_open", "remote_list", "remote_open",
]
