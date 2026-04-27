"""mDNS / Zeroconf LAN discovery for AutoControl hosts.

Hosts call :class:`HostAdvertiser` to broadcast their presence on the
local network; viewers call :class:`HostBrowser` to discover them. Service
type is ``_autocontrol._tcp.local.``. Each advertised service carries
TXT properties: ``host_id``, ``signaling_url`` (optional). The viewer GUI
turns each discovered service into a one-click connect entry.

Both classes are fail-soft: if zeroconf isn't installed (the ``discovery``
extra) they raise on construction with a clear message — the GUI checks
:func:`is_discovery_available` before instantiating.
"""
from __future__ import annotations

import socket
import threading
from typing import Callable, Dict, List, Optional

from je_auto_control.utils.logging.logging_instance import autocontrol_logger

try:
    from zeroconf import ServiceBrowser, ServiceInfo, ServiceListener, Zeroconf
    _AVAILABLE = True
except ImportError:  # pragma: no cover - optional dep
    Zeroconf = None  # type: ignore[assignment]
    ServiceBrowser = None  # type: ignore[assignment]
    ServiceInfo = None  # type: ignore[assignment]
    ServiceListener = None  # type: ignore[assignment]
    _AVAILABLE = False


_SERVICE_TYPE = "_autocontrol._tcp.local."


def is_discovery_available() -> bool:
    return _AVAILABLE


def _local_ip() -> str:
    """Best-effort: ask the kernel which interface routes to a public IP."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.connect(("8.8.8.8", 80))  # nosec B113  # reason: UDP no-traffic probe; no actual packet sent
            return sock.getsockname()[0]
        finally:
            sock.close()
    except OSError:
        return "127.0.0.1"


class HostAdvertiser:
    """Broadcast a single host on the LAN; cancel via :meth:`stop`."""

    def __init__(self, *, host_id: str, port: int = 0,
                 signaling_url: Optional[str] = None,
                 server_name: Optional[str] = None) -> None:
        if not _AVAILABLE:
            raise ImportError(
                "LAN discovery needs the 'discovery' extra: "
                "pip install je_auto_control[discovery]"
            )
        self._host_id = host_id
        self._zc = Zeroconf()
        ip = _local_ip()
        props = {b"host_id": host_id.encode("utf-8")}
        if signaling_url:
            props[b"signaling_url"] = signaling_url.encode("utf-8")
        name = server_name or socket.gethostname()
        self._info = ServiceInfo(
            _SERVICE_TYPE,
            f"{name}-{host_id}.{_SERVICE_TYPE}",
            addresses=[socket.inet_aton(ip)],
            port=int(port) or 0,
            properties=props,
            server=f"{name}.local.",
        )
        self._zc.register_service(self._info)
        autocontrol_logger.info(
            "lan discovery: advertised host_id=%s on %s", host_id, ip,
        )

    def stop(self) -> None:
        try:
            self._zc.unregister_service(self._info)
        except (RuntimeError, OSError) as error:
            autocontrol_logger.debug("zeroconf unregister: %r", error)
        self._zc.close()


class _BrowseListener:
    """Adapter that pumps zeroconf events into the user callback."""

    def __init__(self, on_change: Callable[[Dict[str, dict]], None]) -> None:
        self._on_change = on_change
        self._services: Dict[str, dict] = {}
        self._lock = threading.Lock()

    def add_service(self, zc: "Zeroconf", type_: str, name: str) -> None:
        info = zc.get_service_info(type_, name, timeout=2000)
        if info is None:
            return
        props = info.properties or {}
        host_id = (props.get(b"host_id") or b"").decode(
            "utf-8", errors="replace",
        )
        signaling_url = (props.get(b"signaling_url") or b"").decode(
            "utf-8", errors="replace",
        )
        addresses = [socket.inet_ntoa(a) for a in (info.addresses or [])]
        with self._lock:
            self._services[name] = {
                "name": name,
                "host_id": host_id,
                "signaling_url": signaling_url,
                "ip": addresses[0] if addresses else "",
                "port": info.port or 0,
            }
            snapshot = dict(self._services)
        self._on_change(snapshot)

    def remove_service(self, zc: "Zeroconf", type_: str, name: str) -> None:
        with self._lock:
            self._services.pop(name, None)
            snapshot = dict(self._services)
        self._on_change(snapshot)

    def update_service(self, zc: "Zeroconf", type_: str, name: str) -> None:
        # Re-fetch and treat as add (replaces old entry under same name)
        self.add_service(zc, type_, name)


class HostBrowser:
    """Watch the LAN for AutoControl hosts.

    ``on_change(services_by_name: dict)`` fires on every add/remove/update.
    Cancel via :meth:`stop`.
    """

    def __init__(self, on_change: Callable[[Dict[str, dict]], None]) -> None:
        if not _AVAILABLE:
            raise ImportError(
                "LAN discovery needs the 'discovery' extra: "
                "pip install je_auto_control[discovery]"
            )
        self._zc = Zeroconf()
        self._listener = _BrowseListener(on_change)
        self._browser = ServiceBrowser(
            self._zc, _SERVICE_TYPE, listener=self._listener,
        )

    def stop(self) -> None:
        try:
            self._browser.cancel()
        except (RuntimeError, OSError):
            pass
        self._zc.close()


def list_local_services(timeout_s: float = 2.0) -> List[dict]:
    """One-shot synchronous browse (collects whatever shows up in ``timeout``)."""
    if not _AVAILABLE:
        return []
    snapshot: Dict[str, dict] = {}
    done = threading.Event()
    def _on(services: Dict[str, dict]) -> None:
        snapshot.clear()
        snapshot.update(services)
    browser = HostBrowser(on_change=_on)
    try:
        done.wait(timeout=timeout_s)
    finally:
        browser.stop()
    return list(snapshot.values())


__all__ = [
    "HostAdvertiser", "HostBrowser",
    "is_discovery_available", "list_local_services",
]
