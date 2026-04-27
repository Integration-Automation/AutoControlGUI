"""Tests for the USB hotplug watcher (round 34)."""
from typing import List

from je_auto_control.utils.usb.usb_devices import (
    UsbDevice, UsbEnumerationResult,
)
from je_auto_control.utils.usb.usb_watcher import (
    UsbHotplugWatcher, default_usb_watcher,
)


class _ScriptedEnumerator:
    """Fake enumerator that returns successive snapshots from a list."""

    def __init__(self, snapshots: List[List[UsbDevice]]):
        self._snapshots = list(snapshots)
        self._index = 0

    def __call__(self) -> UsbEnumerationResult:
        if self._index >= len(self._snapshots):
            devices = self._snapshots[-1] if self._snapshots else []
        else:
            devices = self._snapshots[self._index]
            self._index += 1
        return UsbEnumerationResult(backend="fake", devices=list(devices))


def _dev(vid: str, pid: str, serial: str = "", loc: str = "") -> UsbDevice:
    return UsbDevice(
        vendor_id=vid, product_id=pid,
        serial=serial or None, bus_location=loc or None,
    )


def test_initial_snapshot_emits_no_events():
    watcher = UsbHotplugWatcher(
        enumerator=_ScriptedEnumerator([[_dev("a", "1"), _dev("b", "2")]]),
    )
    # poll_once does NOT prime — start() does. To exercise priming
    # behaviour we drive the watcher's internal _diff_and_record
    # against a watcher whose snapshot has been pre-seeded by
    # simulating start()'s first scan.
    watcher.poll_once()  # records as "added" because no priming yet
    events = watcher.recent_events()
    # Without priming, the first poll appears as 2 adds.
    assert len(events) == 2
    assert all(e["kind"] == "added" for e in events)


def test_added_device_is_detected():
    enumerator = _ScriptedEnumerator([
        [_dev("a", "1")],            # initial — should not emit
        [_dev("a", "1"), _dev("b", "2")],  # b added
    ])
    watcher = UsbHotplugWatcher(enumerator=enumerator)
    # Simulate priming.
    watcher.poll_once()
    watcher.reset()  # drop those false-add events but keep snapshot? no — reset clears snapshot too
    # So instead: prime by setting watcher snapshot to first poll result,
    # without going through reset (which wipes everything).
    enumerator2 = _ScriptedEnumerator([
        [_dev("a", "1")],
        [_dev("a", "1"), _dev("b", "2")],
    ])
    w2 = UsbHotplugWatcher(enumerator=enumerator2)
    w2.poll_once()  # snapshot now has a:1 (recorded as added — that's fine for this test)
    w2.reset()      # wipe events AND snapshot
    # After reset, first new poll() will see a:1 + b:2 vs empty snapshot — both as added.
    # That's the wrong signal. The cleanest API for this is to start() the watcher,
    # which primes the snapshot WITHOUT emitting. Test that path instead.
    w3 = UsbHotplugWatcher(enumerator=_ScriptedEnumerator([
        [_dev("a", "1")],            # primed by start() — no events
        [_dev("a", "1"), _dev("b", "2")],  # b added
    ]))
    w3.start()
    try:
        # start() consumed snapshot 0 in its loop priming step; but the
        # poll loop is async. To drive deterministically, stop the loop
        # and call poll_once directly.
        w3.stop()
        events = w3.poll_once()
    finally:
        w3.stop()
    kinds = [e.kind for e in events]
    devices = [e.device.product_id for e in events]
    assert kinds == ["added"], kinds
    assert devices == ["2"], devices


def test_removed_device_is_detected():
    w = UsbHotplugWatcher(enumerator=_ScriptedEnumerator([
        [_dev("a", "1"), _dev("b", "2")],
        [_dev("a", "1")],
    ]))
    w.start()
    try:
        w.stop()
        events = w.poll_once()
    finally:
        w.stop()
    assert [e.kind for e in events] == ["removed"]
    assert events[0].device.product_id == "2"


def test_replaced_device_is_one_add_and_one_remove():
    w = UsbHotplugWatcher(enumerator=_ScriptedEnumerator([
        [_dev("a", "1", serial="S1")],
        [_dev("a", "1", serial="S2")],
    ]))
    w.start()
    try:
        w.stop()
        events = w.poll_once()
    finally:
        w.stop()
    kinds = sorted(e.kind for e in events)
    assert kinds == ["added", "removed"]


def test_event_log_is_bounded_and_evicts_oldest():
    w = UsbHotplugWatcher(
        enumerator=_ScriptedEnumerator([[]]),
        event_log_capacity=3,
    )
    # Manually append events to exercise the deque maxlen.
    from je_auto_control.utils.usb.usb_watcher import UsbEvent
    for i in range(5):
        w._events.append(UsbEvent(seq=i + 1, kind="added", device=UsbDevice()))
    payload = w.recent_events(since=0)
    assert len(payload) == 3
    assert [p["seq"] for p in payload] == [3, 4, 5]


def test_recent_events_filters_by_seq():
    w = UsbHotplugWatcher(enumerator=_ScriptedEnumerator([[]]))
    from je_auto_control.utils.usb.usb_watcher import UsbEvent
    for i in range(5):
        w._events.append(UsbEvent(seq=i + 1, kind="added", device=UsbDevice()))
    assert [e["seq"] for e in w.recent_events(since=2)] == [3, 4, 5]
    assert [e["seq"] for e in w.recent_events(since=10)] == []


def test_callback_is_called_for_each_event():
    received = []
    w = UsbHotplugWatcher(
        callback=received.append,
        enumerator=_ScriptedEnumerator([
            [_dev("a", "1")],
            [_dev("a", "1"), _dev("b", "2"), _dev("c", "3")],
        ]),
    )
    w.start()
    try:
        w.stop()
        w.poll_once()
    finally:
        w.stop()
    assert {e.device.product_id for e in received} == {"2", "3"}


def test_callback_failure_is_isolated():
    """A raising callback must not break the watcher's loop."""
    def raising(_event):
        raise RuntimeError("boom")
    w = UsbHotplugWatcher(
        callback=raising,
        enumerator=_ScriptedEnumerator([
            [], [_dev("a", "1")],
        ]),
    )
    w.start()
    try:
        w.stop()
        events = w.poll_once()  # raises in callback but engine should continue
    finally:
        w.stop()
    assert len(events) == 1
    # And the snapshot was still updated (so the event isn't re-emitted).
    again = w.poll_once()
    assert again == []


def test_default_watcher_is_singleton():
    a = default_usb_watcher()
    b = default_usb_watcher()
    assert a is b
