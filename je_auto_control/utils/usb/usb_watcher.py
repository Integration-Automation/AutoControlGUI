"""Polling-based USB hotplug watcher.

There is no portable Python API for true USB hotplug events without
``libusb`` (and even libusb's hotplug callback isn't supported on
Windows). Instead this module diffs successive enumerations from
:func:`list_usb_devices` to detect adds and removes — good enough for
most automation scenarios where 1–3 second latency is acceptable.

Each detected change becomes an :class:`UsbEvent` appended to a bounded
ring buffer (default 500 events) so late subscribers can catch up via
``recent_events(since=seq)``. The same events are also pushed to a
caller-supplied callback for push-style consumers.
"""
from __future__ import annotations

import threading
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable, Deque, Dict, List, Optional, Tuple

from je_auto_control.utils.logging.logging_instance import autocontrol_logger
from je_auto_control.utils.usb.usb_devices import (
    SUBPROCESS_TIMEOUT_S, UsbDevice, list_usb_devices,
)


_DEFAULT_INTERVAL_S = 2.0
#: How long ``stop()`` waits for the poller. It must outlast one enumeration:
#: the poller only sees the stop event between enumerations, and the platform
#: tool behind one (PowerShell ``Get-PnpDevice``, ``lsusb``,
#: ``system_profiler``) is bounded by ``SUBPROCESS_TIMEOUT_S``. The old 2 s
#: was shorter than a cold PowerShell start on a loaded machine.
_STOP_JOIN_TIMEOUT_S = SUBPROCESS_TIMEOUT_S + 1.0
_DEFAULT_EVENT_LOG_CAPACITY = 500
_EVENT_KIND_ADDED = "added"
_EVENT_KIND_REMOVED = "removed"


@dataclass
class UsbEvent:
    """One add/remove change between two enumerations."""

    seq: int
    kind: str  # "added" or "removed"
    device: UsbDevice = field(default_factory=UsbDevice)

    def to_dict(self) -> Dict[str, Any]:
        """JSON-ready form: ``seq``, ``kind`` and the device as a dict."""
        return {
            "seq": self.seq,
            "kind": self.kind,
            "device": self.device.to_dict(),
        }


_DeviceKey = Tuple[Optional[str], Optional[str], Optional[str], Optional[str]]


def _device_key(device: UsbDevice) -> _DeviceKey:
    """Identity key — best effort with serial when available, falling
    back to bus/location so otherwise-identical sticks plugged into
    different ports register as separate devices.
    """
    return (
        device.vendor_id, device.product_id,
        device.serial, device.bus_location,
    )


class UsbHotplugWatcher:
    """Diff successive USB enumerations and emit add/remove events."""

    def __init__(self,
                 *,
                 callback: Optional[Callable[[UsbEvent], None]] = None,
                 poll_interval_s: float = _DEFAULT_INTERVAL_S,
                 event_log_capacity: int = _DEFAULT_EVENT_LOG_CAPACITY,
                 enumerator: Optional[Callable[[], Any]] = None,
                 ) -> None:
        self._callback = callback
        self._interval = max(0.25, float(poll_interval_s))
        self._enumerator = enumerator or list_usb_devices
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._lifecycle_lock = threading.Lock()
        self._snapshot: Dict[_DeviceKey, UsbDevice] = {}
        #: Bumped by every snapshot write, so a slow priming
        #: enumeration can tell whether it is still the newest reading.
        self._snapshot_epoch = 0
        self._events: Deque[UsbEvent] = deque(maxlen=int(event_log_capacity))
        self._next_seq: int = 1

    @property
    def is_running(self) -> bool:
        """Whether a poller thread is alive for the current run."""
        with self._lifecycle_lock:
            return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        """Start polling on a daemon thread; a no-op while already running."""
        with self._lifecycle_lock:
            if self._thread is not None:
                return
            # A fresh event per run, never ``clear()`` on the old one: a
            # poller that outlived its ``stop()`` (still inside an
            # enumeration) would see a cleared event, carry on polling, and
            # run beside the new one untracked for the life of the process.
            self._stop = threading.Event()
            self._thread = threading.Thread(
                target=self._loop, args=(self._stop,),
                name="usb-hotplug", daemon=True,
            )
            self._thread.start()
        autocontrol_logger.info(
            "usb hotplug watcher: polling every %.1fs", self._interval,
        )

    def stop(self) -> None:
        """Stop polling and wait for the poller to finish its enumeration."""
        with self._lifecycle_lock:
            self._stop.set()
            thread = self._thread
            self._thread = None
        if thread is None:
            return
        # The poller can only notice the event between enumerations, and one
        # enumeration may take as long as its subprocess timeout. Returning
        # sooner reports "stopped" while the thread is still running.
        thread.join(timeout=_STOP_JOIN_TIMEOUT_S)
        if thread.is_alive():
            autocontrol_logger.warning(
                "usb hotplug watcher: poller still inside an enumeration "
                "after %.0fs; it exits as soon as that returns",
                _STOP_JOIN_TIMEOUT_S,
            )

    def recent_events(self, *, since: int = 0,
                      limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """Return events with ``seq > since`` in chronological order."""
        with self._lock:
            payload = [
                event.to_dict() for event in self._events
                if event.seq > int(since)
            ]
        if limit is not None:
            payload = payload[-int(limit):]
        return payload

    def reset(self) -> int:
        """Clear the event log and the snapshot. Returns events dropped."""
        with self._lock:
            count = len(self._events)
            self._events.clear()
            self._snapshot = {}
            self._snapshot_epoch += 1
            self._next_seq = 1
        return count

    def poll_once(self) -> List[UsbEvent]:
        """Run one diff cycle synchronously; useful for tests."""
        return self._diff_and_record()

    def _loop(self, stop: threading.Event) -> None:
        # Prime the snapshot without emitting events for already-present
        # devices — the watcher tracks *changes from now*, not the
        # initial inventory.
        with self._lock:
            epoch = self._snapshot_epoch
        try:
            initial = self._enumerator()
            with self._lifecycle_lock:
                # Superseded, not merely stopped: once a newer run exists its
                # snapshot is the one that counts. A run that was only stopped
                # still primes, so start(); stop(); poll_once() reports changes
                # since start() and not the whole inventory -- whether the
                # stop landed before or after this enumeration returned.
                if stop is not self._stop:
                    return
                with self._lock:
                    # ...unless a poll already wrote a newer reading while
                    # this enumeration was running: stop() gives up after
                    # _STOP_JOIN_TIMEOUT_S, so poll_once() can land first, and
                    # priming over it would report its devices as removed next.
                    if self._snapshot_epoch != epoch:
                        return
                    self._snapshot = {
                        _device_key(dev): dev for dev in initial.devices
                    }
                    self._snapshot_epoch += 1
        except Exception as error:  # noqa: BLE001  # pylint: disable=broad-except  # reason: enumeration may fail per-OS
            autocontrol_logger.warning(
                "usb hotplug initial enumeration: %r", error,
            )
        while not stop.is_set():
            stop.wait(self._interval)
            if stop.is_set():
                return
            try:
                self._diff_and_record()
            except Exception as error:  # noqa: BLE001  # pylint: disable=broad-except  # reason: keep the loop alive across enumeration failures
                autocontrol_logger.warning(
                    "usb hotplug poll: %r", error,
                )

    def _diff_and_record(self) -> List[UsbEvent]:
        result = self._enumerator()
        current: Dict[_DeviceKey, UsbDevice] = {
            _device_key(dev): dev for dev in result.devices
        }
        new_events: List[UsbEvent] = []
        with self._lock:
            previous = self._snapshot
            added_keys = set(current) - set(previous)
            removed_keys = set(previous) - set(current)
            for key in added_keys:
                event = UsbEvent(
                    seq=self._next_seq, kind=_EVENT_KIND_ADDED,
                    device=current[key],
                )
                self._next_seq += 1
                self._events.append(event)
                new_events.append(event)
            for key in removed_keys:
                event = UsbEvent(
                    seq=self._next_seq, kind=_EVENT_KIND_REMOVED,
                    device=previous[key],
                )
                self._next_seq += 1
                self._events.append(event)
                new_events.append(event)
            self._snapshot = current
            self._snapshot_epoch += 1
        if self._callback is not None:
            for event in new_events:
                try:
                    self._callback(event)
                except Exception as error:  # noqa: BLE001  # pylint: disable=broad-except  # reason: never let a bad callback break the watcher loop
                    autocontrol_logger.warning(
                        "usb hotplug callback: %r", error,
                    )
        return new_events


_default_watcher: Optional[UsbHotplugWatcher] = None
_default_lock = threading.Lock()


def default_usb_watcher() -> UsbHotplugWatcher:
    """Process-wide singleton watcher — shared by REST + executor + GUI."""
    global _default_watcher
    with _default_lock:
        if _default_watcher is None:
            _default_watcher = UsbHotplugWatcher()
        return _default_watcher


__all__ = [
    "UsbEvent", "UsbHotplugWatcher", "default_usb_watcher",
]
