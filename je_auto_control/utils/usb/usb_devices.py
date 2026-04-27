"""Cross-platform USB device enumeration.

Tries backends in this order:
  1. ``pyusb`` (libusb wrapper) — works everywhere libusb is installed.
  2. Platform-specific shell commands — Windows ``Get-PnpDevice``,
     macOS ``system_profiler``, Linux ``/sys/bus/usb/devices``.

Only enumerates — does NOT open devices, claim interfaces, or transfer
data. Actual passthrough is a future phase.

All shell-based backends pass argv lists, never shell-string commands,
to satisfy CLAUDE.md's injection-prevention policy.
"""
from __future__ import annotations

import json
import platform
import re
import subprocess  # nosec B404  # reason: needed for platform-specific enumeration tools
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from je_auto_control.utils.logging.logging_instance import autocontrol_logger


_SUBPROCESS_TIMEOUT_S = 10.0


@dataclass
class UsbDevice:
    """One detected USB device (read-only metadata)."""

    vendor_id: Optional[str] = None      # 4-hex-digit string, e.g. "046d"
    product_id: Optional[str] = None
    manufacturer: Optional[str] = None
    product: Optional[str] = None
    serial: Optional[str] = None
    bus_location: Optional[str] = None
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class UsbEnumerationResult:
    """Result of an enumeration call: device list + which backend ran."""

    backend: str
    devices: List[UsbDevice]
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "backend": self.backend,
            "error": self.error,
            "devices": [d.to_dict() for d in self.devices],
            "count": len(self.devices),
        }


def list_usb_devices() -> UsbEnumerationResult:
    """Return the best-available enumeration result for the current OS."""
    pyusb_result = _try_pyusb()
    if pyusb_result is not None:
        return pyusb_result
    system = platform.system()
    if system == "Windows":
        return _enumerate_windows()
    if system == "Darwin":
        return _enumerate_macos()
    if system == "Linux":
        return _enumerate_linux()
    return UsbEnumerationResult(
        backend="unsupported", devices=[],
        error=f"no USB enumeration backend for platform {system!r}",
    )


def _try_pyusb() -> Optional[UsbEnumerationResult]:
    try:
        import usb.core  # type: ignore[import-not-found]
    except ImportError:
        return None
    try:
        devices = list(usb.core.find(find_all=True))
    except (OSError, RuntimeError, ValueError) as error:
        autocontrol_logger.info("pyusb enumerate failed: %r", error)
        return UsbEnumerationResult(backend="pyusb", devices=[],
                                    error=str(error))
    parsed = [_pyusb_to_device(dev) for dev in devices]
    return UsbEnumerationResult(backend="pyusb", devices=parsed)


def _pyusb_to_device(dev: Any) -> UsbDevice:
    return UsbDevice(
        vendor_id=_hex4(getattr(dev, "idVendor", None)),
        product_id=_hex4(getattr(dev, "idProduct", None)),
        manufacturer=_safe_string(dev, "manufacturer"),
        product=_safe_string(dev, "product"),
        serial=_safe_string(dev, "serial_number"),
        bus_location=_pyusb_bus(dev),
    )


def _enumerate_windows() -> UsbEnumerationResult:
    cmd = [
        "powershell", "-NoProfile", "-NonInteractive", "-Command",
        "Get-PnpDevice -PresentOnly -Class USB"
        " | Select-Object FriendlyName, InstanceId, Manufacturer, Status"
        " | ConvertTo-Json -Compress",
    ]
    completed = _run_capture(cmd, "windows")
    if isinstance(completed, UsbEnumerationResult):
        return completed
    try:
        payload = json.loads(completed) if completed else []
    except ValueError as error:
        return UsbEnumerationResult(backend="windows", devices=[],
                                    error=f"json parse: {error}")
    if isinstance(payload, dict):
        payload = [payload]
    return UsbEnumerationResult(
        backend="windows",
        devices=[_windows_to_device(entry) for entry in payload
                 if isinstance(entry, dict)],
    )


def _windows_to_device(entry: Dict[str, Any]) -> UsbDevice:
    instance_id = str(entry.get("InstanceId") or "")
    vid_match = re.search(r"VID_([0-9A-Fa-f]{4})", instance_id)
    pid_match = re.search(r"PID_([0-9A-Fa-f]{4})", instance_id)
    return UsbDevice(
        vendor_id=vid_match.group(1).lower() if vid_match else None,
        product_id=pid_match.group(1).lower() if pid_match else None,
        manufacturer=_strip_or_none(entry.get("Manufacturer")),
        product=_strip_or_none(entry.get("FriendlyName")),
        bus_location=instance_id or None,
        extra={"status": entry.get("Status")},
    )


def _enumerate_macos() -> UsbEnumerationResult:
    completed = _run_capture(
        ["system_profiler", "-json", "SPUSBDataType"], "macos",
    )
    if isinstance(completed, UsbEnumerationResult):
        return completed
    try:
        payload = json.loads(completed)
    except ValueError as error:
        return UsbEnumerationResult(backend="macos", devices=[],
                                    error=f"json parse: {error}")
    devices: List[UsbDevice] = []
    for entry in payload.get("SPUSBDataType", []):
        _walk_macos_node(entry, devices)
    return UsbEnumerationResult(backend="macos", devices=devices)


def _walk_macos_node(node: Dict[str, Any], out: List[UsbDevice]) -> None:
    if "vendor_id" in node or "product_id" in node:
        out.append(UsbDevice(
            vendor_id=_hex4_from_macos(node.get("vendor_id")),
            product_id=_hex4_from_macos(node.get("product_id")),
            manufacturer=_strip_or_none(node.get("manufacturer")),
            product=_strip_or_none(node.get("_name")),
            serial=_strip_or_none(node.get("serial_num")),
            bus_location=_strip_or_none(node.get("location_id")),
        ))
    for child in node.get("_items", []) or []:
        if isinstance(child, dict):
            _walk_macos_node(child, out)


def _enumerate_linux() -> UsbEnumerationResult:
    root = Path("/sys/bus/usb/devices")
    if not root.is_dir():
        return UsbEnumerationResult(backend="linux", devices=[],
                                    error="/sys/bus/usb/devices not found")
    devices: List[UsbDevice] = []
    for entry in sorted(root.iterdir()):
        if ":" in entry.name:
            continue  # skip interface aliases
        device = _linux_node_to_device(entry)
        if device is not None:
            devices.append(device)
    return UsbEnumerationResult(backend="linux", devices=devices)


def _linux_node_to_device(node: Path) -> Optional[UsbDevice]:
    vendor = _read_sys_file(node / "idVendor")
    product = _read_sys_file(node / "idProduct")
    if vendor is None and product is None:
        return None
    return UsbDevice(
        vendor_id=vendor.lower() if vendor else None,
        product_id=product.lower() if product else None,
        manufacturer=_read_sys_file(node / "manufacturer"),
        product=_read_sys_file(node / "product"),
        serial=_read_sys_file(node / "serial"),
        bus_location=node.name,
    )


def _run_capture(cmd: List[str], backend: str) -> Any:
    try:
        completed = subprocess.run(  # nosec B603 B607  # nosemgrep: python.lang.security.audit.dangerous-subprocess-use-audit.dangerous-subprocess-use-audit  # reason: argv list (never shell=True); cmd is built from project-controlled allowlists in _enumerate_via_lsusb / _enumerate_via_system_profiler — no user input flows in
            cmd, capture_output=True, text=True,
            timeout=_SUBPROCESS_TIMEOUT_S, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return UsbEnumerationResult(
            backend=backend, devices=[],
            error=f"{cmd[0]}: {error}",
        )
    if completed.returncode != 0:
        return UsbEnumerationResult(
            backend=backend, devices=[],
            error=f"{cmd[0]} exit {completed.returncode}: "
                  f"{completed.stderr.strip()[:200]}",
        )
    return completed.stdout


def _read_sys_file(path: Path) -> Optional[str]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace").strip()
    except (OSError, UnicodeDecodeError):
        return None
    return text or None


def _hex4(value: Any) -> Optional[str]:
    if value is None:
        return None
    try:
        return f"{int(value):04x}"
    except (TypeError, ValueError):
        return None


def _hex4_from_macos(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    match = re.match(r"0x([0-9A-Fa-f]+)", text)
    if match:
        try:
            return f"{int(match.group(1), 16):04x}"
        except ValueError:
            return None
    return text or None


def _strip_or_none(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _pyusb_bus(dev: Any) -> Optional[str]:
    bus = getattr(dev, "bus", None)
    address = getattr(dev, "address", None)
    if bus is None and address is None:
        return None
    return f"bus={bus} addr={address}"


def _safe_string(dev: Any, attr: str) -> Optional[str]:
    """Look up a USB string descriptor; tolerate libusb permission errors."""
    try:
        text = getattr(dev, attr, None)
    except (OSError, ValueError, NotImplementedError):
        return None
    if text is None:
        return None
    return str(text).strip() or None


__all__ = [
    "UsbDevice", "UsbEnumerationResult", "list_usb_devices",
]
